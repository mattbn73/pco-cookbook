#!/usr/bin/env python3
"""Print the next upcoming service plan for each service type:
when it is, who's scheduled, and the running order."""
import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv

SECRETS = Path.home() / "Secrets" / "pco.env"
if not SECRETS.exists():
    sys.exit("No secrets file")
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing creds")

BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)


def get(path, **params):
    r = session.get(path if path.startswith("http") else BASE + path, params=params)
    r.raise_for_status()
    return r.json()


def included_map(payload):
    """index of (type, id) -> resource, for resolving relationships."""
    return {(x["type"], x["id"]): x for x in payload.get("included", [])}


def main():
    needle = " ".join(sys.argv[1:]).strip().lower()
    service_types = get("/service_types", per_page=100)["data"]
    if not service_types:
        print("No service types found.")
        return

    if needle:
        matches = [st for st in service_types
                   if needle in st["attributes"]["name"].lower()]
        if not matches:
            names = ", ".join(st["attributes"]["name"] for st in service_types)
            sys.exit(f"No service type matching {needle!r}. Available: {names}")
        service_types = matches

    for st in service_types:
        st_id = st["id"]
        st_name = st["attributes"]["name"]
        print(f"\n{'=' * 60}\n{st_name}\n{'=' * 60}")

        plans = get(f"/service_types/{st_id}/plans",
                    filter="future", order="sort_date", per_page=1)["data"]
        if not plans:
            print("  (no upcoming plans)")
            continue

        plan = plans[0]
        pid = plan["id"]
        a = plan["attributes"]
        when = a.get("dates") or a.get("sort_date") or "?"
        title = a.get("title") or a.get("series_title") or "(untitled)"
        print(f"  Next: {when}  —  {title}")

        # Who's scheduled
        tm = get(f"/service_types/{st_id}/plans/{pid}/team_members", include="team", per_page=100)
        teams = included_map(tm)
        if tm["data"]:
            print("\n  Scheduled:")
            for m in tm["data"]:
                ma = m["attributes"]
                name = ma.get("name", "?")
                pos = ma.get("team_position_name", "")
                status = ma.get("status", "")
                team_rel = m.get("relationships", {}).get("team", {}).get("data")
                team_name = ""
                if team_rel:
                    t = teams.get((team_rel["type"], team_rel["id"]))
                    if t:
                        team_name = t["attributes"].get("name", "")
                line = f"    - {name}"
                if pos:
                    line += f" — {pos}"
                if team_name and team_name != pos:
                    line += f" ({team_name})"
                if status and status != "C":
                    line += f"  [{status}]"
                print(line)
        else:
            print("\n  Scheduled: (nobody yet)")

        # Running order
        items = get(f"/service_types/{st_id}/plans/{pid}/items", per_page=100)["data"]
        if items:
            print("\n  Running order:")
            for it in items:
                ia = it["attributes"]
                t = ia.get("title") or "(no title)"
                kind = ia.get("item_type", "")
                key = ia.get("key_name") or ""
                mark = "  ♪" if kind == "song" else ""
                suffix = f"  [{key}]" if key else ""
                print(f"    {ia.get('sequence', '?'):>3}. {t}{suffix}{mark}")
        else:
            print("\n  Running order: (empty)")


if __name__ == "__main__":
    main()
