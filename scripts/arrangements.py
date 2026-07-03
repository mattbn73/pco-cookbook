"""Pick the right arrangement when booking a song into a plan.

PCO has **no "default arrangement" flag**. The bare `/songs/{id}/arrangements`
endpoint returns arrangements in creation order (oldest first), so a naive
`arrangements[0]` grabs whatever was made first — which is how a deliberately
buried `zCAPO` arrangement can win the pick over the real, current one.

Preference order (first that yields a result wins):

  1. **last-used** — the arrangement most recently used for this song in a real
     plan, if the caller supplies its name (e.g. from a recent-plans scan).
     "What we actually sang last time" is the strongest signal and supersedes
     the Z rule — if we deliberately used a zCAPO last time, keep it.
  2. **first non-buried** — the first arrangement whose name does NOT start with
     a leading 'z'/'Z'. A leading Z is the library's deliberate "sink this
     in the UI" marker; the booking logic mirrors that visual burying.
  3. **fallback** — the first arrangement, even if buried, when that's all there is.

Pure functions over a list of `{"id","name"}` dicts so they're trivially
testable; callers fetch the arrangements and (optionally) pass the last-used name.
"""


def is_buried(name):
    """A leading 'z'/'Z' marks an arrangement as deliberately buried."""
    return bool(name) and name.strip().lower().startswith("z")


def pick(arrangements, last_used_name=None):
    """Return the chosen arrangement dict (or None if the list is empty).

    `arrangements`: list of {"id": str, "name": str} in PCO API order.
    `last_used_name`: arrangement name most recently used for this song, if known.
    """
    if not arrangements:
        return None
    if last_used_name:
        target = last_used_name.strip().lower()
        for a in arrangements:
            if (a.get("name") or "").strip().lower() == target:
                return a
    for a in arrangements:
        if not is_buried(a.get("name")):
            return a
    return arrangements[0]


def pick_id(arrangements, last_used_name=None):
    """Convenience: just the id of the chosen arrangement, or None."""
    a = pick(arrangements, last_used_name)
    return a["id"] if a else None
