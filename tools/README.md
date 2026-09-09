# tools/

Runner scripts for research/dataset infrastructure. Not part of the runtime backend.

## Scripts

### `audit_frozen_pack.py`

Validates `research/frozen_pack_v1.yaml` structure. Verifies:
- 100 matches total
- 20 matches per weapon × 5 weapons
- No self-play
- Every model appears ≥5 times (meets cross-benchmark joint filter)
- All seeds unique
- All models exist on live backend

Run at pack lock-time and after any manual edit:

```bash
python3 tools/audit_frozen_pack.py
```

Exit code 0 = pass. Prints per-model slot count.

### `run_calibration_batch.py`

The controlled **real-provider calibration batch** (next-step priority 1).
It is a calibration of the measurement pipeline, not a tournament: the
infrastructure is covered by 240+ tests, the model conclusions are not,
because nearly every stored match was fought by scripted baselines.

Design (`build_plan`): every unordered pair of the chosen models × every
cell of 2 weapons × 2 arenas × 2 control modes, N matches per pair, canvas
side alternated per cell so each model plays left and right equally, seed
= `base_seed + idx`, `strict` no-fallback policy, `standard` length. Every
result row carries the field list the plan asks for (`RESULT_FIELDS`:
benchmark/prompt/physics version, spec fingerprint, model requested + used
and provider per side, seed, weapon, arena, control mode, latency, tokens,
API calls, fallback status, eligibility status, evidence class).

The run ends with an **acceptance audit** (`audit.md` / `audit.json`):
100 % provider + model identified, 100 % eligibility recorded, no silent
fallback in strict mode, ≥ 95 % token coverage or the gap reported, failed
matches retained but excluded, and *real-provider evidence present*. A
scripted dry-run therefore always ends `NOT ACCEPTED` on exactly the last
check — that is the point.

```bash
# offline pipeline dry-run, no keys (≈10 s, 96 sprint matches)
SDL_VIDEODRIVER=dummy python3 tools/run_calibration_batch.py run --local \
    --models bot:pro,mock:duelist,bot:greedy,bot:distance --n 16 --length sprint \
    --out-dir research/calibration/dry-run

# plan the real batch (inspect design + match count before spending anything)
python3 tools/run_calibration_batch.py plan \
    --models groq:llama-3.3-70b-versatile,groq:openai/gpt-oss-120b,openai/gpt-oss-20b:free,google/gemma-4-31b-it:free \
    --n 24 --out research/calibration/2026-09/plan.json

# run it against a backend that has the provider keys (resumable, throttled)
python3 tools/run_calibration_batch.py run --backend https://<backend> \
    --plan research/calibration/2026-09/plan.json \
    --out-dir research/calibration/2026-09 --throttle-sec 90

# re-audit any results file later
python3 tools/run_calibration_batch.py audit research/calibration/2026-09/results.jsonl \
    --plan research/calibration/2026-09/plan.json
```

`--backend` posts `blind: true, flip: false` so the server pins canvas
sides to request order (the plan already balances them) and reads the
finished row back from `/api/export`, so the batch lands in the same
database the leaderboard reads. `--local` runs through `simcore` in
process and needs the provider keys in the environment for real models.
Both paths produce identical rows for the same plan — verified on 24
scripted matches (all fields equal), which is the reproducibility claim
the runner exists to make.

**Status (2026-09-09):** the runner is verified offline and end-to-end
against a local backend with scripted fighters. **No real-provider batch
has been run** — the sandbox has no `OPENROUTER_API_KEY` / `GROQ_API_KEY`.
Until one is, `/api/data_quality` keeps reporting `evidence_level:
scripted_only` and the leaderboard banner stays up.

Throttle: the default 5 s between matches is for a local backend. Against
prod use `--throttle-sec 90` (40/hour) or check `security.py:RL_MATCHES_PER_HOUR`.

### `export_dataset.py`

Versioned public dataset release (priority 3) in the Hugging Face layout
`matches/ votes/ events/ actions/`, each as JSONL + CSV (+ Parquet when
pandas/pyarrow are installed), with `SCHEMA.json` (data dictionary),
`MANIFEST.json` (versions, counts, data-quality summary, SHA-256 of every
file, a Bradley–Terry snapshot), `SHA256SUMS` and a dataset-card README.
Every table goes through a column **whitelist** — `TABLES` in the script —
so API keys, provider headers, prompts, commentary, error text and anything
else not in the dictionary cannot leave the database.

```bash
# offline, from a local database (reads all replays for events/actions)
SDL_VIDEODRIVER=dummy python3 tools/export_dataset.py build \
    --db stickblade/arena_data/arena.db --out-dir research/exports --version v2026.09.09

# from a backend (fetches up to --replays per-match replays)
python3 tools/export_dataset.py build --backend https://<host> \
    --out-dir research/exports --version v2026.09.09 --replays 500

# anyone, later: hashes + refit the ranking from the files alone
python3 tools/export_dataset.py verify research/exports/v2026.09.09
sha256sum -c research/exports/v2026.09.09/SHA256SUMS
```

`verify` exits non-zero when any hash mismatches or when the Bradley–Terry
point estimates refitted from `matches` + `votes` differ from the
`ratings_snapshot` in the manifest — that is the "results regenerable from
exported data" criterion, checked mechanically. `tools/benchmark_report.py
--export <release>/matches/matches.jsonl` renders a report from a release
and its §0 names the dataset version and evidence level.

Releases are not committed to git (they can be large); publish them to the
HF dataset repo `Pioneer37/stickblade-matches` (needs `HF_DATASET_TOKEN`,
not yet done) or attach them to a GitHub release.

### `run_frozen_pack.py`

Dispatches the 100 matches to the live backend, polls until done, appends results to `research/frozen_pack_v1_results.csv`. Resumable — skips matches already recorded.

Full runtime: **~2.5 hours** at the default 40-matches/hour throttle.

**Cost:** **$0-$1** — the pack is dominated by free-tier models (OpenRouter :free + Groq free tier + non-LLM bots). Only `openai/gpt-4o-mini` matches consume budget, and it appears in 10 of 100 matches at ~$0.005/match = $0.05 realistic cost.

#### Sequence to actually run it

**Prerequisite: check your API budget.**

```bash
# Verify backend health, OpenRouter + Groq keys set, and prompt version 1
curl https://pioneer37-stickman-arena.hf.space/api/health
# want: {"up": true, "has_openrouter": true, "has_groq": true, ...}

curl https://pioneer37-stickman-arena.hf.space/api/version
# want: {"prompt_version": 1, ...}
```

**Step 1 — dry run (no matches dispatched):**

```bash
python3 tools/run_frozen_pack.py --dry-run
```

Expected output:
- Preflight checks pass
- "All 21 models in the pack are live on the backend"
- ETA ~150 minutes

If any model is missing from the roster, fix the pack YAML OR wait for the model to reappear before proceeding.

**Step 2 — start the real run:**

```bash
python3 tools/run_frozen_pack.py 2>&1 | tee tools/frozen_pack_run.log
```

- Runs in the foreground. Do NOT close the terminal.
- If you must interrupt, `Ctrl+C` is safe — restart later, it resumes from the last CSV row.
- Every completed match appends to `research/frozen_pack_v1_results.csv`.
- Errors go to `research/frozen_pack_v1_errors.jsonl`.

**Recommended: run overnight in a `screen` or `tmux` session so a laptop close doesn't kill it:**

```bash
tmux new -s frozen-pack
python3 tools/run_frozen_pack.py 2>&1 | tee tools/frozen_pack_run.log
# Ctrl+B then D to detach; tmux attach -t frozen-pack to reattach
```

**Step 3 — after completion, re-run the correlation study:**

```bash
python3 research/cross_benchmark_correlation.py
```

The script auto-detects `frozen_pack_v1_results.csv` and includes those matches in the export DataFrame. Expected result: Spearman ρ becomes computable at n≥5 shared models. If still underpowered, investigate why (roster changes? new errors?).

**Step 4 — update the report:**

Take the new ρ number(s) from step 3, edit `research/cross_benchmark_correlation_report_2026-08-04.md`:
- Add a "2026-XX-XX update: frozen pack results" section at the top
- Report the new ρ + bootstrap CI + p-value
- Update METHODOLOGY.md § 4.1 to remove the "underpowered" caveat
- Update TIMELINE.md: mark Tier-A #4 shipped, mark Research grade 8.2 → 8.4 (per §0.5 evidence bar)

### Rerunning specific matches

If a match errored (rate limit, provider outage), rerun just those:

```bash
# Look up the failed match indices in frozen_pack_v1_errors.jsonl
python3 tools/run_frozen_pack.py --start 42 --end 42
```

### Throttle tuning

Default throttle is 90s between matches (40/hour, under the 50/hour backend cap). If you have a paid HF Space upgrade, or you're running against a local dev backend, you can go faster:

```bash
python3 tools/run_frozen_pack.py --throttle-sec 30    # 120/hour
```

Do NOT do this against live prod without checking `security.py:RL_MATCHES_PER_HOUR` — you'll rate-limit yourself out and half the matches will fail.
