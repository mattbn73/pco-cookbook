#!/usr/bin/env python3
"""Merge a duplicate PCO song (loser) into the canonical one (keeper).

What this does:
  1. Classifies each loser arrangement as local or SS-managed:
       local      = has chord_chart text OR any AttachmentS3 file
       SS-managed = only AttachmentChart::* (Song Select content, no local data)
  2. Copies local arrangements from loser → keeper (" (from merge)" appended to name)
       - Copies: chord_chart, chord_chart_key, bpm, meter, sequence
       - NOTE: lyrics field is read-only (Song Select managed); copy manually if needed
  3. Skips SS-managed-only arrangements (they disappear with the hidden loser — no loss)
  4. Copies ccli_number / author / copyright / admin from loser → keeper if keeper lacks them
  5. Hides the loser and renames it to  ~MERGED→{keeper_title} [{loser_id}]

Usage:
    python merge_songs.py <keeper_id> <loser_id>
"""
import os, sys
import requests
from pathlib import Path
from dotenv import load_dotenv

SECRETS = Path.home() / "Secrets" / "pco.env"
load_dotenv(dotenv_path=SECRETS)
CID, SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not CID or not SEC:
    sys.exit("Missing PCO creds")

BASE = "https://api.planningcenteronline.com/services/v2"
session = requests.Session()
session.auth = (CID, SEC)


def get_song(song_id):
    r = session.get(f"{BASE}/songs/{song_id}")
    if r.status_code == 404:
        sys.exit(f"Song {song_id} not found")
    r.raise_for_status()
    return r.json()["data"]


def get_arrangements(song_id):
    arrs = []
    url = f"{BASE}/songs/{song_id}/arrangements"
    params = {"per_page": 100}
    while url:
        r = session.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        arrs.extend(data["data"])
        url = data.get("links", {}).get("next")
        params = {}
    return arrs


def get_attachment_types(song_id, arr_id):
    r = session.get(f"{BASE}/songs/{song_id}/arrangements/{arr_id}/attachments",
                    params={"per_page": 50})
    if r.status_code != 200:
        return []
    return [a["attributes"]["pco_type"] for a in r.json()["data"]]


def is_local(arr, att_types):
    """True if the arrangement has any locally authored content."""
    has_chord_text = bool((arr["attributes"].get("chord_chart") or "").strip())
    has_s3 = "AttachmentS3" in att_types
    return has_chord_text or has_s3


def copy_arrangement(keeper_id, arr):
    a = arr["attributes"]
    name = a["name"] + " (from merge)"

    r = session.post(f"{BASE}/songs/{keeper_id}/arrangements", json={
        "data": {"type": "Arrangement", "attributes": {"name": name}}
    })
    r.raise_for_status()
    new_id = r.json()["data"]["id"]

    attrs = {}
    if a.get("chord_chart") and a.get("chord_chart_key"):
        attrs["chord_chart"] = a["chord_chart"]
        attrs["chord_chart_key"] = a["chord_chart_key"]
    elif a.get("chord_chart_key"):
        attrs["chord_chart_key"] = a["chord_chart_key"]
    if a.get("bpm") is not None:
        attrs["bpm"] = a["bpm"]
    if a.get("meter"):
        attrs["meter"] = a["meter"]
    if a.get("sequence"):
        attrs["sequence"] = a["sequence"]

    if attrs:
        r2 = session.patch(f"{BASE}/songs/{keeper_id}/arrangements/{new_id}", json={
            "data": {"type": "Arrangement", "id": new_id, "attributes": attrs}
        })
        r2.raise_for_status()

    return new_id, name


def patch_song(song_id, **attrs):
    sid = str(song_id)
    r = session.patch(f"{BASE}/songs/{sid}", json={
        "data": {"type": "Song", "id": sid, "attributes": attrs}
    })
    r.raise_for_status()


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python merge_songs.py <keeper_id> <loser_id>")

    keeper_id, loser_id = sys.argv[1], sys.argv[2]
    if keeper_id == loser_id:
        sys.exit("keeper and loser must be different songs")

    keeper = get_song(keeper_id)
    loser = get_song(loser_id)
    ka = keeper["attributes"]
    la = loser["attributes"]
    keeper_title = ka["title"]
    loser_title = la["title"]

    print("Fetching loser arrangements...", flush=True)
    loser_arrs = get_arrangements(loser_id)

    # Classify each arrangement
    classified = []
    for arr in loser_arrs:
        att_types = get_attachment_types(loser_id, arr["id"])
        local = is_local(arr, att_types)
        classified.append((arr, att_types, local))

    # Determine which metadata fields to carry over from loser → keeper
    metadata_patches = {}
    for field in ["ccli_number", "author", "copyright", "admin"]:
        if not ka.get(field) and la.get(field):
            metadata_patches[field] = la[field]

    audit_name = f"~MERGED→{keeper_title} [{loser_id}]"

    # --- Dry run ---
    print()
    print("=" * 60)
    print("DRY RUN — no changes made yet")
    print("=" * 60)
    print(f"\nKEEPER  [{keeper_id}]  {keeper_title}")
    print(f"LOSER   [{loser_id}]  {loser_title}")

    local_arrs = [(arr, att) for arr, att, local in classified if local]
    ss_arrs = [(arr, att) for arr, att, local in classified if not local]

    print(f"\nLoser arrangements ({len(loser_arrs)} total):")
    for arr, att_types, local in classified:
        a = arr["attributes"]
        has_lyrics = bool(a.get("lyrics"))
        label = "LOCAL" if local else "SS-MANAGED"
        action = f"→ copy as '{a['name']} (from merge)'" if local else "→ skip (SS-managed only)"
        lyric_note = "  [lyrics not copyable via API — copy manually if needed]" if local and has_lyrics else ""
        print(f"  [{label}]  '{a['name']}'{lyric_note}")
        print(f"           {action}")

    if not loser_arrs:
        print("  (none)")

    if metadata_patches:
        print(f"\nMetadata to copy to keeper (keeper currently blank, loser has values):")
        for field, val in metadata_patches.items():
            print(f"  {field}: {val!r}")
    else:
        print("\nMetadata: keeper already has all fields — nothing to copy.")

    print(f"\nLoser will be: hidden=True, title={audit_name!r}")
    print()

    if not local_arrs and not metadata_patches:
        print("Nothing to copy — only SS-managed arrangements and no missing metadata.")
        answer = input("Still proceed with hiding/renaming the loser? [y/N] ").strip().lower()
    else:
        answer = input("Proceed? [y/N] ").strip().lower()

    if answer != "y":
        print("Aborted.")
        return

    print()

    # Copy local arrangements
    for arr, _ in local_arrs:
        new_id, new_name = copy_arrangement(keeper_id, arr)
        has_lyrics = bool(arr["attributes"].get("lyrics"))
        note = "  [lyrics NOT copied — API limitation]" if has_lyrics else ""
        print(f"  Copied '{arr['attributes']['name']}' → '{new_name}' (id {new_id}){note}")

    if ss_arrs:
        print(f"  Skipped {len(ss_arrs)} SS-managed arrangement(s).")

    # Patch keeper metadata
    if metadata_patches:
        patch_song(keeper_id, **metadata_patches)
        for field, val in metadata_patches.items():
            print(f"  Keeper {field} set to: {val!r}")

    # Hide and rename loser
    patch_song(loser_id, hidden=True, title=audit_name)
    print(f"\nLoser hidden and renamed to: {audit_name!r}")
    print("\nDone.")


if __name__ == "__main__":
    main()
