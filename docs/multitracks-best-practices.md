# Making MultiTracks "Import from Planning Center" work with your own cloud uploads

If your church uploads its own stems to MultiTracks (Cloud Songs) and imports plans from
Planning Center into Playback, you have probably seen songs come in as click+pad
placeholders, in the wrong key, or at a suspicious 120 BPM. None of that is random, and
almost all of it is preventable from the Planning Center side.

These are the rules as observed through regular use of both products (as of mid-2026).
Neither product documents this interplay anywhere we could find. Behavior may change;
if something here stops matching what you see, trust what you see.

## The one-sentence model

MultiTracks matches each **Planning Center arrangement** (not just the song) to audio,
and it fills in **key and tempo from two specific Planning Center fields** — so what
imports is determined by data you control in PCO before you ever open Playback.

## Rule 1: Name cloud uploads to exactly match the PCO song title

Matching is punctuation-sensitive. "10,000 Reasons" and "10000 Reasons" are different
titles to MultiTracks — the comma matters. Pick one naming convention and use it
character-for-character in both places:

- PCO song title == MultiTracks cloud upload title
- Same commas, same parentheses, same spelling

This costs nothing at upload time and prevents the most confusing class of mismatch.

## Rule 2: Standardize each song on one PCO arrangement, and reuse it

The link between a PCO song and your cloud upload lives at the **arrangement** level.
A different arrangement of the same song — even a brand-new "Default Arrangement"
created by accident — is unlinked and will import as a click+pad placeholder.

Practical habits:

- Keep one working arrangement per song and put *that* arrangement on plans.
- Don't create new arrangements casually. If you must (new key, new cut), expect to
  redo the link for the new arrangement (Rule 3).
- If a long-linked song suddenly imports as a placeholder, the first thing to check
  is whether the plan is using a different arrangement than usual.

## Rule 3: A new upload's first import is the setup step, not a failure

MultiTracks can only link arrangements it has seen. The sequence that works for a new
cloud upload (or a new arrangement):

1. Put the song (on its standard arrangement) in a plan and **import the plan once**.
   It will come in as a placeholder — expected.
2. In MultiTracks: left nav → **Setlists → Song Link**. Find the song, expand the
   arrangement, click **Link Song**, choose the **Cloud Songs** tab, pick your upload.
3. Re-import. From now on, every future plan using that arrangement imports your
   upload automatically.

## Rule 4: Fix bad matches on the Song Link page, not in the setlist

Inside a setlist, "Edit Song" swaps the audio for *that setlist only* — the underlying
match is unchanged, so the same wrong import happens again next week. The **Song Link**
page (Setlists → Song Link) is the persistent mapping that import-matching actually
uses. Fix it there once instead of re-fixing every week.

(Third lookalike: the library's "Link Song" on a cloud upload ties it to a catalog
song for CCLI/reporting purposes. That one doesn't affect import matching either.)

## Rule 5: Set the key on the PCO plan item — blank imports as C

The key Playback requests at import comes from the **plan item's key field** in
Planning Center. If the item has no key selected, the import requests **C**, and if
your stems are in another key Playback will offer to re-render ("Click to Update") —
pitch-shifting your own recording away from itself.

Practical habits:

- Make sure each song's arrangement has its key defined (the arrangement holds the
  list of available keys; the plan item points at one of them).
- Select the key on the plan item at least once. When you add songs in the PCO web
  UI, PCO carries the last-used key forward to future plans automatically, so this
  is mostly a one-time fix per song.
- **If you create plan items via the PCO API:** the web UI auto-selects a key when
  you add a song, but a raw API-created item is born with `key: null` — exactly the
  blank that imports as C. API-built plans need the key set explicitly.

## Rule 6: Set the BPM on the PCO arrangement — blank imports as 120

The tempo comes from the **arrangement's BPM field** in Planning Center. Blank BPM
imports as 120. Note the asymmetry, because it matters when auditing:

| Imported thing | Comes from (in PCO) | If blank |
|---|---|---|
| Which audio | the arrangement's link (Rule 2/3) | click+pad placeholder |
| Key | the **plan item's** key | C |
| Tempo | the **arrangement's** BPM | 120 |

Both fields are worth a one-time audit across your song library: an hour of filling
in keys and BPMs permanently ends the "everything imports at 120 in C" era.

## Rule 7: "C at 120 BPM" is a symptom, not a bug

When an import comes in generic, it is almost never a MultiTracks malfunction. Read it
as a checklist:

- Placeholder audio → unlinked or brand-new arrangement (Rules 2–3)
- Key C → blank key on the plan item (Rule 5)
- 120 BPM → blank BPM on the arrangement (Rule 6)

All three are fixable in Planning Center, before import, by whoever builds the plans.

## Why this is in a PCO API cookbook

Every lever above is a Planning Center field — song titles, arrangements, item keys,
arrangement BPMs — which means all of it can be audited and enforced with the same
documented PCO API the rest of this repo uses: list arrangements with blank BPMs,
find plan items with no key, standardize titles. The MultiTracks side needs no API
at all; it just faithfully reflects whatever your PCO data says. Keep the PCO data
clean and the imports take care of themselves.
