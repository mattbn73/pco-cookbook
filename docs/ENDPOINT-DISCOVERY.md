# Endpoint Discovery — the UI is a reference client

**The principle:** PCO's web app (and most SaaS web apps) is just *another client of the same API
we call.* When you do something in the UI, your browser fires the real API request behind it —
correct method, correct URL, correct body. So the UI isn't *hinting* at endpoints; it's
**demonstrating** them with working payloads you can read straight off.

This was off the radar through a VBS build and cost us real work: we hand-built a destructive
delete-all-and-re-POST reorder because we believed "you can't reorder items." Wrong — the UI's
drag-to-reorder calls a dedicated `item_reorder` action endpoint. Capturing that one call would have
saved the whole workaround.

## What to call it

- **The UI is a reference client** — the principle.
- **Endpoint capture** (a.k.a. network capture) — the technique: read the request the UI fires.
- **User-as-probe** (a.k.a. "user-as-endpoint") — the human-in-the-loop variant: the user performs
  the UI action so the agent can observe the resulting call. (The user is the *actuator* that
  triggers the real endpoint, not the endpoint itself — but "user-as-endpoint" is the handle.)

Treat a UI action you can't yet do via API as a **candidate endpoint**, not a wall.

## The reliability ladder (best → worst)

1. **Capture the network call** — DevTools → Network, do the action, **Copy as cURL**, decode it.
   Ground truth. Use this for anything that will drive automation.
2. **Agent drives the browser** — if the Chrome extension is connected, Claude opens the page,
   performs the action, and reads the traffic itself. No copy-paste.
3. **Infer from docs** — describe the UI action, Claude maps it to a likely endpoint. A guess only.
   Mark results UNVERIFIED until confirmed by mode 1 or 2.

## The as-if script (the built-in procedure)

```
WHEN  an API call 422s/403s, behavior is undocumented, or the question is
      "can the API even DO this thing the UI does?"

THEN
  1. HYPOTHESIZE   "the UI does X, so an endpoint for X exists." Name it a candidate endpoint.
  2. PICK MODE     by who's at the keyboard:
        user at machine + Chrome extension  -> Mode 2 (Claude drives & captures)
        user at machine, no extension        -> Mode 1 (Claude guides capture, user pastes cURL)
        nobody at the UI                     -> Mode 3 (infer from docs; mark UNVERIFIED)
  3. CAPTURE       do the action ONCE; grab the request (Copy as cURL).
  4. DECODE        extract method + URL + JSON body.
  5. VERIFY TOKEN  re-issue the call with our PAT/OAuth creds (~/Secrets/pco.env).
                   401/403 -> auth/scope gap: note it; the UI uses a session cookie, our
                   token may lack the scope. Don't assume "impossible" — assume "wrong creds."
  6. EMIT          write an idempotent script + record the finding in the project's conventions notes.
```

## Mode 1 — guided network capture (numbered steps to give the user)

1. 🌐 In Chrome, open the PCO page where the action happens.
2. ⌥ Open DevTools (`Cmd+Opt+I`) → **Network** tab.
3. 🔎 Filter to **Fetch/XHR**.
4. 🧹 Click **Clear** so the list is empty.
5. 👆 Do the ONE action in the UI (e.g. drag an item to reorder).
6. 🖱️ Right-click the new request that appears → **Copy → Copy as cURL**.
7. 📋 Paste the cURL into chat. Claude decodes endpoint + body and writes the script.

The single highest-leverage move is step 6–7: **Copy as cURL → paste**. It skips all transcription
and gives Claude the exact, working call.

## Prompt templates (copy-paste)

**Guided capture (user at the keyboard):**
> "I'm in [app]. I want the API call behind [UI action]. Give me the exact step-by-step to capture it
> in the browser network inspector, then I'll paste the 'Copy as cURL' and you decode it into the
> endpoint + body + whether my token can call it."

**Agent-driven (Chrome extension connected):**
> "Reverse-engineer the [action] endpoint in [app] — drive Chrome, watch the network tab, and report
> the call (method, URL, body) plus whether our PCO token can make it."

**Inference only (nobody at the UI):**
> "In [app], when I do [UI action], what endpoint is probably behind it? Check the docs and mark it
> UNVERIFIED until we capture it for real."

## Caveats

- Web app auth = **session cookie**; our scripts = **PAT/OAuth token**. A captured endpoint may need a
  scope our token lacks → that's the team-membership 403 situation. Re-test creds before concluding
  "the API can't."
- A few UI actions hit **internal/undocumented** endpoints that differ from the public API. PCO is
  mostly the same JSON:API surface, so usually directly reusable — but verify.

## What the UI does silently that a raw API call may not — classify it (A/B/C + locus)

When you *miss* a UI convenience, first ask **which category**, then **which locus**. That pair
predicts whether capturing the UI's network call hands you an endpoint, or whether you're building a
guard layer yourself.

**Category — what kind of help is missing:**

| | Category | What it does | Example | On the API? |
|---|---|---|---|---|
| **A** | **Cascade defaults** | companion *objects* auto-made | Song → default arrangement | ✅ often server-side; free |
| **B** | **Derived fields** | *values* auto-filled | arrangement length; item length at insert | ⚠️ split (see locus) |
| **C** | **Guardrails** | bad/incomplete actions *prevented* | required fields, confirm-before-delete, no orphans | ❌ never — build it yourself |

**Locus — where the behavior lives (this decides recoverability):**

- **Server-side** → happens for any caller (UI or API). You get it free. *(default arrangement;
  item-length-copies-from-arrangement-at-insert — both verified on PCO.)*
- **Action endpoint** → the UI convenience exposed as a non-CRUD verb (`item_reorder`,
  `import_template`). Exists; just call it. **Endpoint-capture finds these.**
- **Client-orchestrated** → the browser fires several plain calls in sequence. No magic endpoint —
  replicate the sequence.
- **Pipeline-side** → an import/ingest flow adds the value. A raw POST skips that flow → born blank.
  *(arrangement length comes from the Lifeway/WorshipTools import; a POSTed arrangement has none.)*

**The rule:** A and B *sometimes* have an endpoint worth capturing (server-side or action verb).
**C never does** — guardrails are yours to build (validate-before-write, confirm-before-delete).

Grounded example: POSTing a new song on the PCO API *does* return a default arrangement (Category A,
server-side — confirmed in a live build script's `if arrs:` branch), but that arrangement is born
with **no length** (Category B, pipeline-side — length only arrives via import).

## Transport gotchas (HTTP-level, not API-logic) — found 2026-06-22

These aren't about *which* endpoint; they're ways a correct call silently fails or 422s.

- **POST 302 → silent GET downgrade.** The convenience paths `POST /plans/{id}/items`,
  `/plans/{id}/needed_positions`, `/plans/{id}/team_members` return a **302** redirecting to the
  canonical `/service_types/{st}/plans/{id}/...` path. `requests` (and most clients) follow the 302
  and, per HTTP spec, **convert POST→GET** — the JSON body gets flattened into the query string and
  the call becomes a no-op list read (**HTTP 200 + `data: []`**, looks like success; the `links.self`
  echoes your body as `?data[attributes][...]=...`). Nothing writes. **Fix: always POST/DELETE to the
  canonical `/service_types/{st}/plans/{id}/...` path.** GETs are unaffected (GET→GET survives), which
  is the trap — reads always look right while writes vanish. Cost us a full false-success build pass
  before the 302 was spotted with `allow_redirects=False`.
- **needed_position wants a team_position *id*, not a name.** `POST .../needed_positions` with only
  `attributes.team_position_name` → **422 "invalid for team."** Resolve the id via
  `GET /teams/{team_id}/team_positions`, match by name, send as a `team_position` relationship.
- Both are encoded in `apply_template.py` so they don't get rediscovered.
