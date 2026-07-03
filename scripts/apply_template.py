"""Apply a registered service template to an EXISTING plan in ONE call.

Generalized from Sunday-AM-only to any handle in service_registry. Uses PCO's native
`import` action:
    POST /service_types/{st}/plans/{plan_id}/import
    attributes: source_id, copy_items, copy_people, copy_notes

`copy_people` brings BOTH team members AND needed positions. People come in at whatever
status the source holds (the template stores them Unconfirmed). Returns a PlanImportMetadata
(flags e.g. missing background checks).

The template id + service type come from service_registry.py — re-point a master there, not
here. The `import_template()` helper is the shared import path; book_service.py calls it too.

History: PCO auto-creates the dated plan SHELL, and the old `import_template` 404'd on
existing plans, so booking a shell used to mean copying items + needed positions + people one
POST at a time (and tripping over the `/plans/{id}/items` 302→GET downgrade and the
team_position-id-not-name 422). PCO un-hid this `import` action on 2026-06-22 (issue
planningcenter/developers #1479); it replaces that entire workaround. The gotchas are still
recorded in ENDPOINT-DISCOVERY.md for any code that POSTs plan items directly.

Usage:
    python apply_template.py [handle] <plan_id> [--no-items] [--no-people] [--no-notes] [--apply]
    # handle defaults to sunday_am (back-compat); copies items + people(+needed positions)
    # + notes; dry-run unless --apply
"""
import os
import sys
import json

import requests
from dotenv import load_dotenv

import service_registry as reg

load_dotenv(os.path.expanduser("~/Secrets/pco.env"))
B = "https://api.planningcenteronline.com/services/v2"

session = requests.Session()
session.auth = (os.environ["PCO_CLIENT_ID"], os.environ["PCO_SECRET"])


def import_template(st_id, plan_id, template_id,
                    copy_items=True, copy_people=True, copy_notes=True, sess=None):
    """POST the native import action. Returns the requests.Response."""
    s = sess or session
    attrs = {"source_id": int(template_id),
             "copy_items": copy_items, "copy_people": copy_people, "copy_notes": copy_notes}
    return s.post(f"{B}/service_types/{st_id}/plans/{plan_id}/import",
                  json={"data": {"attributes": attrs}})


def main():
    args = sys.argv[1:]
    plan = next((a for a in args if a.isdigit()), None)
    handle_arg = next((a for a in args
                       if not a.startswith("--") and not a.isdigit()), None)
    if not plan:
        sys.exit("usage: python apply_template.py [handle] <plan_id> "
                 "[--no-items] [--no-people] [--no-notes] [--apply]")
    try:
        handle, svc = reg.resolve(handle_arg or "sunday_am")
    except KeyError as e:
        sys.exit(str(e))

    apply = "--apply" in args
    ci, cp, cn = ("--no-items" not in args, "--no-people" not in args,
                  "--no-notes" not in args)
    print(f"{'APPLY' if apply else 'DRY-RUN'} — import {handle} template "
          f"{svc['template_id']} ({svc['template_name']}) -> plan {plan}")
    print("  " + json.dumps({"copy_items": ci, "copy_people": cp, "copy_notes": cn}))
    if not apply:
        print("\n(dry-run — re-run with --apply to import)")
        return

    r = import_template(svc["service_type_id"], plan, svc["template_id"], ci, cp, cn)
    print(f"\nimport: HTTP {r.status_code}")
    if r.status_code in (200, 201):
        meta = r.json().get("data", {}).get("attributes", {})
        print("  PlanImportMetadata:", json.dumps(meta))
        if meta.get("any_plan_people_missing_background_check"):
            print("  ⚠️ some imported people are missing a required background check")
        print("  done — items + needed positions + people (+notes) copied in.")
    else:
        print("  FAILED:", r.text[:300])


if __name__ == "__main__":
    main()
