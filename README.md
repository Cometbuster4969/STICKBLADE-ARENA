---
title: Stickman Arena
emoji: ⚔️
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
---

# ⚔ STICKBLADE ARENA

[![CI](https://github.com/Cometbuster4969/STICKBLADE-ARENA/actions/workflows/ci.yml/badge.svg)](https://github.com/Cometbuster4969/STICKBLADE-ARENA/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Live demo](https://img.shields.io/badge/live-stickblade--arena.vercel.app-red)](https://stickblade-arena.vercel.app)
[![Featured on pymunk](https://img.shields.io/badge/featured-pymunk%20showcase-8b5cf6)](https://www.pymunk.org/en/latest/showcase.html#stickblade-arena)

> 🏆 **Featured on the [Official Pymunk Showcase](https://www.pymunk.org/en/latest/showcase.html#stickblade-arena) (Non-Games)** — praised by library creator [@viblo](https://github.com/viblo): *"I think it's a very cool project!"* → [#5](https://github.com/Cometbuster4969/STICKBLADE-ARENA/issues/5)
>
> 🥉 **Product of the Day (Bronze)** on [PeerPush](https://peerpush.com/p/stickblade-arena)
>
> 🤖 Cited by Google's AI Overview as *"a brilliant example of gamified AI evaluation"*

**A physics-based LLM benchmark where two language models sword-fight and humans vote blind on who fought smarter.**

Two models are dropped into a deterministic 2D pymunk arena with a sword, a
flail, a bow, a dagger or a spear. They trade turns through a constrained
action interface. A human watches the fight **without knowing which model is
which**, votes on who fought better, and only then sees the names. Every match
ships a provenance record — spec version, physics version, prompt version,
seed, and the full action log — so any published result can be re-run and
audited.

```
model A (blind)  ──▶  action JSON  ──▶  pymunk physics  ──▶  replay
model B (blind)  ──▶  action JSON  ──▶                        │
                                                              ▼
                                             human votes "Fighter A won"
                                                              │
                                        reveal ─▶ Elo update (6 eval cells)
```

**Live:** [stickblade-arena.vercel.app](https://stickblade-arena.vercel.app) ·
backend `https://pioneer37-stickman-arena.hf.space` ·
[cite this project](./CITATION.cff)

---

## Why blind voting

Leaderboards that ask a model to grade itself, or that reveal identities
before the vote, measure brand recognition. Here the canvas shows hatch
patterns and "Fighter A / Fighter B"; the model names are withheld from every
pre-vote payload (`/api/match`, the live stream, the blind replay) and are
only attached after the vote is cast. That is the whole point of the project,
and it is enforced by tests (`tests/test_blind_identity.py`), not by policy.

## Benchmark specification v1.0 (frozen)

| Field | Value |
|---|---|
| Benchmark version | `1.0` |
| Physics version | `1.0` |
| Prompt version | `2` (v1 → v2 on 2026-09-08, soft cutover — see AGENTS.md §10.5) |
| Spec fingerprint | `09de66effd02` (prompt v2) · `029281ed627a` (prompt v1 rows) |
| Match lengths | `sprint` 4 turns · `standard` 12 · `full` 24 |
| Fallback policies | `strict` (exclude on fallback) · `operational` (default) · `demo` (never ranked) |
| Rating | Elo, K=32, start 1000, 6-key cell: model × sharp zone × weapon × mode × arena × blindfolded |

The fingerprint is a hash of the frozen spec document
(`stickblade/benchmark.py`). Every replay stores it; a replay whose
fingerprint does not match the running server is reported as unverifiable
rather than silently trusted. Print it with:

```bash
cd stickblade && python3 benchmark.py --fingerprint
```

Full human-readable spec: **[docs/BENCHMARK_SPEC.md](./docs/BENCHMARK_SPEC.md)**.
Methodology, threats to validity and the honest limits of the numbers:
**[METHODOLOGY.md](./METHODOLOGY.md)**.

## Quickstart

**Run the backend** (needs Python 3.11+, SDL libs for pygame):

```bash
cd stickblade
pip install -r requirements.txt
SDL_VIDEODRIVER=dummy uvicorn server:app --reload      # http://localhost:8000
curl localhost:8000/api/health
curl localhost:8000/api/version        # spec + prompt version
curl localhost:8000/api/benchmark/spec # the whole frozen spec as JSON
```

Without `OPENROUTER_API_KEY` or `GROQ_API_KEY` the arena still runs — every
fight falls back to scripted baselines (`mock:*`, `bot:*`) and is flagged as
such in its provenance.

**Run the frontend:**

```bash
cd stickblade-web
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

**Run a match with no server, no network, no keys** — the single entry point
for every offline tool:

```bash
./tools/run_match.py spec                       # print the frozen spec
./tools/run_match.py simulate --a mock:duelist --b bot:pro --seed 42
./tools/run_match.py verify public/demo_replay.json
./tools/run_match.py demo                       # regenerate the landing-page fight
./tools/run_match.py balance --n 30 --md-out research/balance_report.md
./tools/run_match.py export --out-dir research/exports/ --all-formats
./tools/run_match.py report --export research/exports/x.json --period 2026-09
```

See **[tools/README.md](./tools/README.md)** for the full tool inventory.

## Repository layout

```
stickblade/         backend: physics, brains, Elo, FastAPI server, SQLite/Supabase storage
  benchmark.py      THE frozen spec + provenance/eligibility/verification helpers
  anti_gaming.py    replay forensics (exploit + degenerate-play detectors)
stickblade-web/     Next.js 15 / React 19 frontend
tests/              117 pytest cases — spec, physics, determinism, API, Elo,
                    blind integrity, adversarial input, BYOK key hygiene
tools/              offline research + ops CLIs (run_match.py is the entry point)
research/           published datasets, balance sweeps, correlation study, reports
docs/               long-form documentation (benchmark spec, …)
```

## Testing and CI

```bash
python3 -m pytest tests -q          # ~35 s, no network, no API key required
```

GitHub Actions runs 7 jobs on every push: backend smoke across Python
3.11/3.12/3.13, the pytest suite, frontend build + JSX balance, security
(bandit + dependency audit), link check, and roster consistency. The suite is
headless (`SDL_VIDEODRIVER=dummy`) and touches no provider.

## Documentation

| Document | What it covers |
|---|---|
| [docs/BENCHMARK_SPEC.md](./docs/BENCHMARK_SPEC.md) | The frozen spec in prose: what is measured, what is ranked, what is excluded |
| [docs/API.md](./docs/API.md) | Every HTTP endpoint, which ones are safe before the vote, end-to-end example |
| [docs/ENVIRONMENT.md](./docs/ENVIRONMENT.md) | Every environment variable and its default |
| [docs/LOCAL_DEV.md](./docs/LOCAL_DEV.md) | Local setup, the offline tool inventory, troubleshooting |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Backend (Docker/HF Spaces) and frontend (Vercel), storage, post-deploy checks |
| [METHODOLOGY.md](./METHODOLOGY.md) | Rating model, threats to validity, empirical status of our claims |
| [AGENTS.md](./AGENTS.md) | How to work in this repo (reading order, citation rule, anti-sycophancy protocol) |
| [TIMELINE.md](./TIMELINE.md) | What shipped, what's queued, what we deliberately killed and why |
| [CHANGELOG.md](./CHANGELOG.md) | What changed, and which benchmark version it invalidated |
| [research/DATA_LICENSE.md](./research/DATA_LICENSE.md) | Match data licensing (CC-BY-SA 4.0) |
| [examples/](./examples/README.md) | A minimal bot you can copy, plus the match fixtures |
| [CONTRIBUTING.md](./CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) · [SECURITY.md](./SECURITY.md) | Working on the project |

## Known limitations (read before quoting any number)

- **Sample sizes are small.** This is a solo project on free tiers. Leaderboard
  rows carry Wilson confidence intervals and a `provisional` flag; treat any
  row with fewer than ~30 matches as a signal, not a result.
- **Flail is asymmetric.** On a mirrored bot batch (n=24) side B wins ~81% of
  flail matches — the 95% interval excludes 50/50, so the configuration, not
  the model, is deciding those fights. Flail is labelled `asymmetric` in
  `/api/weapons` and in the UI; do not read flail matches as a like-for-like
  comparison. Details in [research/balance_report.md](./research/balance_report.md).
- **LLM decisions are not reproducible from a seed.** Physics and scripted
  baselines are (verified bit-for-bit in tests); model outputs are not. What
  is reproducible is everything around them — the action log records exactly
  what each model chose, so a replay can be re-simulated deterministically.
- **Cross-benchmark correlation is currently a null result.** See
  [research/cross_benchmark_correlation_report_2026-08-04.md](./research/cross_benchmark_correlation_report_2026-08-04.md).

## License

Code is **Apache-2.0** ([LICENSE](./LICENSE)). Match data exported via
`/api/export` and published snapshots are **CC-BY-SA 4.0**
([research/DATA_LICENSE.md](./research/DATA_LICENSE.md)). Built and maintained
by [@Cometbuster4969](https://github.com/Cometbuster4969).
