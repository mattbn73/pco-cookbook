# UI ↔ API Crosswalk — grounding pack

**Purpose.** Every "simple" action in the PCO web UI is really a *bundle* of API
operations plus silent defaults. This maps UI actions to the endpoints they fire,
names the A/B/C category of each hidden behavior, and tracks whether we have a
script for it. It exists so these stop being one-at-a-time surprises.

Companion doc: `ENDPOINT-DISCOVERY.md` (how to capture an unknown endpoint).

---

## The three categories (read-vs-build rule)

| | What it is | How to find it preemptively | Read or build? |
|---|---|---|---|
| **A — cascade defaults** | companion objects the UI auto-creates (template import, default times, needed_positions) | **harvest the `links` block** — `api_action_harvest.py` | use the action endpoint |
| **B — derived fields** | values auto-filled (`dates` string, sort_date, song length) — *raw POST is born blank* | **blank-POST-diff**: make one via API + one via UI, diff them | read it, never hardcode |
| **C — guardrails** | required fields, confirm-before-delete, no-orphans | **validation-probe**: malformed POST → read the `errors`; ask "what would the UI never let me do?" | build it yourself |

The harvest finds **A only** (actions are links). B and C are *absences* and don't
appear as links — they need the diff / probe methods above.

**Quick tell for which category:** does the UI do it silently for me? → A or B (endpoint exists).
Does the UI stop me or make me confirm? → C (no endpoint; self-build).

Regenerate the gap list anytime: `python api_action_harvest.py` (`--md` for a table).

---

## Mapped actions (known + worked)

| UI action | Real API bundle | Hidden behavior | Have script? |
|---|---|---|---|
| **Add plan(s)** in a service type | `POST create_plans` (or `POST /plans` + `POST /plan_times`) | **A**: next-date from `frequency`; default time from `time_preference_options` (e.g. "Wed 6:45p"). **B**: plan `dates` only renders from a **`service`**-type plan_time — a `rehearsal` time → "No dates". **B**: send times as **UTC**; PCO treats an offset literal as UTC. | `book_service.py` (fixed 2026-06) |
| **Apply a template** | `POST /plans/{id}/import` (or template `import`) | **A**: items + needed_positions + people (Unconfirmed) cascade in one call. Template's real items live at `/plan_templates/{id}/items` — the listing's `item_count` attribute can read 0 while items exist. | `apply_template.py`, `book_service.py` |
| **Add a person to a plan** | `POST team_members` (status `U`) | **C-ish**: leave `prepare_notification` false or it emails. Standing team membership ≠ plan scheduling (see gaps). | `book_service`, assign_* |
| **Drag-reorder items** | `POST item_reorder` | **A**: one call reorders; do NOT delete-and-re-POST (a mistake we made once). | — GAP |
| **Roll the weekly rehearsal order** | per-item POST/PATCH from the ledger | not a single UI action; our automation. Turn-in helper exists; the full roller isn't built. | partial |
| **Populate a team roster** (Team Members + position eligibility — the picker names) | direct POST 403s for our token; **workaround is the workflow**: (1) API-schedule the people onto a plan (`team_members`, status U — always works, plants usage history) → (2) the user clicks **"auto-assign members from usage"** on a Needed position in the plan sidebar. **A**: server derives standing membership from scheduling history, one click per position. Confirmed best path 2026-07-01 (small ministry team). | assignment scripts do step 1; step 2 is a UI click |

---

## Top gap candidates (advertised actions we don't call yet)

From `api_action_harvest.py` — 45 total; the ones with a likely use-case:

- **`Plan/autoschedule`** — UI "auto-schedule" (fill needed positions from team rotation/availability). May supersede hand-rolled assignment scripts. *Investigate before building more rotation logic.* **VERIFIED 2026-06-24**: GET self-describes "Auto-schedule for a team… POST to perform this action" — it is the UI button. Team-scoped, POST-driven.
- **`Song/song_schedules`** — PCO's own record of every plan a song touched (date + service type). **The historical half of a hand-kept song-usage ledger is a duplicate of this.** **VERIFIED 2026-06-24**: returns dated appearances per service type; filter `service_type_name == "Sunday AM"` for sung-on Sundays. (`last_scheduled_item` 404s — use `song_schedules`.)
- **`Person/blockouts`** — live scheduling blockouts. We keep `blockouts.json` — likely a hand-maintained copy. Reconcile.
- **`ServiceType/create_plans`** — the booking popup proper (batch create on cadence). We currently POST plans one at a time.
- **`Plan/next_plan`, `Plan/previous_plan`** — server-side "the Wednesday before/after this one." Useful for roll logic instead of date math.
- **`Person/person_team_position_assignments`, `Team/person_team_position_assignments`** — standing team membership. Earlier testing: POST 403s; the endpoint is advertised, so the gap is scope, not existence. **Downgraded 2026-07-01:** the schedule-then-auto-assign workflow (see mapped actions) makes this gap mostly moot — recheck only if a fully headless path is ever needed.
- **`Plan/signup_teams`, `Person/available_signups`, `Person/schedules`, `Person/scheduling_preferences`** — the self-signup / scheduling-request side we haven't touched.
- **`Arrangement/archive` + `unarchive`, `Song/assign_tags`** — arrangement lifecycle / tagging (relevant to arrangement-name cleanup).
- **`Item/item_times`, `item_notes`, `custom_slides`, `selected_attachment`, `selected_background`** — per-item timing + ProPresenter-facing slide/background selection.
- **`Plan/contributors`, `my_schedules`; ServiceType `plan_person_times`, `public_view`, `unscoped_plans`; Org `email_templates`, `report_templates`, `tag_groups`, `chat`** — lower priority, catalog for completeness.

## Designed-in duplicates surfaced (read the endpoint instead)

These hand-maintained artifacts mirror data PCO already holds — drift suspects:

- the song-usage ledger (historical rows) ↔ `Song/song_schedules` + Sunday plan items
- `blockouts.json` ↔ `Person/blockouts`
- hardcoded booking-time fields ↔ `time_preference_options`
- a hand-kept arrangement-name map ↔ arrangement names on the arrangement records

Each keeps value only for the part PCO can't answer (true *future intent* not yet on a plan). The rest is a read.

---

*Seeded 2026-06-24. Re-run `api_action_harvest.py` after PCO updates or when a new UI action surprises us; add a row here each time one does.*
