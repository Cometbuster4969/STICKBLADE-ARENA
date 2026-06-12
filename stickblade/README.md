# ⚔️ STICKBLADE ARENA — Engine & Server

Two ragdoll stickmen with human-like joint limits fight turn-based duels
(Toribash-style). Each fighter's brain is an LLM — or a built-in scripted
personality so everything runs without API keys. **You** pick the weapon and
decide which zones are dangerous; the AIs must adapt their strategy.

## Quick start

```bash
pip install -r requirements.txt

# desktop duel (mock AIs, no keys):
python main.py --p1 mock:berserker --p2 mock:duelist --weapon sword --sharp tip

# web arena (http://localhost:8000):
uvicorn server:app --port 8000
```

## LLM fighters

One OpenRouter key unlocks 100+ models, including free ones:

```bash
export OPENROUTER_API_KEY=sk-or-...      # openrouter.ai — free signup
python main.py --p1 meta-llama/llama-3.3-70b-instruct:free \
               --p2 openai/gpt-oss-120b:free --weapon flail --sharp spikes
```

Valid fighter ids anywhere (CLI, API, web menus):

| Kind | Example |
|---|---|
| Any OpenRouter model | `qwen/qwen3-coder:free`, `openai/gpt-4o-mini` |
| Mock (no API) | `mock:duelist`, `mock:berserker` |
| Direct APIs (legacy) | `gpt` (`OPENAI_API_KEY`), `gemini` (`GEMINI_API_KEY`) |

Missing key → that slot silently falls back to a mock brain; the game always
runs. The web dropdown roster lives in `ARENA_MODELS` in `config.py`.

## ⚔ Weapons & the danger-zone twist

Both fighters use the same weapon per match; you choose which zones hurt
(`--sharp`, comma-separated). Everything else is blunt shoving.

| Weapon | Zones | Playstyle |
|---|---|---|
| 🗡 `sword` | `tip`, `edge`, `back_edge`, `pommel` | classic dueling — tip-only forces fencing, pommel-only forces clinch brawling |
| ⛓ `flail` | `ball`, `spikes`, `chain`, `handle` | momentum weapon with real chain physics; **spikes = the ball at high speed** (spin_up first!) |
| 🏹 `bow` | `arrowhead`, `arrow_shaft`, `bow_limb` | ranged kiting; ballistic arrows with gravity-drop compensation; `bow_limb` = melee club |

Actions per weapon
- sword: `thrust, overhead_slash, horizontal_slash, rising_slash, pommel_strike, guard_high, guard_low, ready`
- flail: `spin_up, overhead_smash, wide_swing, yank_back, handle_jab, guard_*, ready`
- bow: `draw_shot` (slow/strong), `quick_shot` (fast/weak), `high_arc_shot` (lob), `bow_bash`, `guard_*`, `ready`

Dangerous zones glow **red** on the weapon. The zone rules are written into
each LLM's system prompt; the strategy is up to the model.

## 🧠 Control modes

| | 🎯 MACRO (`--mode macro`, default) | 🧠 JOINT (`--mode joint`) |
|---|---|---|
| LLM outputs | one action + footwork per turn | a state for all 10 joints: `flex / extend / hold / relax` |
| Looks like | actual weapon fighting | emergent, chaotic, true Toribash |
| Measures | tactical reasoning & weapon-rule adaptation | raw spatial/embodied reasoning |

## How a match works

1. **Freeze** — both LLMs get a JSON state (HP, distance, enemy's last action,
   last turn's hits with zones…).
2. Each replies with `{"thought", "action"/"joints", "footwork"}`.
   Footwork: `advance, retreat, lunge, hold, hop_back`.
3. **Unfreeze** — physics runs 3 s, executing both moves via joint-servo
   "muscles".
4. Damage = dangerous zone × impact speed × body part. A fast dangerous-zone
   **headshot is an instant kill** (slow-mo + flash).
5. First to 0 HP loses; after 24 turns the higher HP wins on points.

Every match writes a JSON log with both models' full per-turn reasoning and
every hit event — your dataset for comparing strategies.

## 🌐 Web arena server

```bash
uvicorn server:app --port 8000        # open http://localhost:8000
```

Built-in page: model dropdowns (+ custom OpenRouter id), 🗡/⛓/🏹 weapon
selector with auto-updating zone pills, MACRO/JOINT toggle, canvas replay
player, **blind voting** (names revealed after your vote), live Elo
leaderboard per sharpness config.

| Endpoint | What |
|---|---|
| `GET /api/models` · `GET /api/weapons` | available fighters / weapons+zones |
| `POST /api/match` | `{model_a, model_b, weapon, sharp[], mode, blind}` → queue sim |
| `GET /api/match/{id}` | status; names hidden while blind+unvoted |
| `GET /api/replay/{id}` | replay JSON for the canvas player |
| `POST /api/vote/{id}` | `{choice: a\|b\|draw}` → Elo update + reveal |
| `GET /api/leaderboard?sharp=tip` | Elo per config, or overall |
| `GET /api/recent` | recent matches |

**Storage:** local SQLite by default; set `SUPABASE_URL` + `SUPABASE_KEY`
for persistent cloud storage (schema in `supabase_schema.sql`).

**Security (on by default, env-tunable):** per-IP rate limits
(`RL_MATCHES_PER_HOUR=6`, `RL_VOTES_PER_HOUR=30`, `RL_REQS_PER_MIN=120`),
global daily cap (`MAX_MATCHES_PER_DAY=300`), queue backpressure
(`MAX_QUEUE=10`), custom model ids restricted to `:free`
(`ALLOW_PAID_CUSTOM=1` to lift), strict id validation, docs disabled,
security headers, one vote per match.

## 🎬 Replays

```bash
python record_match.py --p1 mock:duelist --p2 mock:berserker \
                       --weapon bow --sharp arrowhead --mode macro
# -> replays/<name>.html   self-contained, double-click to watch
# -> replays/<name>.json   raw replay data (what the web API serves)
```

The canvas player (play/pause, scrub, frame-step, 0.25–2× speed) re-creates
the full visual experience: blood, sparks, damage numbers, screen shake,
slow-mo lethal hits, thought bubbles.

## 🏆 Tournament mode

```bash
python tournament.py --p1 gpt --p2 gemini --matches 6 \
                     --weapon sword --sharp tip --sharp edge --sharp pommel
```

Auto-plays N matches per sharpness config (sides swapped to cancel bias),
writes `tournaments/<ts>/report.md` + `report.json` with per-brain stats:
wins (kill vs points), damage, sharp/blunt hits, **aggression %**, favoured
actions/footwork, and **sharp-zone alignment %** — did the model actually
understand the weapon rules? Add `--visual` to watch live.

## Desktop controls

`SPACE` pause · `F` 3× fast-forward · `R` rematch · `ESC` quit

## Files

| File | Role |
|---|---|
| `config.py` | every tunable: damage, pacing, colors, model roster |
| `ragdoll.py` | bodies, joint limits, servo muscles, balance |
| `weapons.py` | sword/flail/bow builders, zones, arrow manager |
| `moves.py` | macro move keyframe library (all weapons) |
| `joint_mode.py` | raw joint control mode + its prompt + mock |
| `combat.py` | weapon-aware zone classification + damage model |
| `brains.py` | OpenRouter/GPT/Gemini/mock brains, prompts, state builder |
| `main.py` | Match state machine + desktop game |
| `render.py` | Pygame renderer + FX |
| `recorder.py` / `viewer_template.html` / `player.js` | replay pipeline (player.js is mirrored to `../stickblade-web/public/`) |
| `server.py` / `security.py` / `storage.py` / `storage_supabase.py` | web arena backend |
| `arena_page.html` | built-in single-file web UI |
| `tournament.py` / `record_match.py` | research & replay CLIs |
| `test_headless.py` / `test_phases.py` | smoke tests — run after engine edits |
| `Dockerfile` / `supabase_schema.sql` / `DEPLOY.md` | deployment |

## Tuning tips

- Pace: `TURN_SECONDS`, `MAX_TURNS` in `config.py`
- Gore: raise `DMG_SCALE`, lower `KILL_HEAD_SPEED`
- Flail spike threshold: `SPIKE_SPEED` in `weapons.py`
- Joint-mode floppiness: `FLEX_POWER`, `DRIVE_FRACTION` in `joint_mode.py`
- Visual changes: edit `render.py` **and** `player.js`, then
  `cp player.js ../stickblade-web/public/player.js`

## Deployment

See **[DEPLOY.md](DEPLOY.md)** — full $0 walkthrough:
Supabase (DB) → OpenRouter (LLMs) → Hugging Face Spaces (this server, Docker)
→ Vercel (the `../stickblade-web` frontend).
