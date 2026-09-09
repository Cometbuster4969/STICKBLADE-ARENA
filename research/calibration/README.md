# Calibration batches

Output of `tools/run_calibration_batch.py` — the controlled real-provider
calibration run that priority 1 of the September 2026 review asks for.
One directory per run: `plan.json` (the design, reproducible from its
header alone), `results.jsonl` / `results.csv` (one row per match, schema
= `RESULT_FIELDS` in the tool), `audit.json` / `audit.md` (acceptance
audit against the review's criteria).

| run | date | models | evidence | audit |
|---|---|---|---|---|
| `dry-run/` | 2026-09-09 | `bot:pro`, `mock:duelist`, `bot:greedy`, `bot:distance` (all scripted) | 96 scripted / 0 real | **NOT ACCEPTED** — fails only `real_provider_evidence_present`, by construction |

The dry run validates the pipeline (side balance 0, seeds unique, 96/96
provider + model identified, 0 silent fallbacks, failed rows retained).
It says nothing about any model. **No real-provider batch has been run
yet**: it needs `OPENROUTER_API_KEY` / `GROQ_API_KEY` on the backend, and
the sandbox that produced the dry run had neither. When one runs, add it
here, keep the dry run, and update `research/reports/`.
