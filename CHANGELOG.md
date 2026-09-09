# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for the
API, with one addition that matters more than either: **the benchmark version
triple**. Any change to match rules, physics, or prompting bumps
`BENCHMARK_VERSION` / `PHYSICS_VERSION` / `PROMPT_VERSION` and invalidates
cross-version leaderboard comparison, regardless of the API version.

> History before 2026-09-08 lives in the commit log and in
> [TIMELINE.md](./TIMELINE.md), which is the authoritative narrative of what
> shipped and why. This file starts at the point the frozen spec landed.

## [Unreleased] — benchmark spec v1.0 (fingerprint `09de66effd02` under prompt v2; `029281ed627a` under prompt v1)

### Added — next-step priorities 1–5 (2026-09-09, second session)

- **P1 · calibration batch runner** `tools/run_calibration_batch.py`:
  balanced plan (every pair × weapon × arena × control mode, sides
  alternated per cell, seed = base + idx, strict policy), `--local` and
  `--backend` runners producing identical rows (verified 24/24), resumable,
  acceptance audit against the review criteria. Scripted dry run committed
  under `research/calibration/dry-run/` — `NOT ACCEPTED` on exactly
  `real_provider_evidence_present`, by construction. **No real-provider
  batch has been run** (no keys in the environment).
- **P2 · data-quality labels** `stickblade/data_quality.py` + `GET
  /api/data_quality`; `evidence` on every export row; `data_quality` block
  on every ranking row (`/api/leaderboard`, `/bradley_terry`,
  `/model_stats`, `/objective`) and on `/api/status`; banner + chips in
  the web app (`components/DataQuality.js`).
- **P3 · versioned dataset release** `tools/export_dataset.py build|verify`:
  HF layout `matches/ votes/ events/ actions/` in JSONL+CSV+Parquet,
  column whitelist, `SCHEMA.json`, `MANIFEST.json` with SHA-256 per file and
  a Bradley–Terry snapshot, `SHA256SUMS`, dataset-card README. `verify`
  re-hashes and refits from the files alone; fails on tampering (tested).
  `tools/benchmark_report.py` gained §0 *Data quality* (dataset version,
  versions, fingerprint, evidence split) and reads JSONL.
- **P4 · status page**: `/api/status` now reports overall `status`,
  `components.replays`, `degraded_modes[]`, `last_incident`,
  `provider_errors`; `/status` renders them. An all-scripted deployment
  is `degraded`, not `ok`.
- **P5 · public pages** `/research` (the seven reviewer questions),
  `/methodology`, `/data`, `/reproducibility`, `/limitations`; shared
  `components/DocPage.js` with a live evidence strip from
  `/api/data_quality` so prose cannot outrun the data. Nav, footer, sitemap.
- `POST /api/match` accepts optional `flip` (`null` = random, unchanged
  default) so research batches can pin canvas sides.

### Fixed

- **Seeded fights differed between server and offline paths**:
  `brains.pre_fight_quip` / `MockBrain.chat` drew from the decision RNG, so
  asking for trash talk changed the fight. Now peek a copy of the RNG
  state. Regression test in `tests/test_replay_determinism.py`.
- `MockJointBrain.decide_with_timeout` skipped the provenance stamps, so
  scripted joint matches reported an empty provider; joint mocks now carry
  the roster id (`mock:duelist`) instead of `Mock-jointer`.
- **Spec fingerprint drift explained and pinned**: `029281ed627a` was the
  spec under prompt v1, `09de66effd02` under prompt v2 (the fingerprint
  hashes `PROMPT_VERSION`). Docs corrected; CI asserts the value per prompt
  version instead of printing it.

### Added — ratings with uncertainty (2026-09-09, action-plan §5)

- **`stickblade/ratings.py`** — Bradley–Terry with a Davidson tie term, the
  tie parameter estimated from the data (a fixed ν silently compressed a
  90/10 record to 1.21 logits instead of the analytic 2.197), ridge
  shrinkage so a 3–0 newcomer stays finite, bootstrap 95 % CIs that
  resample matches rather than pair rows, and connected-component reporting.
- `GET /api/leaderboard/bradley_terry` (`?bootstraps=`, `?tier=`) and
  `GET /api/model_stats`. New UI tabs: **Bradley–Terry (with CI)** — where
  overlapping intervals share a tie letter and are labelled *not separable*
  — and **Full metrics**.
- `docs/CAPACITY.md` — first measured throughput (1/5/25/100 concurrency →
  59/99/111/105 matches per minute, 0 failures; CPU-bound on one worker).

### Added — evaluators, events, cost, ablations (§6, §10, §31, §33/34, §11)

- **§6** Votes carry a self-declared `voter_tier`; ratings can be fitted per
  tier and the export carries `votes_expert` / `votes_casual`. A label, not
  a weight — the tiers are never pooled silently.
- **§10** Research debug overlay in the replay player (⚙ Debug, or `d`):
  hitboxes, weapon segments with the sharp zone highlighted, velocity
  vectors, contact points with damage and body part, frame/turn/action. All
  replayed from stored frame data; nothing re-simulated.
- **§31** `stickblade/events.py` + `/api/events` + `/events`: weekly cup,
  monthly season, weapon cups, blindfolded challenge, speed tournament,
  JOINT open. Schedule derived from cadence + anchor (no cron, no table to
  desync). A champion is named only when the leader clears the minimum
  sample **and** separates from the runner-up.
- **§33/§34** Provider-reported token usage is now captured and persisted,
  so `/api/costs` reports measured spend. Unreported usage ⇒
  `complete: false` (a lower bound, never free); offline matches counted
  separately; unset budgets report `unset`. Access tiers published.
- **§11** `stickblade/ablations.py` + `tools/run_ablation.py`: ten state
  ablations, verified valid, with measured prompt cost per field. The
  behavioural sweep refuses to run on scripted fighters.

### Changed

- `PROMPT_VERSION` is **unchanged**. Note for future work: the bow
  `per_shot` aiming tables are ~25 % of every prompt and are meaningless in
  melee; gating them on weapon would be a spec change and needs a version
  bump, so it is queued rather than applied
  (`research/ablation_prompt_cost.md`).

### Added — frozen specification & provenance

- **`stickblade/benchmark.py`** — the authoritative spec document. Derives its
  values from the live code so it cannot drift, emits a 12-hex
  fingerprint (`029281ed627a`) stored on every match and replay, and provides
  `provenance()` + `verify_replay()` (`stickblade/benchmark.py:111`,
  `stickblade/benchmark.py:296`).
- Every match now records `benchmark_version`, `physics_version`,
  `prompt_version`, `spec_fingerprint`, `seed`, `match_length`, `max_turns`,
  `fallback_policy`, `model_used_a/b`, `provider_used_a/b`, `fallback_used`,
  `latency_ms_a/b`, `invalid_actions_a/b`, `ranking_eligible`, `cancelled`.
- **Deterministic action log** in every replay plus the 8-check integrity
  audit (`provenance_present`, `version_pinned`, `seed_present`,
  `action_log_complete`, `frames_present`, `hp_monotonic`, `result_consistent`).
- `GET /api/benchmark/spec`, `GET /api/integrity/{match_id}`,
  `GET /api/metrics`, `GET /api/status`, `GET /api/export` (json/jsonl/csv).

### Added — match configuration

- **Match lengths** `sprint` (4 turns), `standard` (12), `full` (24).
- **Fallback policies** `strict` (any fallback ⇒ unranked), `operational`
  (default), `demo` (never ranked).
- **Seeds.** A seeded match replays bit-for-bit. LLM decisions are not
  reproducible from a seed; the recorded action log is what makes a published
  result reproducible.
- **Multi-axis voting.** `execution`, `entertainment`, `deserved` and a 1–5
  confidence rating are collected; only the `tactical` vote is ranked.
- **Match cancellation.** `POST /api/match/{mid}/cancel` marks a queued or
  running match cancelled so it is never silently counted.
- **Parallel decisions.** The two fighters' API calls now run concurrently,
  roughly halving per-turn wall clock (`stickblade/main.py:229`).

### Added — integrity & anti-gaming

- `stickblade/anti_gaming.py` scans finished replays for repeated identical
  actions, excessive guarding, permanent retreat, never attacking, edge
  camping, prompt-injection markers, truncated thoughts and high fallback
  rates. Thresholds are published in the module.
- `GET /api/integrity/{match_id}` returns the replay audit **and** the
  anti-gaming verdict together.
- 13 adversarial-input tests: the detectors are fed attacker-controlled data
  and must never raise on garbage input.

### Added — research & ops tooling

- `tools/run_match.py` — one entry point: `spec | simulate | verify | demo`
  plus pass-through `batch | balance | report | export | loadtest`.
- `tools/weapon_balance.py` — mirrored bot-batch balance sweeps with Wilson
  intervals. **Findings:** flail is measurably asymmetric (side-A win rate
  0.19, 95 % CI [0.08, 0.38] excludes 50/50 at n=24); bow and sword are
  provisional at this sample size ([research/balance_report.md](./research/balance_report.md)).
- `tools/export_dataset.py` — public dataset export in JSON / JSONL / CSV
  (+ Parquet when `pyarrow` is present), directly from a live backend or from
  a local `arena.db`, with a `MANIFEST.json` recording counts, date range,
  version triple and licence.
- `tools/benchmark_report.py` — monthly report generator. Sections with no
  input say *not supplied* rather than being silently omitted.
- `tools/load_test.py` — concurrency waves (written; full 25–100 concurrent
  runs still outstanding).
- `tools/simcore.py` — shared headless bootstrap; every battle log now goes to
  `os.devnull` by default instead of littering the working tree.

### Added — frontend

- **Quick Match** as the default path (curated models, one click) with a
  separate **Research** mode that exposes the full configuration, including
  match length, fallback policy and seed.
- **Sample fight** modal (`/public/demo_replay.json`) — a real engine replay
  recorded offline, so the landing page works when the backend is cold.
  Regenerate with `./tools/run_match.py demo`.
- **`/trust`** — what is collected, what is not, BYOK key lifecycle, retention
  and deletion.
- **`/status`** — live service status from `GET /api/status` + `GET /api/metrics`.
- **`/dashboard`** — public dataset dashboard: reliability stats, configuration
  coverage per weapon/arena/mode/length, and the commands to reproduce them.
- **Integrity badge**, **result scorecard** (provenance table + roast),
  **multi-axis vote panel**, **wait panel** with phase/turn/ETA/cancel,
  **share bar** (link, summary, 𝕏, Reddit, embed), **accessibility controls**
  (reduced motion, high contrast, reduced effects), weapon balance markers.
- Shared site nav + footer across every page so the credibility pages are
  reachable from anywhere.
- **Self-hosted fonts.** Inter and Rajdhani now ship via `@fontsource/*`
  through `next/font/local`; the build no longer fetches from
  `fonts.googleapis.com` (also fixes builds that failed when Google Fonts was
  unreachable).

### Fixed

- **Seeded matches were not reproducible.** Two causes: scripted brains drew
  from Python's global RNG while the two fighters decide in concurrent
  threads, and the think phase steps physics once per frame while it waits, so
  thread-scheduling jitter changed the fighters' positions between runs.
  Scripted brains now own a per-instance RNG, and a match between two
  scripted fighters resolves inline instead of in threads
  (`stickblade/brains.py:708`, `stickblade/main.py:229`).
- **Provenance recorded `Fighter A`/`Fighter B` as the model used** in blind
  matches, because the blind rename happens before decisions and scripted
  brains carry no `.model`. Provenance now falls back to the requested roster
  id (`stickblade/main.py:302`).
- Anti-gaming detectors raised on `None` / malformed replay documents; now
  null-hardened throughout.
- The test suite hit production rate limits (`503 arena is busy`) when running
  many offline matches quickly. Fixed in `tests/conftest.py` via env
  overrides — the production caps bound LLM spend and were left alone.
- Battle logs from batch runs are written to `os.devnull` instead of the CWD.

### Changed

- Schema: `supabase_schema.sql` gained the benchmark v1.0 columns plus an
  idempotent migration block and two indexes; `votes` gained the extra axes.
  Both storage backends degrade gracefully (retry without the new columns) so
  an un-migrated deploy keeps running.
- CI: new `test-suite` job runs the pytest suite on Python 3.11 and 3.13 and
  asserts the spec fingerprint is stable; `ci-summary` now depends on it.
- `POST /api/vote` accepts the optional axes and confidence.

### Test suite

117 passing cases across 8 files — spec conformance, physics determinism, API
contracts, Elo math, blind-election integrity, adversarial input, BYOK key
hygiene. Runs in ~35 s with no network and no API key.
