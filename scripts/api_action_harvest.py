#!/usr/bin/env python3
"""Preemptive endpoint-gap finder for PCO Services.

Every PCO object ships a `links` map listing the actions/related endpoints it
supports (create_plans, item_reorder, time_preference_options, import, ...).
This harvests that map across one representative object of each major type, then
greps our own scripts to flag which advertised actions we have NEVER called.

The leftovers = the "UI does this, we don't yet" list — Category-A cascades and
action endpoints we haven't mapped to a use-case. (It does NOT find Category-B
derived fields or Category-C guardrails — those aren't links; see crosswalk doc.)

Usage: api_action_harvest.py [service_type_id]        # print the gap table
       api_action_harvest.py [service_type_id] --md   # emit a markdown table to stdout
"""
import os, sys, glob, re, requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Secrets/pco.env"))
B = "https://api.planningcenteronline.com/services/v2"
S = requests.Session(); S.auth = (os.environ["PCO_CLIENT_ID"], os.environ["PCO_SECRET"])
MD = "--md" in sys.argv

def g(path):
    r = S.get(path if path.startswith("http") else B + path)
    r.raise_for_status(); return r.json()

def first_id(path):
    data = g(path).get("data", [])
    return data[0]["id"] if data else None

# --- self-bootstrap: discover one representative object per type ---
# Any active service type works — put YOUR service type ID here (it's in the PCO web
# URL when you open the service type), or pass it as the first CLI argument.
ST = "1111111"  # your service type ID here
_cli_ids = [a for a in sys.argv[1:] if a.isdigit()]
if _cli_ids:
    ST = _cli_ids[0]
plan = first_id(f"/service_types/{ST}/plans?per_page=1&order=-sort_date")
item = first_id(f"/service_types/{ST}/plans/{plan}/items?per_page=1") if plan else None
song = first_id("/songs?per_page=1")
arr  = first_id(f"/songs/{song}/arrangements?per_page=1") if song else None
team = first_id(f"/service_types/{ST}/teams?per_page=1")
person = first_id("/people?per_page=1")
tmpl = first_id(f"/service_types/{ST}/plan_templates?per_page=1")

TARGETS = {
    "Organization (root)": "/",
    "ServiceType":         f"/service_types/{ST}",
    "Plan":                f"/service_types/{ST}/plans/{plan}" if plan else None,
    "Item":                f"/service_types/{ST}/plans/{plan}/items/{item}" if item else None,
    "Song":                f"/songs/{song}" if song else None,
    "Arrangement":         f"/songs/{song}/arrangements/{arr}" if (song and arr) else None,
    "Team":                f"/service_types/{ST}/teams/{team}" if team else None,
    "Person":              f"/people/{person}" if person else None,
    "PlanTemplate":        f"/service_types/{ST}/plan_templates/{tmpl}" if tmpl else None,
}

# --- what do OUR scripts already reference? (grep all .py for the link key) ---
corpus = ""
for f in glob.glob(os.path.join(os.path.dirname(__file__), "*.py")):
    if os.path.basename(f) == os.path.basename(__file__):
        continue
    try: corpus += open(f, encoding="utf-8", errors="ignore").read()
    except OSError: pass

def used(action):
    # action endpoints (create_plans, item_reorder) vs plain related collections.
    return bool(re.search(rf"\b{re.escape(action)}\b", corpus))

# nav links every object has — not interesting as "actions"
BORING = {"self", "html"}

rows = []
for tname, path in TARGETS.items():
    if not path:
        rows.append((tname, "(no sample object found)", "", "")); continue
    links = (g(path).get("data", {}) or {}).get("links", {}) or {}
    def href(v):
        if isinstance(v, dict): v = v.get("href")
        return (v or "").split("/services/v2")[-1]
    actions = sorted(k for k in links if k not in BORING)
    for a in actions:
        rows.append((tname, a, "✓" if used(a) else "—  GAP", href(links[a])))

if MD:
    print("| Object | Advertised action | We use it? | Path |")
    print("|---|---|---|---|")
    last = None
    for t, a, u, p in rows:
        print(f"| {t if t!=last else ''} | `{a}` | {u} | `{p}` |"); last = t
else:
    last = None
    for t, a, u, p in rows:
        head = t if t != last else ""
        print(f"{head:22} {u:8} {a:28} {p}"); last = t
    gaps = [r for r in rows if r[2].startswith("—")]
    print(f"\n{len(gaps)} advertised actions with no reference in our scripts (candidate gaps).")
