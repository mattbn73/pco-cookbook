# Design — Worship Calendar Resolver

Design notes for a read-only reconciliation layer that merges PCO service plans, a
forward-planning spreadsheet, the general church calendar, and staff-meeting commitments
into one date-keyed view. Written against one church's workflow, but the pattern
(assertions + authority ranks + drift/coverage flags) generalizes.

**Status:** design / not built. Written 2026-06-22.
**Origin:** "Wednesday-night and Sunday-morning planning aren't aware of each other; we need a
top-level thing that knows where to look and what the source of truth is." Extended same session to
include the general church calendar (staff-meeting one-offs, holidays).

---

## 1. The problem, stated precisely

PCO models every plan as a standalone dated object. There is **no native link** between a
Wed PM Choir plan and the Sunday AM plan it feeds, between the Choir Specials ledger and either of
them, or between a staff-meeting commitment and the calendar entry it should become. The
relationships ("Wed 'Sunday:' slot → next Sunday's special, 5-day lead"; "Mother's Day → no
special"; "guest preacher mentioned in staff meeting → flag the plan") live in convention, scattered
notes, and a drifting spreadsheet. **The data exists; the edges between it live in no system.**

This is not a data-*access* problem (a full unified pull is ~20–40 GETs — trivial). It is a
**relationship + truth-resolution** problem. Caching is the substrate, not the solution.

### What the 2026-06-22 audit found (scope of the problem today)
- **4 drifts in a 9-week window** (ledger vs live PCO specials). Confirmed real: 6/21 was *One Day*
  in PCO, *Worthy of It All* in the ledger — a systematic ~2-week slip from June onward.
- **PCO has no Sunday AM plans past ~1 week out.** The forward plan exists *only* in the ledger.
  → For future dates, the ledger is the de-facto source of truth; PCO is empty until shells get built.
- Special-slot detection is non-trivial (naive "first song after Offering" mislabels anomalous weeks).

---

## 2. The core abstraction

**Every source emits date-keyed assertions, each with a known authority rank.** The resolver merges
assertions by date, applies precedence when they disagree, and flags two kinds of problem:
- **Drift** — two sources assert different things for the same date (ledger says Washed Away,
  pipeline says Jireh).
- **Coverage gap** — something *promised* upstream never *materialized* downstream (a staff-meeting
  commitment that never became a calendar entry; a ledger special with no PCO shell built yet).

That second class is the "forgotten one-offs" problem. It's the same machinery as drift, just
comparing a promise against its expected destination.

### Precedence rule — a time-axis crossover (the executable "snapshots vs intent")
The source of truth changes with *when* a date sits relative to now (framing from 2026-06-22):
1. **Past tense → live PCO is canonical.** Once a Sunday is past, its PCO plan is the record of what
   actually happened, full stop — *unless the user explicitly asks to update it to record a change.* Never
   "correct" a past plan to match the ledger; the plan is right and the ledger drifted.
2. **Future → the forward-planning doc is canonical.** The artifact that goes out weeks-to-months (the
   Choir Specials ledger today) is the source of truth for long-range intent, because PCO is empty that
   far out — no shells exist yet (confirmed: no Sunday AM plans past ~1 week on 2026-06-22).
3. **Near-term / crossover (this week–next) →** whichever is closest-to-execution and most recently
   edited wins. This is the contested zone the reconciler watches hardest.
4. **Holidays & liturgical dates** are authoritative-by-definition *constraints* over all of the above.
5. **Derived sidecars never auto-overwrite a past PCO plan.** The resolver flags; the user reconciles.

**VBS is an explicit exception.** Single-viewer, heavy one-off churn — treat its plans as low-trust and
out of scope for auto-reconciliation until a dedicated cleanup pass happens.

---

## 3. The layers (where every source sits)

| Source | Axis | Tier | Authority | Risk |
|---|---|---|---|---|
| **Sunday AM** (`<SERVICE_TYPE_ID>`) | plan content | **1 — authoritative** | wins where it exists; empty in future | low |
| **Wed PM Choir** (`<SERVICE_TYPE_ID>`) | plan content + pipeline | **1 — authoritative** | "Sunday:" slot = next Sun special | low |
| Sunday PM, VBS, Special (seasonal) | plan content | 1 — authoritative | coupled only in season | low |
| **General church calendar** (Apple/Google) | **events & dates** | **1 — authoritative (parallel)** | what's happening, when | **high** (hand-entered) |
| **Holidays / liturgical** | date constraints | **reference (static)** | authoritative-by-definition | low |
| **Choir Specials.xlsx** | forward special plan | 2 — derived/advisory | drifts; forward-only truth today | med |
| **Song-suggestion ballot** | song source pool | 2 — derived/advisory | input to pipeline | low |
| **Plan notes** (in PCO) | forward rollover + history | 2 — advisory | free text | med |
| **Staff-meeting minutes** | commitments → events | **feeder (ingest)** | becomes calendar + sometimes a plan | **high** |

### Calendar, specifically (answering "what layer is it — derived?")
**Not derived. Calendar is a second Tier-1 authority — but on a different axis.** PCO is
authoritative for *what's in a service*; the calendar is authoritative for *what's happening and
when*. They intersect, and the intersection is where the value is:
- **Holidays are reference-tier constraints.** Mother's Day → no choir special (we literally found
  this correction); July-4 weekend → lighter; Easter → multi-song; Advent → Christmas track. The
  resolver applies these as rules over the worship timeline.
- **One-off events are Tier-1 once entered, but the staff-meeting pipeline is their feeder.** A
  staff-meeting transcript processor already emits a *calendar diff* + *personal-implications brief* —
  that is exactly an upstream assertion stream. Its output should flow into the resolver as
  "promised events."
- **The *implications* of calendar on worship plans are derived** — the resolver computes them: "this
  Sunday is Mother's Day → expect no special"; "staff meeting committed a guest preacher 6/28 → flag
  the plan"; "ledger promises a special 7/12 but no PCO shell + no calendar confirmation → coverage gap."

So the resolver becomes **date-keyed**: for any date it assembles PCO plan + ledger intent + calendar
events + holiday constraints + staff-meeting commitments → one unified view, plus a flag list (drift +
coverage gaps). The one-offs that slip through the cracks are caught as coverage gaps between the
staff-meeting feeder and the calendar/plan destination.

---

## 4. The resolver's three jobs

1. **Merge** — assemble a date-keyed unified view across all coupled sources (worship + calendar).
2. **Resolve** — apply the precedence rule to pick the authoritative value per date/field.
3. **Reconcile** — emit flags: drift (sources disagree) and coverage gaps (promised ≠ materialized).
   Output is a report, like `tuesday_report.py` evolved. Never writes back without confirmation.

---

## 5. Architecture & phases (each ships on its own)

Built on the existing (stranded) sqlite cache. Each phase has its own Definition of Done.

### Phase 0 — Un-strand the cache  *(blocker for everything)*
- Sort out main's uncommitted state, merge the sqlite-cache branch.
- **DoD:** `refresh.py` runs on main; songs/arrangements/tags cached; tests green.

### Phase 1 — Worship substrate
- Extend the cache pull to **plans + items + needed_positions + team_members** for the coupled
  service types (Phase-2 of the original cache brief). Add a `keys` table.
- **DoD:** a date range of Sunday AM + Wed PM Choir plans queryable from sqlite, refreshed nightly.

### Phase 2 — Edge view (the unification)
- Robust **special-slot detection** (song between Offering and INVITATION headers, handling anomalies
  — not "first song after Offering").
- A derived view joining each Sunday AM plan to its feeder Wed PM Choir "Sunday:" slot (5-day lead).
- **DoD:** one query returns, per Sunday, {PCO special, Wed-predicted special, do-they-agree}. The
  schedules are now "aware of each other."

### Phase 3 — Worship drift reconciler
- Compare ledger ↔ PCO-derived special ↔ Wed prediction across a window. Flag mismatches; respect the
  precedence rule (future = ledger authoritative; near-term = PCO).
- **DoD:** a report that would have flagged the 6/21 *One Day* / *Worthy* drift and the 2-week slip
  automatically. Flags only — no auto-fix.

### Phase 4 — Calendar layer
- Ingest **holidays/liturgical** as a static reference table (constraints).
- Ingest the **general calendar** (Apple/Google) and the **staff-meeting feeder** output as
  date-keyed event/commitment assertions.
- **Coverage reconciler:** flag promised-but-not-materialized (staff-meeting commitment with no
  calendar entry; ledger special with no PCO shell; holiday with a conflicting plan).
- **DoD:** for any date, the resolver lists service + special + one-offs + holiday constraints +
  open staff-meeting commitments, and flags anything promised that hasn't landed.

### Phase 5 — The unified view ("one place to look")
- A single date-keyed report / CLI: "show me the next N weeks, fully resolved, with all flags."
- The precedence rule documented in the project conventions so it's executable policy, not tacit.
- **DoD:** the user opens one artifact and sees the whole picture — worship + calendar — with a short flag
  list of everything that needs attention. No cross-referencing across PCO, xlsx, and calendar by hand.

---

## 6. Definition of "finished" (whole system)
The system is **done** when:
- There is **one command** that produces a date-keyed, fully-resolved forward view (worship + calendar).
- It **flags every drift and coverage gap** (the 6/21 slip, a forgotten staff-meeting one-off, an
  un-built ledger special) without being told where to look.
- The **precedence rule is written down and executed**, not carried in anyone's head.
- It **never auto-writes** — it surfaces, the user decides.
- Nightly refresh keeps it current; opening it is the start of any planning session.

## 7. Non-goals (explicitly)
- Not a replacement for PCO or the calendar — it reads and reconciles, it is not a new system of record.
- Not auto-reconciliation — drift/gaps are surfaced, never silently fixed.
- Not all 17 service types — only the coupled core (Sunday AM, Wed PM Choir, + Sunday PM / VBS / Special
  seasonally). The other 13 stay independent.

## 8. Anchored vs. floating songs — a roller invariant (added 2026-06-24)

The resolver's holiday rule (precedence #4: "holidays are authoritative-by-definition constraints")
lives in the **read/flag** layer. But the same constraint has to exist on the **booking/roller**
side, or the roller keeps mis-booking exactly what the resolver would keep flagging. Two song
classes:

- **Floating** — timing is *relative*. Introduce → ~2 weeks as "New" → graduate to the "Sunday:"
  slot. The performance date is an **output** of the rule. Most songs.
- **Anchored** — the performance date is an **input**, pinned by the calendar. A patriotic number on
  Independence Sunday isn't "should be near," it's "**must be on, and is invalid after**." It also
  drops off cleanly the moment its date passes — it does *not* roll into next week's Review like a
  floating song would (singing it the Sunday after July 4 is wrong, not just suboptimal).

**Design principle: anchored songs are constraints, not participants.** Place them first — pin the
song to the Wednesday that feeds its anchor Sunday — then roll the floating songs *around* them.

**The window, not the deadline.** A floating song has one constraint ("ready by"). An anchored
holiday song has a *window*: an **earliest-OK** (don't sing patriotic in May) and a hard
**latest-OK** (= the date itself). Some calendar dates *suppress* instead of *require* (Mother's Day
→ no special). So the calendar layer needs both "requires X here" and "forbids X here / after here."

**Worked example (the bug that motivated this).** The summer roller treated *Truth Is Marching On*
(anchored to Sun 7/5/2026, Independence Sunday) as floating. Its fixed "New for N weeks → Sunday
slot" lead-time carried its performance to **7/12** — one Wednesday too far, sailing past the
immovable anchor, while 7/5 got a generic *Worthy of It All*. Fixed by hand 2026-06-24: re-pinned
Truth → 7/5, slid Worthy → 7/12, in PCO plans + the ledger + the derived turn-in lists. This is a
textbook **Phase-4 holiday coverage-gap** — the resolver, once built, should flag it automatically.

**Second roller invariant surfaced same day: minimum practice-lineup size.** Every Wed PM Choir plan
should carry **≥ 4 rehearsable songs** (Review + Sunday + New); the roller emitted a 3-song 6/24 and
it had to be topped up by hand. Both invariants (anchored-song constraints, ≥4 songs) belong in
`roll_wed_plan.py` whenever it gets built — until then they're manual checks each booking.

## 9. Open decisions
- **Calendar backend:** which calendar is authoritative — Apple Calendar, Google, or a church-wide
  shared one? Determines the Phase-4 ingest.
- **Holiday source:** hand-maintained table vs a liturgical-calendar library/feed.
- **Ledger's future:** once Phase 3 exists, does the xlsx stay as the forward-intent source, or does
  forward intent move into PCO shells (built early) + plan notes? (Affects precedence rule #2.)
- **Staff-meeting → resolver wiring:** does the staff-meeting calendar-diff write into the resolver's
  commitment store directly, or stay a separate brief the user reads?
