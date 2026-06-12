# ⚔️ STICKBLADE ARENA — LLM vs LLM Physics Sword Duel

Two ragdoll stickmen with human-like joint limits fight a turn-based sword duel
(Toribash-style). Each fighter's brain is an LLM (**GPT** or **Gemini**) — or a
built-in scripted personality so you can play without API keys. **You** decide
which part of the sword is sharpened, and watch how each AI adapts its strategy.

## Quick start (no API keys needed)

```bash
pip install -r requirements.txt
python main.py --p1 berserker --p2 duelist --sharp tip
```

## Real LLM duel

```bash
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
python main.py --p1 gpt --p2 gemini --sharp tip
```

If a key is missing the corresponding slot silently falls back to a mock brain,
so the game always runs. Models can be changed via env vars
`STICKBLADE_OPENAI_MODEL` (default `gpt-4o-mini`) and
`STICKBLADE_GEMINI_MODEL` (default `gemini-2.0-flash`).

## The sharpness twist

`--sharp` accepts any comma-combo of: `tip`, `edge`, `back_edge`, `pommel`.

| Sharp zone | What a smart LLM should figure out |
|---|---|
| `tip` | Slashing is useless — fence with thrusts and lunges |
| `edge` | Classic sabre — overhead & horizontal slashes |
| `back_edge` | Only rising slashes cut — weird and fun |
| `pommel` | A war hammer with extra steps — get to clinch range |

The sharp zones are highlighted **red** on each blade. The sword-zone rules are
written into each LLM's system prompt; everything else they must reason out.

## How a match works

1. **Freeze** — both LLMs get a JSON snapshot (HP, distance, enemy's last
   action, who got hit last turn and with what zone...).
2. Each replies with `{"thought", "action", "footwork"}`.
   Actions: `thrust, overhead_slash, horizontal_slash, rising_slash,
   pommel_strike, guard_high, guard_low, ready` ·
   Footwork: `advance, retreat, lunge, hop_back, hold`.
3. **Unfreeze** — physics runs for 3 seconds, executing both moves via
   joint-servo "muscles" on the ragdolls.
4. Damage = sharp zone × impact speed × body part. A fast **sharp hit to the
   head is an instant kill** (slow-mo + flash). Blunt contact mostly shoves.
5. First to 0 HP loses; after 24 turns the higher HP wins on points.

Every match writes `battle_log_<timestamp>.json` containing each turn's
**full reasoning** from both LLMs plus every hit event — that's your dataset
for comparing model strategies.

## 🏆 Tournament mode

Auto-plays a series of duels and produces a strategy-comparison report:

```bash
# 6 matches per sharpness config, 3 configs = 18 duels, headless & fast:
python tournament.py --p1 gpt --p2 gemini --matches 6 --sharp tip --sharp edge --sharp pommel

# Watch every match in a window instead:
python tournament.py --p1 berserker --p2 duelist --matches 4 --sharp tip --visual

# Mirror match (consistency test) — fighters auto-named #1 / #2:
python tournament.py --p1 gpt --p2 gpt --matches 5 --sharp tip
```

- Sides are **swapped every other match** to cancel spawn-side bias.
- Output goes to `tournaments/<timestamp>/`:
  - `match_<sharp>_<n>.json` — full per-turn reasoning log of each duel
  - `report.md` — human-readable scoreboard & strategy breakdown
  - `report.json` — machine-readable stats for your own analysis
- Per-brain metrics include: wins (kill vs points), damage dealt, sharp/blunt
  hits, **aggression** (% of turns spent attacking), favoured actions &
  footwork, and **sharp-zone alignment** — the % of attack moves whose leading
  sword zone was actually sharp, i.e. did the LLM *understand the weapon*.

## 🎬 Browser replays (web deployment — Phase 1)

Run a match headless and watch it in any browser — no backend needed:

```bash
python record_match.py --p1 berserker --p2 duelist --sharp tip
# -> replays/<name>.html   (self-contained: double-click to watch)
# -> replays/<name>.json   (raw replay data — the future web API payload)
```

The HTML player is a canvas re-implementation of the Pygame renderer:
same dark arena, blood particles & floor stains, sword-clash sparks, damage
numbers, screen shake, slow-mo + flash on lethal hits, thought bubbles, HUD —
plus play/pause, scrubbing, frame-step (`←`/`→`) and 0.25×–2× speed.

This is the heart of the planned web arena ("simulate server-side, replay
client-side"): the same JSON your future FastAPI backend will serve, and the
same player your Next.js frontend will embed.

- `recorder.py` — captures frames/events/thoughts during a headless match
- `viewer_template.html` — the canvas player (replay JSON gets embedded)
- `record_match.py` — CLI: run + record + export in one command

## 🌐 Web arena (FastAPI backend — Phases 3+4)

A complete arena server with blind voting and per-sharpness Elo leaderboards:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

The built-in arena page lets you: pick two fighters → choose sharp zones →
FIGHT → watch the canvas replay → **vote blind** (models hidden as
Fighter A/B) → identities + Elo changes revealed after your vote.

**API:**

| Endpoint | What |
|---|---|
| `GET /api/models` | available fighters (from `ARENA_MODELS` in config) |
| `POST /api/match` | `{model_a, model_b, sharp[], blind}` → queues a headless sim |
| `GET /api/match/{id}` | status; hides model names until voted (blind mode) |
| `GET /api/replay/{id}` | replay JSON for the canvas player |
| `POST /api/vote/{id}` | `{choice: a\|b\|draw}` → Elo update + reveal (one vote/match) |
| `GET /api/leaderboard?sharp=tip` | Elo per sharpness config, or overall |
| `GET /api/recent` | recent matches (names hidden while unvoted) |

**OpenRouter — every model with one key:** get a key at openrouter.ai, then

```bash
export OPENROUTER_API_KEY=sk-or-...
```

`ARENA_MODELS` in `config.py` lists the fighters; ids with `:free`
(Llama 3.3, Mistral, Gemma, DeepSeek) cost **$0**. Any OpenRouter model id
also works in the CLI: `python main.py --p1 meta-llama/llama-3.3-70b-instruct:free --p2 mock:duelist`.
Without a key everything still runs on mock brains.

**Storage:** `storage.py` (SQLite + replay files in `arena_data/`) — the
interface is the contract for the future Supabase drop-in (Phase 5).
Elo is tracked **separately per sharpness config**: "best fencer (tip)" and
"best brawler (pommel)" are different leaderboards.

## Controls

| Key | Effect |
|---|---|
| `SPACE` | pause |
| `F` | fast-forward 3× |
| `R` | rematch (fresh brains) |
| `ESC` | quit |

## Files

- `main.py` — game loop, turn state machine, match setup
- `tournament.py` — multi-match runner + strategy report generator
- `ragdoll.py` — physics bodies, joint limits, servo muscles, balance
- `moves.py` — macro move keyframe library
- `combat.py` — sword-zone classification + damage model
- `brains.py` — GPT / Gemini / mock brains, prompt & state builder
- `render.py` — Toribash-style rendering, blood, FX, HUD
- `config.py` — all tunables (damage, pacing, colors, models)
- `test_headless.py` — run a windowless smoke-test match

## Tuning tips

- Turn length: `TURN_SECONDS` in `config.py` (3s default).
- Make fights bloodier: raise `DMG_SCALE`, lower `KILL_HEAD_SPEED`.
- Joint-level control mode (true Toribash, LLM sets every joint) is the
  planned next phase — the `Servo` API in `ragdoll.py` is already built for it.

## ☁️ Persistence & deployment (Phases 5+7)

- `storage_supabase.py` — Supabase drop-in (auto-activated by env vars
  `SUPABASE_URL` + `SUPABASE_KEY`; otherwise local SQLite is used)
- `supabase_schema.sql` — run once in the Supabase SQL editor
- `Dockerfile` — ready for Hugging Face Spaces / Render / Railway
- **`DEPLOY.md` — the full $0 deployment guide (start here)**

## 🧠 Control modes (the original two-mode plan — both built)

| | 🎯 MACRO (tactician) | 🧠 JOINT (raw nervous system) |
|---|---|---|
| LLM outputs | one action + footwork (`thrust`, `guard_high`, …) | a state for **all 10 joints**: `flex` / `extend` / `hold` / `relax` |
| Engine does | plays keyframed move via joint servos | drives each joint to its human limit / locks / goes floppy |
| Looks like | actual sword fighting | emergent, chaotic, true Toribash |
| Measures | tactical reasoning & weapon-rule adaptation | raw spatial/embodied reasoning (much harder for LLMs) |

Everywhere you can pick it:

```bash
python main.py         --p1 gpt --p2 gemini --sharp tip --mode joint
python record_match.py --p1 mock:duelist --p2 mock:berserker --mode joint
# web: the MACRO / JOINT toggle in the fight panel (both built-in page & Next.js)
# API: POST /api/match {"mode": "joint", ...}
```

Implementation: `joint_mode.py` (JointController, joint system prompt,
sanitizer, MockJointBrain). Balance assist and footwork remain active in
joint mode — without them every duel is pure floor-flopping.
