#!/usr/bin/env python3
"""Snapshot a PCO plan to disk so we can recover from destructive ops.

Snapshots live at `_snapshots/YYYY-MM-DD/HHMMSS_<plan_id>_<label>.json` (gitignored,
local-only). Each file = plan metadata + full item list with song/arrangement/key
relationship IDs preserved, so a snapshot is sufficient to reconstruct the plan via
POST calls if needed.

Default retention: 30 days. Anything older is auto-pruned on each new snapshot.

USAGE — module:
    from snapshot import snapshot_plan, prune_old
    snapshot_plan(session, st_id, plan_id, label="pre-cut", items=preloaded)

USAGE — CLI:
    python snapshot.py <st_id> <plan_id> [label]    # snapshot one plan
    python snapshot.py --prune                       # just prune old

WHEN TO CALL (the rule):
    Before any DELETE on an item, or any PATCH that changes plan title / structure,
    snapshot every affected plan ONCE at the start of the batch. Reuse preloaded
    items if you already have them — no need for an extra GET.
"""
import os, sys, json, datetime, re
from pathlib import Path
from dotenv import load_dotenv
import requests

SECRETS = Path.home() / "Secrets" / "pco.env"
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")

BASE = "https://api.planningcenteronline.com/services/v2"

# Snapshots go at the project root (this file's directory)
SNAP_ROOT = Path(__file__).resolve().parent / "_snapshots"
RETENTION_DAYS = 30


def _session():
    s = requests.Session()
    s.auth = (CID, SEC)
    return s


def _safe_label(s: str) -> str:
    """Sanitize an arbitrary string into a filename-safe slug."""
    s = re.sub(r"[^\w\-]+", "-", s.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:50] or "snap")


def snapshot_plan(session, st_id, plan_id, label="snap", items=None, plan_meta=None,
                  reason=None):
    """Write a snapshot for one plan.

    Args:
        session: a requests.Session with PCO auth (or None — will build one)
        st_id, plan_id: PCO IDs
        label: short slug for the filename ("pre-cut", "pre-batch", etc.)
        items: pre-loaded items list (raw JSON:API dicts with relationships). If None,
               will GET them with include=song,arrangement,key.
        plan_meta: pre-loaded plan dict. If None, will GET.
        reason: free-text note saved inside the snapshot file (one line)
    Returns:
        Path to the written file.
    """
    s = session or _session()

    if plan_meta is None:
        r = s.get(f"{BASE}/service_types/{st_id}/plans/{plan_id}")
        r.raise_for_status()
        plan_meta = r.json()["data"]

    if items is None:
        r = s.get(f"{BASE}/service_types/{st_id}/plans/{plan_id}/items",
                  params={"include": "song,arrangement,key", "per_page": 100})
        r.raise_for_status()
        items = r.json()["data"]

    now = datetime.datetime.now()
    day_dir = SNAP_ROOT / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{now.strftime('%H%M%S')}_{plan_id}_{_safe_label(label)}.json"
    fpath = day_dir / fname

    payload = {
        "snapshot_taken_at": now.isoformat(timespec="seconds"),
        "service_type_id": str(st_id),
        "plan_id": str(plan_id),
        "label": label,
        "reason": reason,
        "plan": {
            "id": plan_meta.get("id"),
            "attributes": plan_meta.get("attributes", {}),
        },
        "items": [
            {
                "id": it.get("id"),
                "attributes": it.get("attributes", {}),
                "relationships": {
                    rk: {"data": rv.get("data")}
                    for rk, rv in it.get("relationships", {}).items()
                    if rv.get("data") is not None
                },
            }
            for it in items
        ],
    }
    fpath.write_text(json.dumps(payload, indent=2))

    # Prune as a side-effect of writing — keeps the store self-maintaining
    prune_old(RETENTION_DAYS)
    return fpath


def prune_old(days=RETENTION_DAYS):
    """Delete snapshot files older than `days`. Also removes empty day-dirs."""
    if not SNAP_ROOT.exists():
        return 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    removed = 0
    for day_dir in SNAP_ROOT.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            day_date = datetime.datetime.strptime(day_dir.name, "%Y-%m-%d")
        except ValueError:
            continue
        if day_date >= cutoff:
            continue
        for f in day_dir.iterdir():
            f.unlink()
            removed += 1
        try:
            day_dir.rmdir()
        except OSError:
            pass
    return removed


def latest_snapshot_for(plan_id):
    """Return Path of most recent snapshot for a plan, or None."""
    if not SNAP_ROOT.exists():
        return None
    candidates = []
    for day_dir in SNAP_ROOT.iterdir():
        if not day_dir.is_dir():
            continue
        for f in day_dir.glob(f"*_{plan_id}_*.json"):
            candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--prune" in sys.argv and not args:
        n = prune_old()
        print(f"Pruned {n} old snapshot files (older than {RETENTION_DAYS} days).")
        return
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    st_id, plan_id = args[0], args[1]
    label = args[2] if len(args) > 2 else "manual"
    s = _session()
    fpath = snapshot_plan(s, st_id, plan_id, label=label, reason="manual CLI snapshot")
    print(f"Wrote {fpath}")


if __name__ == "__main__":
    main()
