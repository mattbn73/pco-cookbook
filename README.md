# PCO Cookbook

Notes and scripts for automating [Planning Center](https://www.planningcenteronline.com/) (Services) via its API, from a music minister's weekly workflow at a small church.

Covers booking services from templates, scheduling teams, reconciling blockouts, and song-library cleanup. IDs and names are placeholders. Fill in your own.

## The UI is a reference client

Most of what the Planning Center web UI does, it does by calling the same API your token can reach. So when the docs don't list an endpoint for something the UI clearly does, your own browser can show you how the UI does it: open DevTools, go to the Network tab, do the action in the browser, and use Copy as cURL. (This is your own account doing its normal work; you're just reading the request your browser already sent. When you find a gap this way, it's also worth asking on Planning Center's developer GitHub — they've documented endpoints on request.)

Start with [docs/ENDPOINT-DISCOVERY.md](docs/ENDPOINT-DISCOVERY.md). The rest of the repo builds on that method.

## Docs

| Doc | What it covers |
|---|---|
| [ENDPOINT-DISCOVERY.md](docs/ENDPOINT-DISCOVERY.md) | How to capture undocumented endpoints from the web UI |
| [UI-API-crosswalk.md](docs/UI-API-crosswalk.md) | Map of UI actions to API calls, and the three kinds of work the UI does silently that a raw API call won't (cascade defaults, derived fields, guardrails) |
| [DEMAND-HARVEST-METHOD.md](docs/DEMAND-HARVEST-METHOD.md) | A framework for deciding which API gaps are worth solving |
| [multitracks-best-practices.md](docs/multitracks-best-practices.md) | Which PCO fields control what MultiTracks "Import from Planning Center" produces, and how to keep custom cloud uploads importing correctly |
| [DESIGN-worship-calendar-resolver.md](docs/DESIGN-worship-calendar-resolver.md) | Design notes: unifying PCO plans with a personal calendar into one source of truth |

## Scripts

Python 3, no framework, just `requests`. Each script is small and single-purpose. Read it before you run it.

**Setup:** put your PCO credentials in `~/Secrets/pco.env`:

```
PCO_APP_ID=your_app_id
PCO_SECRET=your_secret
```

(Get a Personal Access Token at [api.planningcenteronline.com](https://api.planningcenteronline.com/).) Then fill in your own service-type and template IDs in `scripts/service_registry.py`.

### Infrastructure (imported by the others)

- `service_registry.py`: one place to define your recurring services (service type ID, template, day, time)
- `pco_cache.py`: on-disk cache for GET responses, keeps repeated runs fast and easy on rate limits
- `pco_log.py`: append-only changelog of every write your scripts make
- `snapshot.py`: save a plan's state to disk before destructive operations, so you can undo

### Weekly workflow

- `book_service.py`: create the next service from its template in one step
- `apply_template.py`: apply a registered template to an existing plan
- `autoschedule.py`: trigger PCO's auto-schedule for one team on one plan
- `blockout_reconcile.py`: find people scheduled over their blockouts and fix the status
- `template_lint.py`: catch people who were removed from a team but crept back in via a template
- `next_plan.py`: print the next upcoming plan per service type
- `search_items.py`: search plan items by keyword across a date range

### Song library hygiene

- `dedup_songs.py` / `merge_songs.py`: find and merge duplicate songs (CCLI + fuzzy match)
- `sequences.py`: seed arrangement sequences from lyric section labels
- `arrangements.py`: pick the right arrangement when booking a song

### Discovery

- `api_action_harvest.py`: list the API actions PCO advertises that you've never used

## Safety habits

The API has none of the UI's guardrails: no confirm-before-delete, no required-field nudges. The pattern used throughout this repo:

1. Snapshot before destructive writes (`snapshot.py`)
2. Log every write (`pco_log.py`)
3. Recreate first, delete after confirming. Never delete-then-recreate.

## License

MIT, see [LICENSE](LICENSE).
