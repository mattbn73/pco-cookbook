#!/usr/bin/env python3
"""Run PCO's built-in Auto-schedule for one team on one plan.

This is the API form of the UI "Auto-schedule" button (matrix → team → Auto-schedule).
It is ADDITIVE and SEPARATE from any hand-rolled assignment scripts you may have. PCO's
auto-schedule rotates by "longest time since served," which is NOT necessarily the same
as your own rotation rules. Treat this as an experiment: dry-run, look at the picks,
decide whether you'd rather click one button than hand-edit a list.

    python autoschedule.py "Sunday AM" 2026-06-28 "Praise Team"          # dry-run (safe)
    python autoschedule.py "Sunday AM" 2026-06-28 "Praise Team" --apply  # perform it

Omit the team to list which teams still have unfilled positions on that plan.

--- ENDPOINT STATUS -------------------------------------------------------------------
Endpoint VERIFIED to exist (read-only probe 2026-06-26):
    GET  /service_types/{st}/plans/{plan}/autoschedule
      -> 200 {meta:{description:"Auto-schedule for a team. Returns a collection of
              scheduled PlanPersonAutoscheduleVertex", help:"POST to this URL ..."}}
The POST request BODY is UNVERIFIED — PCO's docs are JS-rendered and don't expose it, so
the body below (a JSON:API `team` relationship) is best-inference. The FIRST --apply
doubles as verification: a 422 is harmless and its `errors` will tell us the real contract
(see ENDPOINT-DISCOVERY.md "validation-probe"). Once a real run (or a DevTools "Copy as
cURL" capture) confirms it, delete this notice. Auto-scheduled people land Unconfirmed and
no emails are sent, so a wrong run is reversible — this script reports exactly which
team_members it added and how to undo them.
"""
import os, sys, json, requests
from pathlib import Path
from dotenv import load_dotenv
from pco_log import log

SECRETS = Path.home() / "Secrets" / "pco.env"
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing PCO creds")

BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)


def get(path, **params):
    url = path if path.startswith("http") else BASE + path
    r = session.get(url, params=params)
    r.raise_for_status()
    return r.json()


def autoschedule_body(team_id):
    # UNVERIFIED best-inference body — see ENDPOINT STATUS in the module docstring.
    return {"data": {"type": "PlanPersonAutoschedule",
                     "relationships": {"team": {"data": {"type": "Team", "id": team_id}}}}}


def find_service_type(name):
    types = get("/service_types", per_page=100)["data"]
    st = next((t for t in types
               if t["attributes"]["name"].strip().lower() == name.strip().lower()), None)
    if not st:
        sys.exit(f"Service type {name!r} not found")
    return st["id"]


def find_plan(st_id, date):
    for filt in ("future", "past"):
        url, params = f"{BASE}/service_types/{st_id}/plans", {"filter": filt, "order": "sort_date", "per_page": 50}
        while url:
            payload = get(url, **params)
            for p in payload["data"]:
                if p["attributes"].get("sort_date", "")[:10] == date:
                    return p["id"]
            url, params = payload.get("links", {}).get("next"), {}
    sys.exit(f"No plan found on {date} in that service type")


def team_members_for(st_id, plan_id, team_id):
    """Current team_member ids for one team on a plan (to diff before/after apply)."""
    out = {}
    tm = get(f"/service_types/{st_id}/plans/{plan_id}/team_members", per_page=100, include="team")
    for m in tm["data"]:
        tr = (m.get("relationships", {}).get("team", {}).get("data") or {})
        if tr.get("id") == team_id:
            out[m["id"]] = (m["attributes"].get("name", "?"), m["attributes"].get("team_position_name", "?"))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) < 2:
        sys.exit('Usage: python autoschedule.py "<service type>" <YYYY-MM-DD> ["<team>"] [--apply]')
    st_name, date = args[0], args[1]
    team_name = args[2] if len(args) > 2 else None

    st_id = find_service_type(st_name)
    plan_id = find_plan(st_id, date)
    print(f"Service type: {st_name} (id {st_id})")
    print(f"Plan: {date} (id {plan_id})\n")

    teams = {t["attributes"]["name"].strip(): t["id"]
             for t in get(f"/service_types/{st_id}/teams", per_page=100)["data"]}

    # Needed positions grouped by team (the unfilled slots auto-schedule would target).
    np = get(f"/service_types/{st_id}/plans/{plan_id}/needed_positions", per_page=100)["data"]
    needed_by_team = {}
    for n in np:
        tr = (n.get("relationships", {}).get("team", {}).get("data") or {})
        a = n["attributes"]
        needed_by_team.setdefault(tr.get("id"), []).append((a.get("team_position_name"), a.get("quantity")))

    if not team_name:
        print("Teams with unfilled positions on this plan:")
        id_to_name = {v: k for k, v in teams.items()}
        for tid, slots in needed_by_team.items():
            tot = sum(q or 0 for _, q in slots)
            print(f"  {id_to_name.get(tid, tid):<18} {tot} open: " +
                  ", ".join(f"{p}×{q}" for p, q in slots))
        print("\nRe-run with a team name to dry-run auto-schedule for it.")
        return

    team_id = teams.get(team_name) or next((v for k, v in teams.items()
                                            if k.lower() == team_name.lower()), None)
    if not team_id:
        sys.exit(f"Team {team_name!r} not found. Teams: {', '.join(teams)}")

    slots = needed_by_team.get(team_id, [])
    before = team_members_for(st_id, plan_id, team_id)
    print(f"Team: {team_name} (id {team_id})")
    print(f"Currently scheduled: {len(before)}" +
          (" — " + ", ".join(f"{n} ({p})" for n, p in before.values()) if before else ""))
    if slots:
        print("Unfilled positions auto-schedule would try to fill: " +
              ", ".join(f"{p}×{q}" for p, q in slots))
    else:
        print("No unfilled needed positions for this team — auto-schedule may be a no-op.")

    url = f"{BASE}/service_types/{st_id}/plans/{plan_id}/autoschedule"
    body = autoschedule_body(team_id)
    print(f"\nWould POST {url}")
    print("Body (UNVERIFIED — see docstring): " + json.dumps(body))

    if not apply:
        print("\n(dry-run — re-run with --apply to actually perform it)")
        return

    print("\nApplying auto-schedule...")
    r = session.post(url, json=body, headers={"Content-Type": "application/json"},
                     allow_redirects=False)
    print(f"HTTP {r.status_code}")
    if r.status_code in (301, 302, 303, 307, 308):
        print(f"  REDIRECT to {r.headers.get('Location')} — POST would downgrade to GET; "
              "use the canonical path (see ENDPOINT-DISCOVERY transport gotchas).")
        return
    body_text = r.text[:1500]
    print(body_text)
    if r.status_code not in (200, 201):
        print("\n(non-2xx — read the errors above; this reveals the real body contract. "
              "No write happened.)")
        log("AUTOSCHED_FAIL", f"{date} {team_name} [HTTP {r.status_code}]")
        return

    # Success: diff team_members to report exactly what was added (undo handle).
    after = team_members_for(st_id, plan_id, team_id)
    added = {k: v for k, v in after.items() if k not in before}
    print(f"\n✓ Auto-schedule succeeded. Added {len(added)} assignment(s) (Unconfirmed, no emails):")
    for tm_id, (n, p) in added.items():
        print(f"    + {n} → {p}   [team_member {tm_id}]")
    if added:
        print("\n  To undo: DELETE these team_members at "
              f"/service_types/{st_id}/plans/{plan_id}/team_members/<id>")
    log("AUTOSCHED", f"{date} {team_name} added {len(added)} [plan:{plan_id}]")


if __name__ == "__main__":
    main()
