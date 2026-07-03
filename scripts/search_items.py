#!/usr/bin/env python3
"""Search plan items (titles and headers) in one service type for a keyword.

Usage:
  python search_items.py dedication
  python search_items.py "baby dedication"
  python search_items.py dedication --years 3
  python search_items.py dedication --years 5
"""
import os, sys, time, requests
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

SECRETS = Path.home() / "Secrets" / "pco.env"
if not SECRETS.exists():
    sys.exit("No secrets file")
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing creds")

# The service type to search — set to your service type's exact name as it appears
# in PCO (or override with the SERVICE_TYPE_NAME environment variable).
SERVICE_TYPE_NAME = os.getenv("SERVICE_TYPE_NAME", "Sunday AM")
BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)


def get(path, **params):
    r = session.get(path if path.startswith("http") else BASE + path, params=params)
    r.raise_for_status()
    return r.json()


def get_all_pages(path, **params):
    """Fetch every page and return combined list of data."""
    results = []
    params.setdefault("per_page", 100)
    url = BASE + path
    while url:
        for attempt in range(5):
            r = session.get(url, params=params)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10))
                print(f"  [rate limited, waiting {wait}s]")
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        payload = r.json()
        results.extend(payload["data"])
        url = payload.get("links", {}).get("next")
        params = {}  # next link already includes params
    return results


def main():
    # Parse args
    args = sys.argv[1:]
    years = 3
    if "--years" in args:
        i = args.index("--years")
        years = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if not args:
        sys.exit("Usage: python search_items.py <keyword> [--years N]")
    keyword = " ".join(args).lower()

    since = (date.today() - timedelta(days=years * 365)).isoformat()
    print(f"Searching {SERVICE_TYPE_NAME} plans from {since} onward for: {keyword!r}\n")

    # Find service type
    service_types = get("/service_types", per_page=100)["data"]
    st = next((s for s in service_types
               if s["attributes"]["name"].strip().lower() == SERVICE_TYPE_NAME.lower()), None)
    if not st:
        sys.exit(f"Service type {SERVICE_TYPE_NAME!r} not found.")
    st_id = st["id"]

    # Fetch all plans in the date range (past only)
    plans = get_all_pages(
        f"/service_types/{st_id}/plans",
        filter="past",
        order="sort_date",
        **{"where[sort_date][gte]": since},
    )
    print(f"Found {len(plans)} plans to scan...")

    hits = []
    for i, plan in enumerate(plans, 1):
        pid = plan["id"]
        pa = plan["attributes"]
        plan_date = pa.get("dates") or pa.get("sort_date") or "?"
        plan_title = pa.get("title") or pa.get("series_title") or ""

        # Fetch items for this plan (small delay to stay under rate limit)
        time.sleep(0.25)
        items = get_all_pages(f"/service_types/{st_id}/plans/{pid}/items")

        for item in items:
            ia = item["attributes"]
            item_title = ia.get("title") or ""
            item_desc = ia.get("description") or ""
            item_type = ia.get("item_type") or ""

            # Search title and description
            if keyword in item_title.lower() or keyword in item_desc.lower():
                hits.append({
                    "date": plan_date,
                    "plan_title": plan_title,
                    "item_type": item_type,
                    "item_title": item_title,
                })

        # Progress indicator every 25 plans
        if i % 25 == 0:
            print(f"  ...scanned {i}/{len(plans)} plans")

    print(f"\n{'=' * 60}")
    print(f"Results: {len(hits)} match(es) for {keyword!r}")
    print(f"{'=' * 60}\n")

    if not hits:
        print("No matches found.")
    else:
        for h in hits:
            label = f"[{h['item_type']}]" if h["item_type"] else ""
            plan_info = f" — plan: {h['plan_title']}" if h["plan_title"] else ""
            print(f"  {h['date']}{plan_info}")
            print(f"    {label} {h['item_title']}")
            print()


if __name__ == "__main__":
    main()
