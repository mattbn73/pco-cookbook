#!/usr/bin/env python3
"""Find duplicate songs in PCO.

Steps:
  1. Fetch all songs from PCO
  2. Group by CCLI number -> definite duplicates
  3. Fuzzy-match titles among remaining songs -> probable duplicates
  4. For songs in any dupe pair, fetch arrangements to show richness signals
  5. Print a report

Usage:
    python dedup_songs.py              # default fuzzy threshold: 90
    python dedup_songs.py 85           # lower threshold = more candidates
"""
import os, sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from rapidfuzz import fuzz
from collections import defaultdict

SECRETS = Path.home() / "Secrets" / "pco.env"
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing PCO creds")

BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)

FUZZY_THRESHOLD = int(sys.argv[1]) if len(sys.argv) > 1 else 90


def get_all_songs():
    songs = []
    url = f"{BASE}/songs"
    params = {"per_page": 100}
    while url:
        r = session.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        songs.extend(data["data"])
        url = data.get("links", {}).get("next")
        params = {}
    return songs


def fetch_arrangement_signals(song_ids):
    """For a set of song IDs, fetch arrangements and return richness signals.

    Returns dict: song_id -> {"arr_count": int, "has_chord_chart": bool, "has_lyrics": bool}
    """
    signals = {}
    for sid in song_ids:
        arrs = []
        url = f"{BASE}/songs/{sid}/arrangements"
        params = {"per_page": 100}
        while url:
            r = session.get(url, params=params)
            if r.status_code != 200:
                break
            data = r.json()
            arrs.extend(data["data"])
            url = data.get("links", {}).get("next")
            params = {}
        signals[sid] = {
            "arr_count": len(arrs),
            "has_chord_chart": any(a["attributes"].get("has_chord_chart") for a in arrs),
            "has_lyrics": any(a["attributes"].get("lyrics") for a in arrs),
        }
    return signals


def fmt(song, signals=None):
    a = song["attributes"]
    ccli = a.get("ccli_number") or "no CCLI"
    last = a.get("last_scheduled_short_dates") or "never scheduled"
    hidden = " [hidden]" if a.get("hidden") else ""
    sig = ""
    if signals:
        s = signals.get(song["id"])
        if s:
            parts = [f"{s['arr_count']} arr"]
            if s["has_chord_chart"]:
                parts.append("chords")
            if s["has_lyrics"]:
                parts.append("lyrics")
            sig = f"  [{', '.join(parts)}]"
    return f"  [{song['id']}] '{a['title']}' by {a.get('author') or '?'}  (CCLI: {ccli}, last used: {last}){sig}{hidden}"


def main():
    print("Fetching songs...", flush=True)
    songs = get_all_songs()
    print(f"  {len(songs)} songs loaded\n")

    # --- Step 1: group by CCLI ---
    by_ccli = defaultdict(list)
    no_ccli = []
    for s in songs:
        ccli = s["attributes"].get("ccli_number")
        if ccli:
            by_ccli[ccli].append(s)
        else:
            no_ccli.append(s)

    ccli_dupes = {k: v for k, v in by_ccli.items() if len(v) > 1}

    # --- Step 2: fuzzy match titles ---
    candidates = no_ccli + [v[0] for v in by_ccli.values()]  # one rep per CCLI group

    def norm(title):
        return title.lower().strip()

    fuzzy_pairs = []
    seen = set()
    for i, s1 in enumerate(candidates):
        for j, s2 in enumerate(candidates):
            if j <= i:
                continue
            pair_key = tuple(sorted([s1["id"], s2["id"]]))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            t1 = norm(s1["attributes"]["title"])
            t2 = norm(s2["attributes"]["title"])
            score = fuzz.token_sort_ratio(t1, t2)
            if score >= FUZZY_THRESHOLD:
                fuzzy_pairs.append((score, s1, s2))

    fuzzy_pairs.sort(key=lambda x: -x[0])

    # --- Step 3: enrich duped songs with arrangement signals ---
    duped_ids = set()
    for group in ccli_dupes.values():
        for s in group:
            duped_ids.add(s["id"])
    for _, s1, s2 in fuzzy_pairs:
        duped_ids.add(s1["id"])
        duped_ids.add(s2["id"])

    signals = {}
    if duped_ids:
        print(f"Fetching arrangement signals for {len(duped_ids)} duped songs...", flush=True)
        signals = fetch_arrangement_signals(duped_ids)
        print()

    print(f"=== DEFINITE DUPLICATES (same CCLI number): {len(ccli_dupes)} groups ===\n")
    if ccli_dupes:
        for ccli, group in sorted(ccli_dupes.items(), key=lambda x: -len(x[1])):
            print(f"  CCLI {ccli}  ({len(group)} entries):")
            for s in group:
                print(fmt(s, signals))
            print()
    else:
        print("  None found.\n")

    print(f"=== PROBABLE DUPLICATES (fuzzy title match >= {FUZZY_THRESHOLD}): {len(fuzzy_pairs)} pairs ===\n")
    if fuzzy_pairs:
        for score, s1, s2 in fuzzy_pairs:
            print(f"  Similarity: {score}%")
            print(fmt(s1, signals))
            print(fmt(s2, signals))
            print()
    else:
        print("  None found.\n")

    print(f"--- Summary ---")
    print(f"  Total songs:              {len(songs)}")
    print(f"  Songs with no CCLI:       {len(no_ccli)}")
    print(f"  CCLI duplicate groups:    {len(ccli_dupes)}")
    print(f"  Fuzzy title pairs (>={FUZZY_THRESHOLD}%): {len(fuzzy_pairs)}")


if __name__ == "__main__":
    main()
