"""Audit (and fix) blockout-status visibility on upcoming plans.

Read-only by default. For each registered service's upcoming plans, lists who is
scheduled + their status, then joins each person's blockouts (SERVICES product:
services/v2/people/{id}/blockouts — the People product has NO blockouts link and 404s)
against the plan date. Reports DRIFT: people scheduled Unconfirmed who actually have a
blockout covering that date, so the plan still shows them yellow-Unconfirmed instead
of blocked.

The blockout join is the Category-B derived field the UI computes at render time and
never stores. The web UI surfaces it live only when you schedule someone interactively;
a *template import* (book_service.py) drops people in as plain U and PCO never
re-evaluates — that's why blocked choir members sit yellow on imported plans.

PCO exposes no writable "blocked" flag (statuses are only C/U/D), so the fix is to set
each blocked person to Declined (status 'D') with the blockout as decline_reason. A
status PATCH is SILENT — verified: notification_sent_at / notification_prepared_at stay
null, no email/text fires.

Usage:
    python blockout_reconcile.py [--days N]            audit only (default 21d)
    python blockout_reconcile.py [--days N] --apply    snapshot each plan, then decline
                                                        blocked-out people with a reason
"""
import sys
import datetime as dt
from zoneinfo import ZoneInfo

import requests
from pco_cache import session  # reuse the authed session
from snapshot import snapshot_plan

import service_registry as reg

SVC = "https://api.planningcenteronline.com/services/v2"
# Blockouts are a SERVICES-product resource (services/v2/people/{id}/blockouts).
# The People product (people/v2) has NO blockouts link — hitting it 404s and, if
# swallowed, masquerades as "zero blockouts". Always use SVC here.
CENTRAL = ZoneInfo("America/Chicago")  # set to your local timezone

STATUS = {"C": "Confirmed", "U": "Unconfirmed", "D": "Declined"}


def g(url, **params):
    r = session.get(url, params=params)
    r.raise_for_status()
    return r.json()


def upcoming_plans(st_id, horizon):
    today = dt.date.today()
    out = []
    data = g(f"{SVC}/service_types/{st_id}/plans",
             filter="future", per_page=50, order="sort_date").get("data", [])
    for p in data:
        sd = (p.get("attributes", {}).get("sort_date") or "")[:10]
        if not sd:
            continue
        d = dt.date.fromisoformat(sd)
        if today <= d <= horizon:
            out.append((d, p["id"], p.get("attributes", {}).get("dates") or sd))
    return out


def team_members(st_id, pid):
    """Each scheduled person: (person_id, name, status, team)."""
    rows = []
    url = f"{SVC}/service_types/{st_id}/plans/{pid}/team_members"
    params = {"per_page": 100, "include": "person"}
    while url:
        body = g(url, **params)
        for tm in body.get("data", []):
            a = tm.get("attributes", {})
            rel = tm.get("relationships", {}).get("person", {}).get("data") or {}
            rows.append({
                "person_id": rel.get("id"),
                "name": a.get("name"),
                "status": a.get("status"),
                "team": a.get("team_position_name"),
                "tm_id": tm["id"],
            })
        url = body.get("links", {}).get("next")
        params = {}
    return rows


def _local_date(iso):
    """UTC ISO ('2025-11-10T05:59:59Z') -> local Central date."""
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return d.astimezone(CENTRAL).date()


def blockouts_for(person_id):
    """All blockout ranges for a person (local Central dates). Cached per run.
    Errors are NOT swallowed — a failed fetch raises rather than faking 'no blockouts'.
    """
    if person_id in _BO_CACHE:
        return _BO_CACHE[person_id]
    body = g(f"{SVC}/people/{person_id}/blockouts", per_page=100)
    ranges = []
    for b in body.get("data", []):
        a = b.get("attributes", {})
        s, e = a.get("starts_at"), a.get("ends_at")
        if not (s and e):
            continue
        ranges.append({
            "start": _local_date(s),
            "end": _local_date(e),
            "reason": a.get("reason") or (a.get("description") or "(no reason)"),
            "repeats": (a.get("repeat_frequency") or "no_repeat") != "no_repeat",
            "repeat_freq": a.get("repeat_frequency"),
        })
    _BO_CACHE[person_id] = ranges
    return ranges


_BO_CACHE = {}


def covers(ranges, day):
    """Return (reason, repeats_flag) if a blockout covers `day`, else None.
    Repeating blockouts are surfaced as a same-weekday best-effort match within
    their active span and flagged so they get a manual confirm."""
    for r in ranges:
        if r["start"] <= day <= r["end"]:
            return (r["reason"], r["repeats"])
        if r["repeats"] and day >= r["start"] and day.weekday() == r["start"].weekday():
            return (f"{r['reason']} [repeating {r['repeat_freq']}]", True)
    return None


def decline(st_id, pid, tm_id, reason):
    """Set a PlanPerson to Declined with a reason. Silent — no notification fires."""
    payload = {"data": {"type": "PlanPerson",
                        "attributes": {"status": "D", "decline_reason": reason[:255]}}}
    r = session.patch(
        f"{SVC}/service_types/{st_id}/plans/{pid}/team_members/{tm_id}", json=payload)
    r.raise_for_status()
    return r.json()["data"]["attributes"]


def main():
    days = 21
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    apply = "--apply" in sys.argv
    horizon = dt.date.today() + dt.timedelta(days=days)
    mode = "APPLY (decline blocked-out)" if apply else "READ-ONLY"
    print(f"Blockout reconcile — today {dt.date.today()} → {horizon} ({days}d), {mode}\n")

    total_drift = 0
    for handle in reg.handles():
        svc = reg.SERVICES[handle]
        st_id = svc["service_type_id"]
        plans = upcoming_plans(st_id, horizon)
        if not plans:
            continue
        print(f"=== {handle}  ({svc['service_type_name']})  st={st_id} ===")
        for day, pid, label in plans:
            tms = team_members(st_id, pid)
            drift = []
            for tm in tms:
                if not tm["person_id"]:
                    continue
                hit = covers(blockouts_for(tm["person_id"]), day)
                if hit and tm["status"] != "D":
                    drift.append((tm, hit[0], hit[1]))
            tag = f"  ⚠ {len(drift)} blockout-vs-status drift" if drift else "  ✓ clean"
            print(f"  {day} plan {pid}  ({len(tms)} scheduled){tag}")
            if drift and apply:
                # snapshot once per plan before any write (PCO has no edit history)
                try:
                    snapshot_plan(session, st_id, pid, label="pre-blockout-reconcile",
                                  reason="decline blocked-out people")
                except Exception as e:
                    print(f"      snapshot failed ({e!r}); skipping writes on this plan")
                    continue
            for tm, reason, repeats in drift:
                mark = "~" if repeats else "•"
                line = (f"      {mark} {tm['name']:24} {STATUS.get(tm['status'], tm['status'])}"
                        f" on [{tm['team']}] — blocked out: {reason}")
                if apply:
                    a = decline(st_id, pid, tm["tm_id"], reason)
                    line += f"   → set Declined (notif_sent={a.get('notification_sent_at')})"
                print(line)
            total_drift += len(drift)
        print()
    verb = "declined" if apply else "drift across window"
    print(f"TOTAL {verb}: {total_drift}")


if __name__ == "__main__":
    main()
