"""Book a recurring service the way the UI does — shell PLUS its template, in one step.

The template is the unmarked default. `book_service.py sunday_am 2026-06-28` resolves the
handle through service_registry, finds-or-creates the dated shell, sets the default time,
and imports the registered master template (items + needed positions + people, Unconfirmed)
in a single `import` action. Only deviations are surfaced — a wrong weekday, an already-booked
date, an existing plan that would be re-scaffolded.

A bare/blank plan is the *marked* exception: pass --blank to skip the template import.

Usage:
    python book_service.py <handle> <YYYY-MM-DD> [--apply] [--blank] [--force] [--title "..."]
      handle   sunday_am | wed_night  (any handle in service_registry; aliases ok: am/wed/...)
      --apply  actually write (default is dry-run)
      --blank  create the shell only, no template (the marked exception)
      --force  if a plan already exists on that date, re-import the template onto it
               (snapshots first). Pair with --no-items on a plan that already has items.
      --no-items / --no-people / --no-notes  limit what the template import copies
      --title  title for a newly created shell (default: the date)

People always land Unconfirmed (the template stores them U); this never sends invites.
"""
import os
import sys
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import service_registry as reg
from snapshot import snapshot_plan
from apply_template import import_template

load_dotenv(os.path.expanduser("~/Secrets/pco.env"))
B = "https://api.planningcenteronline.com/services/v2"
TZ = ZoneInfo("America/Chicago")  # set to your local timezone

session = requests.Session()
session.auth = (os.environ["PCO_CLIENT_ID"], os.environ["PCO_SECRET"])


def g(path, **params):
    r = session.get(f"{B}{path}", params=params)
    r.raise_for_status()
    return r.json()


def find_plan_on_date(st_id, date_str):
    """Return a plan dict whose sort_date falls on date_str, else None."""
    data = g(f"/service_types/{st_id}/plans",
             filter="future", per_page=100, order="sort_date").get("data", [])
    # future filter can miss today / past; also scan a plain recent page as a fallback
    seen = {p["id"]: p for p in data}
    for p in g(f"/service_types/{st_id}/plans", per_page=100, order="-sort_date").get("data", []):
        seen.setdefault(p["id"], p)
    for p in seen.values():
        sd = (p.get("attributes", {}).get("sort_date") or "")[:10]
        if sd == date_str:
            return p
    return None


def plan_counts(st_id, pid):
    def n(sub):
        return len(g(f"/service_types/{st_id}/plans/{pid}/{sub}", per_page=100).get("data", []))
    return n("items"), n("team_members"), n("needed_positions")


def main():
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    pos = [a for a in args if not a.startswith("--")]
    title_arg = None
    if "--title" in args:
        i = args.index("--title")
        if i + 1 < len(args):
            title_arg = args[i + 1]
            pos = [a for a in pos if a != title_arg]
    if len(pos) < 2:
        print(__doc__)
        sys.exit(1)

    handle, date_str = pos[0], pos[1]
    apply = "--apply" in flags
    blank = "--blank" in flags
    force = "--force" in flags
    # granular copy flags (matter mainly on --force re-import so items aren't duplicated)
    ci, cp, cn = ("--no-items" not in flags, "--no-people" not in flags,
                  "--no-notes" not in flags)

    try:
        handle, svc = reg.resolve(handle)
    except KeyError as e:
        sys.exit(str(e))
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        sys.exit(f"bad date {date_str!r} — use YYYY-MM-DD")

    st_id = svc["service_type_id"]
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"{mode} — book {handle} ({svc['service_type_name']}) on {date_str}")

    # Deviation flag: wrong weekday for this service
    if d.weekday() != svc["weekday"]:
        wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
        print(f"  ⚠ deviation: {date_str} is a {wd}; {handle} normally falls on weekday "
              f"{svc['weekday']}. Proceeding anyway.")

    # plan_time from the registry default (DST-correct via zoneinfo)
    hh, mm = (int(x) for x in svc["time"].split(":"))
    starts = datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
    ends = starts + datetime.timedelta(minutes=svc["duration_min"])
    # PCO ignores an offset on the wire and treats the literal as UTC — so send
    # explicit UTC, not local-with-offset, or 7:00pm Central lands as 7:00pm UTC.
    def _utc(dt):
        return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    starts_w, ends_w = _utc(starts), _utc(ends)

    existing = find_plan_on_date(st_id, date_str)
    if existing:
        pid = existing["id"]
        ni, np_, npos = plan_counts(st_id, pid)
        print(f"  plan already exists on {date_str}: {pid} "
              f"(items={ni}, people={np_}, needed_positions={npos})")
        if not force:
            print("  already booked — nothing to do. Use --force to re-import the template.")
            return
        print("  --force: will re-import the template onto the existing plan")

    # --- writes below ---
    if not apply:
        print(f"  would set time: {starts.isoformat()} ({svc['time_type']})")
        if blank:
            print("  --blank: shell only, no template import")
        else:
            parts = (["items"] if ci else []) + \
                    (["needed positions + people (Unconfirmed)"] if cp else []) + \
                    (["notes"] if cn else [])
            print(f"  would import template {svc['template_id']} "
                  f"({svc['template_name']}) — {', '.join(parts) or 'nothing selected'}")
            if existing and force and ci:
                print("    note: existing plan already has items — consider --no-items "
                      "so the template's items aren't duplicated")
        print("\n(dry-run — re-run with --apply)")
        return

    if existing:
        pid = existing["id"]
        # re-import is destructive-ish; snapshot first
        snapshot_plan(session, st_id, pid, label="pre-reimport",
                      reason=f"book_service --force re-import of {handle}")
    else:
        title = title_arg or date_str
        pid = session.post(
            f"{B}/service_types/{st_id}/plans",
            json={"data": {"type": "Plan", "attributes": {"title": title}}},
        ).json()["data"]["id"]
        print(f"  + created shell {pid} (title {title!r})")
        # plan_time only on fresh shells (don't duplicate on re-import)
        session.post(
            f"{B}/service_types/{st_id}/plans/{pid}/plan_times",
            json={"data": {"type": "PlanTime", "attributes": {
                "starts_at": starts_w, "ends_at": ends_w,
                "time_type": svc["time_type"]}}},
        )
        print(f"  + time {starts.isoformat()} ({svc['time_type']})")

    if blank:
        print("  --blank: skipped template import (marked exception).")
    else:
        r = import_template(st_id, pid, svc["template_id"],
                            copy_items=ci, copy_people=cp, copy_notes=cn, sess=session)
        if r.status_code in (200, 201):
            meta = r.json().get("data", {}).get("attributes", {})
            ni, np_, npos = plan_counts(st_id, pid)
            print(f"  + imported template {svc['template_id']} -> "
                  f"items={ni}, people={np_}, needed_positions={npos}")
            if meta.get("any_plan_people_missing_background_check"):
                print("  ⚠ some imported people are missing a required background check")
        else:
            print(f"  import FAILED: HTTP {r.status_code} {r.text[:300]}")
            return

    print(f"\nDone. plan {pid}  https://services.planningcenteronline.com/plans/{pid}")


if __name__ == "__main__":
    main()
