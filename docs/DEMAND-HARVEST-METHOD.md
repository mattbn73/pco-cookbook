# Demand-Harvest Method — ranking beginner tasks to find API gaps

**Purpose.** Decide *which* hidden UI behaviors are worth turning into endpoints first,
by ranking beginner tasks on how much the world asks about them. Pairs with
`UI-API-crosswalk.md` (the A/B/C gap map) and `ENDPOINT-DISCOVERY.md` (how to capture an
unknown endpoint). Output lives in `DEMAND-RANKED-GAPS.md`.

This is the **demand layer** the crosswalk lacked: the crosswalk tells us *what* the UI
hides; this tells us *which hidden things matter to the average user*, so we build the
high-traffic ones first instead of whatever surprised us last.

---

## The core insight — demand × invisibility (not demand alone)

The starting heuristic: more questions / more "101" articles / more tutorial videos = more
valid for the average use case. True, but as a raw rank it points at the wrong target.

**Tutorials cluster on *visible* friction.** The valuable API gaps hide where **high
demand meets LOW tutorial coverage — because the UI made the work invisible** (the
cascade nobody films, since one click does it). So we score two axes and multiply:

```
            INVISIBILITY  (how silently does the UI do it?)
            low                         high
demand high │ table stakes            │ ◀ THE GOLD ▶          │
            │ (well-tutorialed; the   │ high demand + few     │
            │  API usually exposes it │ tutorials *because*    │
            │  cleanly already)       │ the UI hides it →      │
            │                         │ Category-A cascade     │
demand low  │ ignore                  │ niche; catalog only    │
```

`ROI ≈ demand × invisibility`, then discounted by **"do we already have a script?"** A
high-ROI task we've already automated drops off the build list (it stays as a *teaching*
row for a future natural-language → UI-steps teaching layer, but not a build target).

---

## The five stages

### Stage 1 — Harvest the beginner-task inventory
Pull natural-language intents from four sources, **most authoritative first**:

| # | Source | What it tells you | How to read it |
|---|---|---|---|
| a | **Planning Center University** workbook + course list | the canonical "what a beginner must learn" curriculum | each lesson/session topic ≈ one beginner intent. PDF: `planningcenterassets.s3.amazonaws.com/downloads/pcu/Planning_Center_University.pdf` |
| b | **Help Center "Getting Started" hubs** | how much official 101 attention each topic gets | count articles per cluster. Role hubs `138432`/`138434`/`138435`/`138436`/`138437` link the canonical beginner articles (category index pages are JS-rendered — use the role hubs) |
| c | **YouTube / creator tutorials** | external demand + the *visibility* signal | per task: count dedicated how-to videos (none/few/many/saturated) + view counts where reachable. WorshipResources.church + PCU are the anchor channels |
| d | **Community question frequency** | where beginners get *confused* (the invisibility signal) | recurring "why did/didn't X happen" themes. Browse Reddit and the official Community forum by hand for these; a good shortcut is the answer-side proxy (help articles + creator blogs + Capterra reviews exist *because* a question recurs) |

Phrase every row as a plain-language intent ("schedule someone for Sunday", "build this
week's plan from last week", "why is everyone still yellow?").

### Stage 2 — Score demand
Per intent, a 1–5 composite of: official-lesson presence (a+b), tutorial-video tier (c),
community-question frequency (d). Tutorial *volume* is the popularity proxy; community
*confusion* is the early read on invisibility.

### Stage 3 — Map the linguistics (plain-words layer)
For each high-demand intent: plain words → official jargon → exact UI steps → objects/
fields touched. This stage seeds a reusable plain-words ↔ jargon crosswalk and a
procedure map per intent.

### Stage 4 — Classify the gap (A/B/C + invisibility score)
For each intent's UI steps ask "what does the UI do silently?" Tag **A** cascade default /
**B** derived field / **C** guardrail, and tag the **API shape**: single endpoint ·
endpoint combination · ordered cascade/sequence. Set invisibility 1–5. Fill unknowns with
`api_action_harvest.py` (finds Category-A action gaps) and the `ENDPOINT-DISCOVERY.md`
capture procedure. **Remember C never has an endpoint — those are teaching rows, not
build targets.**

### Stage 5 — Rank by ROI
`demand × invisibility`, discounted by existing-script status. Write the ranked register
to `DEMAND-RANKED-GAPS.md`; the top cell = endpoint sequences to build first.

---

## Re-running it
Stages 1–2 are a web-research fan-out (3 agents: official inventory, video census,
community frequency). Stage 4 leans on `api_action_harvest.py`. Designed to later run on
a weekly refresh so the demand scores stay current as PCO's curriculum and the
creator ecosystem move. Re-run after a major PCO release or when a new beginner task keeps
coming up.

*Seeded 2026-06-26 (PCO Services first pass). Sources cited per-row in `DEMAND-RANKED-GAPS.md`.*
