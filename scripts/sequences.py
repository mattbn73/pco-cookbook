#!/usr/bin/env python3
"""Audit and seed Arrangement.sequence across the PCO song library.

The sequence (array of section names like ['Verse 1','Chorus']) is what
ProPresenter's Planning Center import uses to auto-build the slide
arrangement. Many song libraries have lyrics with parseable sections
but an empty sequence — this tool fills the gap.

Classification (per non-Z arrangement on each in-scope song):
  HAS-SEQ   — sequence already set. Never touched.
  SEEDABLE  — sequence empty, lyrics parse into ≥1 labeled section.
              Proposal generated (see rules below).
  GENERAL   — lyrics exist but have no section labels (single 'General'
              block). Skipped; needs lyric labels added in PCO UI first.
  NO-LYRICS — no lyrics at all. Skipped; flagged for awareness.

Proposal rules (marked in the report):
  [hymn]  exactly one Chorus/Refrain section + ≥2 Verses and nothing else
          except optional Tag/Ending → interleave: V1 C V2 C ... (Tag/End
          appended last).
  [order] anything else → sections once each, in lyric order.
  --plain forces [order] for everything.

Scope: songs scheduled within --years N (default 3) of today, plus
never-scheduled songs created within that window. --all widens to every
visible song. Hidden songs and Z-prefixed arrangements are always skipped.

Usage:
    python sequences.py              # dry run: audit + proposals
    python sequences.py --go         # apply proposals (writes log first)
    python sequences.py --all        # widen scope to all visible songs
    python sequences.py --plain      # lyric-order proposals only

Apply writes a before/after log to _sequence_logs/YYYY-MM-DD_HHMMSS.json
(every write was previously empty, so undo = PATCH sequence back to []).
"""
import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

SECRETS = Path.home() / "Secrets" / "pco.env"
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing PCO creds in ~/Secrets/pco.env")

BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)

DRY_RUN = "--go" not in sys.argv
ALL_SONGS = "--all" in sys.argv
PLAIN = "--plain" in sys.argv
YEARS = 3
for i, a in enumerate(sys.argv):
    if a == "--years" and i + 1 < len(sys.argv):
        YEARS = int(sys.argv[i + 1])

LOG_DIR = Path(__file__).parent / "_sequence_logs"

# ---------------------------------------------------------------------------
# Rate-limited GET (stay under 90 req / 20s)
# ---------------------------------------------------------------------------
_req_times = []

def get(url, **kwargs):
    now = time.time()
    while _req_times and now - _req_times[0] > 20:
        _req_times.pop(0)
    if len(_req_times) >= 90:
        sleep_for = 20 - (now - _req_times[0]) + 0.5
        print(f"  [rate limit] sleeping {sleep_for:.1f}s...", flush=True)
        time.sleep(sleep_for)
    r = session.get(url, **kwargs)
    _req_times.append(time.time())
    return r


def get_all(url, params=None):
    items = []
    p = dict(params or {})
    p.setdefault("per_page", 100)
    while url:
        r = get(url, params=p)
        r.raise_for_status()
        data = r.json()
        items.extend(data["data"])
        url = data.get("links", {}).get("next")
        p = {}
    return items


# ---------------------------------------------------------------------------
# Proposal logic
# ---------------------------------------------------------------------------
VERSE_RE = re.compile(r"^verse\b", re.I)
CHORUS_RE = re.compile(r"^(chorus|refrain)\b", re.I)
OUTRO_RE = re.compile(r"^(tag|ending|outro|coda)\b", re.I)

def propose(labels):
    """Return (sequence, rule) for a list of section labels in lyric order."""
    if PLAIN:
        return labels, "order"
    verses = [l for l in labels if VERSE_RE.match(l)]
    choruses = [l for l in labels if CHORUS_RE.match(l)]
    outros = [l for l in labels if OUTRO_RE.match(l)]
    other = [l for l in labels if l not in verses + choruses + outros]
    if len(choruses) == 1 and len(verses) >= 2 and not other:
        seq = []
        for v in verses:
            seq.extend([v, choruses[0]])
        seq.extend(outros)
        return seq, "hymn"
    return labels, "order"


def section_labels(sid, aid):
    r = get(f"{BASE}/songs/{sid}/arrangements/{aid}/sections")
    if r.status_code != 200:
        return None
    secs = r.json().get("data", {}).get("attributes", {}).get("sections", [])
    return [s["label"] for s in secs]


def is_z_prefixed(name):
    return bool(re.match(r"^z\d?\s|^z\d?$", name.strip(), re.I)) or name.strip().lower().startswith("z ")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * YEARS)
    print(f"{'DRY RUN — ' if DRY_RUN else ''}Fetching all songs...", flush=True)
    songs = get_all(f"{BASE}/songs")
    visible = [s for s in songs if not s["attributes"].get("hidden")]

    def in_scope(song):
        if ALL_SONGS:
            return True
        a = song["attributes"]
        stamp = a.get("last_scheduled_at") or a.get("created_at")
        if not stamp:
            return False
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")) >= cutoff

    scoped = [s for s in visible if in_scope(s)]
    print(f"  {len(songs)} total, {len(visible)} visible, "
          f"{len(scoped)} in scope ({'all' if ALL_SONGS else f'active last {YEARS}y'})\n")

    has_seq, seedable, general, no_lyrics = [], [], [], []

    for i, song in enumerate(scoped):
        sid = song["id"]
        title = song["attributes"]["title"]
        if (i + 1) % 25 == 0:
            print(f"  ...scanning song {i+1}/{len(scoped)}", flush=True)

        for arr in get_all(f"{BASE}/songs/{sid}/arrangements"):
            a = arr["attributes"]
            name = a.get("name") or ""
            if is_z_prefixed(name):
                continue
            if a.get("sequence"):
                has_seq.append((title, name))
                continue
            if not (a.get("lyrics") or "").strip():
                no_lyrics.append((title, name))
                continue
            labels = section_labels(sid, arr["id"])
            if labels is None:
                no_lyrics.append((title, name + " [sections fetch failed]"))
                continue
            real = [l for l in labels if l.lower() != "general"]
            if not real:
                general.append((title, name))
                continue
            seq, rule = propose(real)
            seedable.append({
                "song_id": sid, "song": title,
                "arrangement_id": arr["id"], "arrangement": name,
                "sections": real, "proposed_sequence": seq, "rule": rule,
            })

    # ------------------------------------------------------------------ report
    print()
    print("=" * 70)
    print(f"SEQUENCE {'AUDIT (DRY RUN)' if DRY_RUN else 'SEED PLAN'}")
    print("=" * 70)

    print(f"\nAlready set ({len(has_seq)}) — untouched")
    print(f"No lyrics ({len(no_lyrics)}) — skipped")
    print(f"Unlabeled lyrics ({len(general)}) — need section labels in PCO UI:")
    for t, n in general:
        print(f"    {t!r} / {n!r}")

    print(f"\n{'─'*70}")
    print(f"SEEDABLE ({len(seedable)}) — sequence currently empty, proposal below")
    print(f"{'─'*70}")
    for p in seedable:
        print(f"  {p['song']!r} / {p['arrangement']!r}  [{p['rule']}]")
        print(f"      → {' · '.join(p['proposed_sequence'])}")

    print(f"\nSUMMARY: {len(has_seq)} set · {len(seedable)} seedable · "
          f"{len(general)} unlabeled · {len(no_lyrics)} no-lyrics")

    if DRY_RUN:
        print("\nDry run complete. Run with --go to apply.")
        return

    if not seedable:
        print("\nNothing to apply.")
        return

    answer = input(f"\nApply {len(seedable)} sequence writes? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    log_path.write_text(json.dumps({
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "note": "all sequences below were empty before this run; undo = PATCH back to []",
        "writes": seedable,
    }, indent=2))
    print(f"Log written: {log_path}")

    errors = []
    for p in seedable:
        r = session.patch(
            f"{BASE}/songs/{p['song_id']}/arrangements/{p['arrangement_id']}",
            json={"data": {"type": "Arrangement", "id": p["arrangement_id"],
                            "attributes": {"sequence": p["proposed_sequence"]}}})
        if r.status_code == 200:
            print(f"  SET  {p['song']!r} / {p['arrangement']!r}")
        else:
            msg = f"  ERROR {r.status_code} {p['song_id']}/{p['arrangement_id']}: {r.text[:100]}"
            print(msg)
            errors.append(msg)

    print(f"\nDone. {len(seedable) - len(errors)} written, {len(errors)} error(s).")


if __name__ == "__main__":
    main()
