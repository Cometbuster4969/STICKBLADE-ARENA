# HTTP API reference

The FastAPI backend also serves a machine-readable OpenAPI schema at
**`/openapi.json`** and interactive docs at **`/docs`**. This file is the
human-readable map of what matters, including which endpoints are safe to call
before a vote has been cast.

Base URL in production: `https://pioneer37-stickman-arena.hf.space`
Local: `http://localhost:8000` (or same-origin `/api` through the Next dev proxy).

> **Blind-election rule:** nothing under *pre-vote* may reveal which model is
> which. Model names appear only in the reveal payload (`POST /api/vote/{id}`,
> `GET /api/replay/{id}` after voting, `/api/export`, `/api/leaderboard`).

## Specification & integrity

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/benchmark/spec` | The whole frozen specification as JSON (benchmark, physics, rules, model interface, rating, voting, eval axes, licences). |
| GET | `/api/version` | API version, `prompt_version`, weapons, modes, replay format. |
| GET | `/api/health` | Liveness: which provider keys are configured, queue depth. Distinguishes "backend down" from "backend up, provider throttled". |
| GET | `/api/status` | `status` (`ok`/`degraded`/`down`), component health incl. `replays` (is the latest replay blob readable), `degraded_modes[]` in plain words (no provider key, scripted-only rankings, fallback/failure rate, queue depth, replay storage), `last_incident {at, what}` (last scrubbed backend error since process start), `provider_errors`, 24 h failure rate, completion rate, `data_quality` evidence summary, version triple, spec fingerprint. Powers [`/status`](https://stickblade-arena.vercel.app/status). |
| GET | `/api/data_quality` | Evidence report for a cell (`sharp`, `weapon`, `mode`, `arena`, `blindfolded`): `summary.evidence_level` ∈ `scripted_only`/`insufficient_real`/`real`, counts by evidence class, real ranked matches, fallback / silent-fallback / unidentified / token-missing counts, token coverage, last match; `models[]` with per-model `evidence`, `status` (`ranking_eligible`/`exploratory_only`/`reference_baseline`) and counts; `labels` for display; benchmark/physics/prompt version + fingerprint. |
| GET | `/api/metrics` | Operational counters: matches/votes, latency percentiles, fallback rate, error breakdown. |
| GET | `/api/integrity/{match_id}` | Replay audit **plus** the anti-gaming verdict for one match. |
| GET | `/api/weapons` | Weapon catalogue with zones and empirical balance status (`balanced` / `provisional` / `asymmetric`). |

## Matches

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/models` | Roster: LLMs, scripted bots, mocks. |
| POST | `/api/match` | Start a match. Body: `model_a`, `model_b`, `sharp[]`, `weapon`, `mode`, `arena`, `blindfolded`, `match_length` (`sprint`/`standard`/`full`), `fallback_policy` (`strict`/`operational`/`demo`), `seed`, optional `flip` (`null` = random canvas sides, default; `false`/`true` pins `model_a` to left/right — used by research batches so seeded fights replay with balanced sides), optional `api_key` (BYOK). Returns `match_id`. |
| GET | `/api/match/{match_id}` | Status. **Pre-vote payload is restricted** to `{turn, action_a, action_b, hits, hp_a, hp_b, status}` — no model names, no thoughts. |
| POST | `/api/match/{match_id}/cancel` | Cancel a queued or running match; it is marked cancelled and never ranked. |
| GET | `/api/replay/{match_id}` | Full replay (frames, events, thoughts, provenance, action log). Blind until voted. |
| POST | `/api/vote/{match_id}` | Cast the vote. Body: `choice` (`a`/`b`/`draw`) plus optional `execution`, `entertainment`, `deserved` and `confidence` (1–5). **Only `choice` is ranked.** Response reveals the models and the Elo delta. |

## Rankings and data

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/leaderboard` | Perceived-Elo rows with `n`, Wilson 95 % interval, `provisional`, `eligible`, `benchmark_version`. Filter by `sharp`, `weapon`, `mode`, `arena`, `blindfolded`. |
| GET | `/api/leaderboard/objective` | Physics-derived axis (damage/turn, hit rate, fallback rate, avg distance) — independent of human votes. |
| GET | `/api/leaderboard/bradley_terry` | Bradley–Terry + Davidson ties fitted over every voted comparison in the cell at once, with bootstrap 95 % intervals, tie-informative `component`/`component_size`, and `provisional` flags. `?bootstraps=N` (0–1000, default 200), `?tier=casual\|expert` (§6, default: all votes pooled). See `METHODOLOGY.md §3.3b`. |
| GET | `/api/model_stats` | Full per-model table: win rate, human preference rate, damage/turn, hit rate, lethal rate, survival rate, timeout rate, invalid-action rate, fallback rate, latency. |
| GET | `/api/head_to_head` | Pairwise record between two models. |
| GET | `/api/export` | Public dataset: `fmt=json\|jsonl\|csv`, `since`, `until`, `limit`. Every row carries `evidence` (real_provider / mixed_provider / scripted_baseline); the JSON wrapper carries a `data_quality` summary. Match data is CC-BY-SA 4.0. Versioned releases with hashes + data dictionary: `tools/export_dataset.py`. |
| GET | `/api/recent` | Recently finished matches. |
| GET | `/api/stats/vote_rate` | Vote-through rate (the funnel metric). |

## Operating cost (§33) and access model (§34)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/costs` | Measured provider spend over `?days=N`: prompt/completion tokens, USD total, USD per match, per-model split, plus budget state and the published access tiers. |

Costs are **measured from the providers' own usage blocks**, accumulated
across retries and buddy fallbacks — so a match that degraded still reports
what it cost. Any billable match whose provider reported no usage sets
`complete: false`, which makes every figure a lower bound; unreported is
never counted as free. Scripted/offline matches are counted separately
(`matches_offline`) so they cannot mask real gaps. Prices are data:
override with `STICKBLADE_PRICES_JSON` (USD per 1M tokens per model
prefix). Budgets come from `BUDGET_DAILY_USD` / `BUDGET_MONTHLY_USD`; an
unset limit reports `status: "unset"`, never `ok`.

## Events (§31)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/events` | Recurring event calendar (`past`, `future`, `bootstraps`): running / upcoming windows plus the champions archive. |
| GET | `/api/events/{id}` | One event's windows and standings. 404 on an unknown id. |

Standings use the same Bradley–Terry fit as `/api/leaderboard/bradley_terry`.
An event names a champion only when the leader has cleared the event's
`min_matches` **and** its interval clears the runner-up's; otherwise the
payload carries `decided: false` and a `reason` saying exactly what is
missing. The schedule is derived from `stickblade/events.py` — there is no
cron and no table to fall out of sync.

## Tournaments

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/tournament` | Create a single-elimination bracket. |
| GET | `/api/tournament/{tid}` | Bracket state. |
| GET | `/api/tournaments` | List brackets. |

## Example: run a match end to end

```bash
# 1. start — scripted baselines need no key and finish in seconds
curl -X POST localhost:8000/api/match -H 'Content-Type: application/json' \
  -d '{"model_a":"mock:duelist","model_b":"bot:pro","sharp":["tip"],
       "weapon":"sword","mode":"macro","arena":"normal",
       "match_length":"sprint","fallback_policy":"operational","seed":42}'
# → {"match_id":"ab12cd34ef56","status":"queued", ...}

# 2. poll (pre-vote: no model names, by design)
curl localhost:8000/api/match/ab12cd34ef56

# 3. vote blind — this is the only ranked input, and it reveals the models
curl -X POST localhost:8000/api/vote/ab12cd34ef56 -H 'Content-Type: application/json' \
  -d '{"choice":"a","execution":"a","entertainment":"b","deserved":"a","confidence":4}'

# 4. audit it
curl localhost:8000/api/integrity/ab12cd34ef56
```

## Python client

There is no SDK; the export tool doubles as a reference client:

```python
from urllib.request import urlopen
import json
spec = json.load(urlopen("http://localhost:8000/api/benchmark/spec"))
print(spec["benchmark_version"], spec["physics_version"])
```

## Rate limits

Per-IP sliding windows, defaults in [docs/ENVIRONMENT.md](./ENVIRONMENT.md):
50 matches/hour, 100 votes/hour, 120 requests/minute, 10 queued simulations,
300 matches/day globally. Exceeding them returns `429` or `503 arena is busy`.
