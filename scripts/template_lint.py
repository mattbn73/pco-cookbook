"""Lint the service templates for people who shouldn't ride along on copies.

ONE actionable check: name on the removed/deceased list (removed_people.json) — someone who
should be gone entirely but is still parked on the template. These get a delete path.

Declined (status 'D') is NOT a finding — it's normal and useful. `copy_people` imports each
person at the template's stored status, Declined included, so a declined person shows up
declined on every booked plan with no action: an inherited visual marker (and a hint about who
regularly declines). The lint just reports the count as an FYI.

Read-only. Run before any template-based booking.

removed_people.json lives next to this script and is not checked in — create your own.
Expected format: names as they appear in PCO, mapped to a one-line reason:
    {"removed": {"Jane Smith": "moved away 2024", "John Doe": "deceased 2023"}}

Usage:
    python template_lint.py            # lint all registered templates
    python template_lint.py wed_choir  # just one handle
"""
import os
import sys
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

import service_registry as reg

load_dotenv(os.path.expanduser("~/Secrets/pco.env"))
B = "https://api.planningcenteronline.com/services/v2"

session = requests.Session()
session.auth = (os.environ["PCO_CLIENT_ID"], os.environ["PCO_SECRET"])

REMOVED = json.loads((Path(__file__).resolve().parent / "removed_people.json").read_text())["removed"]


def template_people(st_id, tid):
    """Yield (member_id, name, status, team, position) for a template's team_members."""
    r = session.get(f"{B}/service_types/{st_id}/plan_templates/{tid}/team_members",
                    params={"include": "team,team_position", "per_page": 100})
    r.raise_for_status()
    j = r.json()
    inc = {(o["type"], o["id"]): o["attributes"] for o in j.get("included", [])}
    for pp in j.get("data", []):
        a = pp["attributes"]
        rel = pp.get("relationships", {})
        tid_ = (rel.get("team", {}).get("data") or {}).get("id")
        pos = (rel.get("team_position", {}).get("data") or {})
        team = inc.get(("Team", tid_), {}).get("name") if tid_ else None
        position = (inc.get(("TeamPosition", pos.get("id")), {}).get("name") if pos else None) \
            or a.get("team_position_name")
        yield pp["id"], (a.get("name") or a.get("full_name")), a.get("status"), team, position


def lint_template(handle, svc):
    st_id, tid = svc["service_type_id"], svc["template_id"]
    findings = []        # actionable: on the removed list
    declined = []        # informational only
    for member_id, name, status, team, position in template_people(st_id, tid):
        if name in REMOVED:
            findings.append((name, status, team, position, member_id))
        elif status == "D":
            declined.append(name)
    print(f"\n=== {handle}  template {tid} ({svc['template_name']}) ===")
    if findings:
        for name, status, team, position, member_id in findings:
            print(f"  ⚠ REMOVE {name}  [{status}]  {team} / {position}")
            print(f"       on removed list — {REMOVED[name]}")
            print(f"       delete: DELETE /service_types/{st_id}/plan_templates/{tid}"
                  f"/team_members/{member_id}")
    else:
        print("  ✅ no removed-list people")
    if declined:
        print(f"  ℹ {len(declined)} declined (normal — imports as a visual marker): "
              f"{', '.join(declined)}")
    return findings


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        try:
            handle, svc = reg.resolve(args[0])
        except KeyError as e:
            sys.exit(str(e))
        targets = {handle: svc}
    else:
        targets = reg.SERVICES

    total = 0
    for handle, svc in targets.items():
        total += len(lint_template(handle, svc))
    print(f"\n{total} finding(s) across {len(targets)} template(s).")


if __name__ == "__main__":
    main()
