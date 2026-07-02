---
title: Stickman Arena
emoji: ⚔️
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
---

# ⚔ STICKBLADE ARENA

**A physics-driven benchmark for LLM reasoning, creativity, and real-time decision-making — disguised as a Toribash-style stick-figure sword duel.**

Two large language models step into a 2D physics arena. You decide what part of the weapon is sharp. They fight blind. Physics decides who actually dies. You vote without knowing which model is which. Their Elo updates. Over time, the leaderboard tells you which model is the most *tactically creative* swordsman — separately from how it codes, chats, or writes essays.

🌐 **Live:** [stickblade-arena.vercel.app](https://stickblade-arena.vercel.app)
🛠 **Backend:** FastAPI + pymunk on Hugging Face Spaces
🎨 **Frontend:** Next.js 15 on Vercel

---

## 📑 Table of Contents

- [Why this is actually a useful LLM benchmark](#-why-this-is-actually-a-useful-llm-benchmark)
- [What's tested (and how it's different from MMLU et al.)](#-whats-tested-and-how-its-different-from-mmlu-et-al)
- [Key features](#-key-features)
- [How a match works](#-how-a-match-works-end-to-end)
- [Game modes](#-game-modes)
- [Weapons & sharp zones](#-weapons--sharp-zones)
- [Arena modifiers](#-arena-modifiers)
- [Tournaments](#-tournaments)
- [Architecture](#-architecture)
- [REST API (quick reference)](#-rest-api-quick-reference)
- [Running locally](#-running-locally)
- [Adding new models](#-adding-new-models)
- [Tech stack](#-tech-stack)
- [Roadmap](#-roadmap)

---

## 🧠 Why this is actually a useful LLM benchmark

Most LLM benchmarks test **static, closed-form** problems — multiple-choice trivia (MMLU), code completion (HumanEval), single-turn chat (MT-Bench). A model can ace them by pattern-matching against its training data.

**Stickblade Arena tests the opposite axis: open-ended, real-time tactical reasoning under physical constraints, judged by human eyes.** It probes capabilities that don't reliably show up in any standardized test:

### 1. Real-time decision-making under partial information

Every 3 simulated seconds, the model gets a tightly compressed JSON snapshot of the world and has to commit to one action *and live with the physical consequences*. It can't redraft, it can't apologize, it can't say "let me think again."

```jsonc
{
  "turn": 4, "turns_left": 20, "my_hp": 67.3, "enemy_hp": 80.1,
  "distance": 142,
  "me":     { "torso":[412,150], "head":[412,191], "weapon_tip":[461,180],
              "facing":  1, "velocity":[ 30, -2] },
  "enemy":  { "torso":[554,150], "head":[554,193],
              "facing": -1, "velocity":[-18,  4] },
  "relative": {
    "dx": 142, "dy": 0, "enemy_is": "right", "facing_enemy": true
  },
  "ranged_hint": { "arrow_flight_time_s": 0.20,
                   "vertical_drop_to_compensate": 24,
                   "aim_at_enemy_head": [554, 193] },
  "enemy_last_action": "guard_high",
  "my_last_action":    "thrust",
  "last_turn_hits":    [ {"by":"enemy", "zone":"edge",
                          "damage":4.1, "was_sharp":false} ]
}
```

The model must answer in under ~15 seconds with a single JSON action. What we measure:

- **Spatial reasoning** — can the model interpret `relative.dx`, `velocity`, and `facing_enemy` and decide whether to advance, retreat, or commit? Tiny models often pick actions that miss because they're facing the wrong way.
- **Plan continuity** — its previous action (`my_last_action`) and the enemy's response (`enemy_last_action`) demand multi-turn coherence. Random play loses against any model with a 2-turn windup → strike loop.
- **Constraint satisfaction** — only zones the user marked as "sharp" do real damage. A model that always swings the *edge* against a "tip-only" duel will lose every fight.
- **Recovery from failure** — when knocked down (`my_height: "knocked_down"`), can it switch from offense to defense?

### 2. Creativity — measured by *outcome*, not by *prose*

We don't ask the model to *write about* a strategy. We watch it execute one in a deterministic physics simulator and *count the lethal hits.* Every match produces emergent behavior:

- A bow fighter that **leads the target with arrow drop compensation**, vs one that blindly shoots straight.
- A flail fighter that **whirls for 2 turns to build spike-speed momentum** before swinging, vs one that smashes immediately and bounces off.
- A dagger fighter that **lunges aggressively into clinch range**, knowing its reach is tiny, vs one that gets out-reached.
- A spear fighter that **maintains the 120–180 px kill zone** vs one that lets the enemy walk past the spike.

Two models given the *same* state can produce wildly different tactical doctrines. The Elo leaderboard, segmented per weapon and per sharp-zone, exposes which models develop coherent, situationally-aware playstyles vs which just thrash around.

### 3. Two control modes — strategic vs motor

| Mode | What the LLM controls | What we test |
|---|---|---|
| **MACRO** | Picks one of 7 named tactical moves (`thrust`, `overhead_slash`, `lunge`, etc.) per turn | High-level **strategic** decision-making |
| **JOINT** | Sets a state (`flex`/`extend`/`hold`/`relax`) for *every single joint* — like Toribash | Raw **motor planning** + understanding of biomechanics |

Strong models on MACRO are sometimes terrible at JOINT — they understand chess-like moves but can't compose "extend shoulder + flex elbow" into a coherent swing. JOINT mode is *much* more emergent and often produces the most surprising kills (and the most spectacular faceplants).

### 4. Blind, unbiased human evaluation

After each duel:

- Both fighters are labeled only **Fighter A** and **Fighter B**
- Which model becomes the **green** vs **blue** ragdoll is **randomized server-side per match** — even the person who set up the fight can't tell which slot is which
- You vote on who fought better (form, tactics, kills) — *not* on the model name
- After the vote, the reveal shows which model was which and updates their Elo

This eliminates brand-recognition bias. A vote for "the green fighter who landed three clean thrusts" stays valid whether that turned out to be GPT-OSS, Qwen3, or DeepSeek R1.

### 5. Asymmetric, weapon-specific Elo

A model's overall benchmark score can hide huge skill gaps. We track Elo separately per `(model, weapon, sharp-zone)` triple. So "DeepSeek R1 the fencer" and "DeepSeek R1 the bowman" rank independently. You quickly discover that:

- Reasoning-heavy models (DeepSeek R1) often win at *macro* sword play but are too slow for *bow* snap-shots.
- Small models (Llama 3.2 3B) survive surprisingly well at *clinch-range dagger* fights where reach matters more than reasoning depth.
- Some models develop a *signature zone* — winning consistently with sharp pommel hits (brawler style) while losing with sharp tips (fencer style).

This is **a behavioural benchmark, not a knowledge benchmark.** It reveals capability dimensions Vibes-Bench and MMLU simply don't see.

---

## 📋 What's tested (and how it's different from MMLU et al.)

| Capability | Standard benchmarks | Stickblade Arena |
|---|---|---|
| Static knowledge | ✅ MMLU, ARC | not tested |
| Code synthesis | ✅ HumanEval, SWE-bench | not tested |
| Multi-turn coherence | ❌ mostly single-turn | ✅ 24 turns of state continuity |
| Real-time deadline | ❌ no time budget | ✅ ≤15 s per turn or you forfeit |
| Spatial reasoning | partial (math word problems) | ✅ continuous 2D physics, must reason about velocity vectors |
| Constraint satisfaction | partial | ✅ only specific zones do damage; must adapt strategy |
| Creativity scored by outcome | ❌ judged by prose | ✅ judged by who lands kills |
| Adversarial pressure | ❌ opponent is fixed | ✅ opponent is *another LLM also adapting* |
| Blind human eval | partial (Chatbot Arena) | ✅ + server-side identity scramble |
| Embodied / motor planning | ❌ | ✅ JOINT mode |

If a model is bad at this, it tells you something MMLU never could — that it can't sustain a multi-turn plan in an evolving environment.

---

## ✨ Key features

- **Two control modes:** MACRO (named tactical actions) and JOINT (raw per-joint flex/extend/relax, Toribash-style)
- **Five weapons:** 🗡 sword · 🔪 dagger · ⊥ spear · ⛓ flail · 🏹 bow (with real arrow ballistics + lead compensation)
- **Sharp zones — the twist:** you choose what part of the weapon damages. Same weapon, completely different fight when only the *back edge* is sharp.
- **Arena modifiers:** ❄ ice floor (low friction + reduced air-drag, LLMs told about it) · 🌙 low gravity (moon-ish)
- **Blind voting:** A/B labels with server-side green↔blue randomization, so identity never leaks from the picker
- **Per-weapon, per-zone Elo leaderboards:** track who's a fencer vs a brawler vs a bowman
- **Pre-fight trash talk + post-fight roast:** each model throws a one-liner before the fight; a third commentator LLM roasts the loser afterward (only revealed after voting)
- **Live wait screen** (no more staring at spinner dots):
  - Trash-talk quips surface **within ~5-15s** of hitting Fight
  - **Queue position** — "3 fights ahead of you"
  - **Spoiler-safe combat ticker** — `turn 05 · A:draw_shot vs B:high_arc_shot ◆ B→torso 20.8dmg SHARP` scrolls in as each turn finalizes server-side
  - **Head-to-head card** — "Llama is 2-1 in previous duels vs Qwen"
  - Recent-duels feed clickable to any other user's match
- **Predict-then-watch streaks:** call the winner before voting, track your prediction streak in localStorage
- **Killcam:** auto-slow-motion replay of the lethal blow at match end, with cinematic letterbox bars
- **Synthesized sound FX:** WebAudio sword clangs, blunt thuds, lethal hit-stop chime — zero asset hosting, CSP-clean
- **Tournaments:** 4- or 8-model single-elim brackets with live bracket viewer, auto-advance, champion card
- **Resilient LLM layer** — per-model 429 circuit breaker, provider-diverse buddy failover, per-model reasoning policy (`gpt-oss` handled as mandatory-reasoning, `gemma-4`/`nemotron` disabled via `enabled: false`, vanilla models get no reasoning param), and a scripted-fallback banner if the LLMs error out mid-match
- **Debug endpoints** (`/api/debug/brain_errors`, `/api/debug/cooldowns`, `/api/debug/openrouter_ping`) so you can see exactly why a match fell back without hunting through Space logs
- **Spectator-friendly replay system:** every match saved as a tiny JSON; share-link plays back deterministically in-browser
- **21+ free OpenRouter models** in the picker out of the box — bring your own `OPENROUTER_API_KEY` and you're done

---

## 🥊 How a match works (end-to-end)

```
                            ┌────────────────────────────────────┐
USER          ──pick──►     │  /api/match { model_a, model_b,    │
   sets weapon, zones,      │              sharp[], weapon,       │
   arena, mode              │              arena, mode }          │
                            └──────────────┬─────────────────────┘
                                           │
                                           ▼
                            ┌────────────────────────────────────┐
                            │ server.run_simulation(mid)         │
                            │                                    │
                            │  1. random flip ←─ blind safety    │
                            │  2. spawn 2 fighters with chosen   │
                            │     weapon + arena                 │
                            │  3. pre_fight_quip() for each      │
                            │     → published to LIVE_STATE      │
                            │       instantly (visible ~5-15s)   │
                            │  4. loop turns:                    │
                            │     a. build_state(...)            │
                            │        (includes arena modifier)   │
                            │     b. both brains decide(state)   │
                            │        - retry ladder w/ 429       │
                            │          circuit breaker + buddy   │
                            │          failover on throttle      │
                            │     c. JointController/Move        │
                            │        Controller for 3 s of phys  │
                            │     d. CombatSystem resolves hits, │
                            │        records events              │
                            │     e. recorder.tick()             │
                            │     f. publish blind tick to       │
                            │        LIVE_STATE (ticker feed)    │
                            │  5. commentator_roast()            │
                            │  6. finish_match() → SQLite/Postgres│
                            │     (Elo via atomic Postgres RPC)  │
                            └──────────────┬─────────────────────┘
                                           │
USER         ◄──poll────────  /api/match/{mid}  ◄──── .live { quips,
   1.5s poll while running    (.live populated while       queue_pos,
   → WaitPanel renders         status ∈ queued|running)     log[],
   quips + queue + ticker                                   turn }
   + H2H card + recents                    │
                                           ▼
                       canvas <player.js>  replay + sound + killcam
                                           │
USER  ──vote──►        /api/vote/{mid}     → reveal + Elo deltas
   predict streak                          + commentator's roast
                                           │
                                           ▼
                                     canvas_a_model /
                                     canvas_b_model +
                                     names[] map
                                     (used by main page
                                      AND /replay?id=…
                                      after this fix)
```

A match takes ~20-60 seconds of wall-clock time for a typical 6-turn fight, dominated by the LLMs' thinking time (the physics runs at simulated 60 fps and produces ~3000-5000 frames of replay JSON, gzipped to a few kilobytes). While it's running, the wait screen streams pre-fight quips, queue position, and a spoiler-safe combat ticker — so the user is watching the fight unfold as text before the animated replay is ready.

---

## 🎯 Game modes

### MACRO mode (default, recommended for first-time models)

The LLM picks one tactical move per turn from a weapon-specific list:

| Weapon | Actions |
|---|---|
| sword / dagger | thrust, overhead_slash, horizontal_slash, rising_slash, pommel_strike, guard_high, guard_low, ready |
| spear | thrust, overhead_slash, horizontal_slash, rising_slash, pommel_strike, guard_high, guard_low, ready |
| flail | spin_up, overhead_smash, wide_swing, yank_back, handle_jab, guard_high, guard_low, ready |
| bow | draw_shot, quick_shot, high_arc_shot, bow_bash, guard_high, guard_low, ready |

Plus one of `advance / retreat / lunge / hop_back / hold` for footwork. The engine animates the named keyframe and runs physics for 3 s. **Strategic** test.

### JOINT mode — true Toribash

The model controls every joint as `flex` (drive to positive limit), `extend` (negative limit), `hold` (lock current angle), or `relax` (go floppy). Plus footwork.

```json
{
  "thought": "Wind up — coil the sword arm, then release.",
  "joints": {
    "shoulder": "extend", "elbow": "flex", "grip": "hold",
    "off_shoulder": "extend", "off_elbow": "flex",
    "hip_f": "flex", "knee_f": "flex", "hip_b": "hold", "knee_b": "hold",
    "neck": "hold"
  },
  "footwork": "advance",
  "fire": false
}
```

For bows, set `"fire": true` to release an arrow during the turn. **Embodied / motor** test. Often produces wildly chaotic but mesmerizing fights.

---

## 🗡 Weapons & sharp zones

The "sharp zone" mechanic is the secret sauce of the benchmark. The same weapon plays *completely differently* based on what part you mark dangerous.

| Weapon | Zones | Reach | Notes |
|---|---|---|---|
| **sword** | tip · edge · back_edge · pommel | medium | the baseline |
| **dagger** | tip · edge · back_edge · pommel | short | half-length, lighter, faster recovery — must clinch |
| **spear** | tip · shaft · butt | very long | thrust kingdom at 120-180 px; clinch is death |
| **flail** | ball · spikes · chain · handle | medium | momentum weapon — `spin_up` then strike; `spikes` only counts at high speed |
| **bow** | arrowhead · arrow_shaft · bow_limb | ranged | unlimited arrows; needs lead + drop compensation; `bow_limb` is melee fallback |

A model that's great at "sword + sharp tip" (a fencer's game) may be terrible at "sword + sharp pommel" (a brawler's game requiring grip flips and hilt strikes). Each combination gets its own Elo cell.

---

## 🏟 Arena modifiers

- **Normal** — standard physics, stone floor (friction = 1.5, damping = 0.99).
- **❄ Ice** — floor friction × 0.10, shin friction knocked down to 0.2 (so contact friction actually drops ~9×), AND global space damping bumped to 0.996 so slides last ~2× longer than normal. Lunges over-shoot, hop-backs slide further, and — critically — **the LLMs are told about it** via a state.arena field and a system-prompt paragraph, so a well-tuned model will prefer `advance`/`hold` over `lunge` on ice.
- **🌙 Low gravity** — y-gravity × 0.35 — bigger arcs, slower falls. Brutal for spear thrusts and bow arcs (which now drop less). Models that assume Earth-normal ballistics suddenly miss every shot. Also surfaced in the state payload + system prompt.

---

## 🏆 Tournaments

A 4- or 8-model **single-elimination bracket** runs every match through the same simulator. Standard seeding (#1 vs #N, #2 vs #N-1, etc.) so top seeds can't meet until the final. Live bracket viewer auto-polls and updates round-by-round. Winner gets a gold champion card.

This is the best way to compare *many* models head-to-head quickly, and to discover surprising matchups (small open-source models sometimes upset top-seeded frontier ones because they have a tighter motor-control pattern that the bigger model "overthinks").

---

## 🧬 Architecture

```
┌─────────────────────────── stickblade/ (Python backend) ──────────────────────────┐
│  server.py        FastAPI: REST + worker queues (matches + tournaments)            │
│                   + LIVE_STATE for the wait-screen ticker (quips/queue/log)        │
│                   + /api/debug/* (brain_errors, cooldowns, openrouter_ping)        │
│                   + /api/head_to_head?a=X&b=Y                                      │
│  main.py          Match: orchestrates 24-turn fight (think → sim → resolve)        │
│                   arena-aware physics (ice damping + shin friction override)       │
│  brains.py        Brain hierarchy: Mock, GPT, Gemini, OpenRouter + chat() shim     │
│                   + 429 circuit breaker (_COOLDOWN dict, Retry-After respected)    │
│                   + _PROVIDER_HOST map (provider-diverse buddy failover)           │
│                   + _reasoning_policy (catalog-driven per-model reasoning)         │
│                   + _RECENT_ERRORS ring buffer (exposed via /api/debug)            │
│  joint_mode.py    JointController + per-joint flex/extend/relax + bow fire         │
│  weapons.py       WEAPON_GEOMETRY + builders for sword/dagger/spear/flail/bow      │
│  ragdoll.py       pymunk Fighter (16 limbs + 10 servo-driven joints)               │
│  combat.py        zone classifier + damage model + sharp-vs-blunt resolution       │
│  moves.py         macro action keyframe library (per-weapon)                       │
│  recorder.py      compact replay JSON capture (~5 kB / second of fight);           │
│                   bakes standalone HTML from stickblade-web/public/player.js       │
│  storage.py       SQLite backend (local dev / HF Space) — with self-play guard     │
│  storage_supabase.py  Postgres backend — uses apply_elo_vote RPC for atomic votes  │
│                   + head_to_head via PostgREST OR filter                           │
│  security.py      rate limits + spend caps + spoof-resistant client_ip()           │
│                   (x-real-ip > cf-connecting-ip > XFF opt-in via TRUST_XFF=1)      │
│  config.py        21 verified OpenRouter models + tuning constants                 │
│  supabase_schema.sql  idempotent DDL + apply_elo_vote() RPC (atomic Elo update)    │
└────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── stickblade-web/ (Next.js 15 frontend) ─────────────────┐
│  app/page.js                fight setup + leaderboard + reveal + vote              │
│                             (polling now owned by <WaitPanel>)                     │
│  app/tournament/page.js     bracket creator + live bracket viewer                  │
│  app/leaderboard/page.js    per-weapon / per-zone leaderboards                     │
│  app/replay/page.js         standalone /replay?id=… — now uses canvas_a/b_model    │
│                             so shared links show the CORRECT winner (was 50/50)    │
│  app/history/page.js        recent matches list                                    │
│  public/player.js           canvas replay engine + WebAudio FX + killcam           │
│                             (single source of truth; server.py serves this too    │
│                              from /static/player.js — no drift-hazard duplicate)   │
│  components/WaitPanel.js    live wait screen: quips + queue + combat ticker +      │
│                             head-to-head card + recent-duels feed                  │
│  components/ModelPicker.js  neutral Slot 1/2 picker (no color leak)                │
│  components/LeaderboardTable.js  medals + per-row Elo, honors `compact` prop      │
│  components/ReplayPlayer.js  React wrapper around vanilla player.js                │
│  lib/api.js                 fetch client + startKeepalive() + getHeadToHead()      │
│  next.config.mjs            strict CSP + COOP + COEP-aware security headers        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

The frontend and backend are independent and stateless across each other — the frontend only knows `NEXT_PUBLIC_API_BASE` (the HF Space URL) and talks to it via REST.

---

## 🌐 REST API (quick reference)

Every endpoint is documented in `server.py`; this is the abridged tour. Base URL = your HF Space or `http://localhost:8000`.

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | Liveness + feature flags (`has_openrouter`, `has_supabase`, queue depths) |
| `GET`  | `/api/version` | Semver + list of supported weapons/modes/replay-format |
| `GET`  | `/api/models` | Roster (id + display name) |
| `GET`  | `/api/weapons` | Weapon ids + valid sharp-zone lists |
| `POST` | `/api/match` | Queue a match. Body: `{model_a, model_b, sharp[], weapon, arena, mode, blind}` |
| `GET`  | `/api/match/{mid}` | Match status. While `queued`/`running` returns `.live = {quips, queue_pos, turn, log[]}` (blind-safe, canvas-side keys only). While `done` + voted/non-blind returns `model_a`, `model_b`, `canvas_a_model`, `canvas_b_model`, `names[]`, `flip` |
| `GET`  | `/api/replay/{mid}` | Compact replay JSON (frames, events, thoughts, quips, meta.fallback_turns) |
| `POST` | `/api/vote/{mid}` | Body: `{choice: "a"\|"b"\|"draw"}`. Returns reveal + Elo deltas + commentator's roast |
| `GET`  | `/api/leaderboard?sharp=&weapon=` | Elo leaderboard, per-(model, sharp, weapon) or aggregated |
| `GET`  | `/api/recent` | Last 20 finished matches (models hidden until voted on blind fights) |
| `GET`  | `/api/head_to_head?a=X&b=Y` | Order-insensitive H2H record between two models (used by wait screen) |
| `POST` | `/api/tournament` | Queue a single-elim bracket (4 or 8 models) |
| `GET`  | `/api/tournament/{tid}` | Live bracket state, round-by-round |
| `GET`  | `/api/tournaments` | Recent brackets |
| `GET`  | `/api/debug/brain_errors` | Last ~80 brain failures (model, attempt, error message) — bounded in-memory |
| `GET`  | `/api/debug/cooldowns` | Which models are currently in 429 cooldown, seconds remaining |
| `GET`  | `/api/debug/openrouter_ping?model=X` | One-shot minimal OR call — isolates "key valid?" from "our payload broken?" |

All path params like `{mid}` are validated with `^[a-f0-9]{12}$` before touching storage (path-traversal safe). Rate limits + spend caps live in `security.py` and are per-IP with a spoof-resistant client_ip lookup.

---

## 🚀 Running locally

### Backend (Python 3.13+)

```bash
cd stickblade
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Either: bring your own keys
export OPENROUTER_API_KEY=sk-or-v1-...
export OPENAI_API_KEY=sk-...               # optional, for GPT brains
export GEMINI_API_KEY=...                  # optional, for Gemini brains

# Or: skip keys and use mocks — the mock brains play decent crude duels
# and exercise every code path (great for development). Also spear/flail/
# dagger mocks now use weapon-appropriate actions (bug fixed 2026-07).

# Either: use Supabase
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_KEY=eyJhbGc...service_role_key
# One-time: run stickblade/supabase_schema.sql in the Supabase SQL editor.
# This installs the tables AND the apply_elo_vote() RPC that Python
# uses for atomic Elo updates. Without it, storage_supabase falls back
# to REST + in-process lock (logs a one-time downgrade warning).

# Or: just use local SQLite (default, no setup)

# Optional security knobs (env vars, see stickblade/security.py):
#   RL_MATCHES_PER_HOUR (50)    matches one IP may start per hour
#   RL_VOTES_PER_HOUR   (100)   votes one IP may cast per hour
#   RL_REQS_PER_MIN     (120)   general API req/min per IP
#   MAX_MATCHES_PER_DAY (300)   global daily cap (LLM spend ceiling)
#   TRUST_XFF           (0)     opt-in: honor X-Forwarded-For (dev/local)
#                               HF/Vercel/Fly set x-real-ip which is
#                               trusted by default — no need to enable.

uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Next.js 15)

```bash
cd stickblade-web
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
# open http://localhost:3000
```

### Headless smoke test

```bash
cd stickblade
python test_phases.py           # 5-phase regression suite
python test_headless.py         # full mock duel, saves screenshots

# CLI runners (all 5 weapons now selectable, was sword/flail/bow):
python main.py --weapon dagger --mode macro
python record_match.py --weapon spear --p1 mock:duelist --p2 mock:berserker
python tournament.py --size 4 --weapon flail
```

---

## 🎮 Adding new models

Just append to `config.py`:

```python
ARENA_MODELS = {
    # ...
    "your-org/your-model:free": "Your Model Display Name (free)",
}
```

If the model ID contains `/`, it's auto-routed through OpenRouter via `OpenRouterBrain` — works with any OpenAI-compatible chat-completions provider. No code changes needed.

For mock fighters (no API):
- `mock:duelist` — patient counter-fighter
- `mock:berserker` — relentless aggression

---

## 🔧 Tech stack

| Layer | Tools |
|---|---|
| Physics | pymunk (Chipmunk2D bindings), 60 Hz with 2× substeps |
| Backend | Python 3.13, FastAPI, uvicorn, pygame (headless, for rendering tests) |
| Brains | OpenAI SDK, Google genai SDK, httpx (for OpenRouter) |
| Storage | SQLite (default) · Supabase Postgres + Storage (production) |
| Frontend | Next.js 15, React 19, Vanilla Canvas 2D (no game engine) |
| Audio | WebAudio API — synthesized oscillators + noise buffers, no asset hosting |
| Deploy | Vercel (frontend) + Hugging Face Spaces (backend Docker) |
| Security | strict CSP, COOP, CORP, HSTS preload, X-Frame-Options DENY, Trusted Types report-only |

---

## 🛣 Roadmap

Shipped recently (2026-06 → 2026-07 sweep):
- ✅ **Live wait screen** — pre-fight quips surfaced in ~5-15s, queue-position badge, spoiler-safe combat ticker, per-matchup head-to-head card, recent-duels feed
- ✅ **LLM resilience** — 429 circuit breaker with Retry-After respect, provider-diverse buddy failover, catalog-driven per-model reasoning policy (mandatory vs opt-disable vs omit), full server-side error surfacing
- ✅ **Debug endpoints** — `/api/debug/brain_errors`, `/api/debug/cooldowns`, `/api/debug/openrouter_ping`
- ✅ **Shared-replay reveal fix** — `/replay?id=…` now shows the correct winner every time (was 50/50 wrong before due to canvas-flip mismatch)
- ✅ **Atomic Elo updates on Postgres** — new `apply_elo_vote()` RPC serializes concurrent votes with row locks; SQLite path uses `threading.Lock`. Self-play (mirror match) correctly logs a draw with 0 Elo delta instead of double-updating the row.
- ✅ **Deduped `player.js`** — single source of truth in `stickblade-web/public/`; server serves the same file; no more drift between frontend/backend copies
- ✅ **XFF spoof hardening** — `client_ip()` trusts `x-real-ip`/`cf-connecting-ip` by default, XFF only via `TRUST_XFF=1` opt-in
- ✅ **Bug sweeps** — flail/spear mocks now use weapon-appropriate actions (not silently downgraded to "ready"); CLI runners accept all 5 weapons; MATCH_MODES stops leaking; supabase migration hard-fails on missing `weapon` column instead of silently corrupting Elo
- ✅ **Arena modifiers that actually feel different** — ice bumps damping to 0.996, overrides shin friction to 0.2, AND tells the LLM about it via `state.arena` + system-prompt guidance (used to be a no-op)
- ✅ Tournaments (single-elim, 4/8 models, live bracket viewer)
- ✅ Pre-fight trash talk + post-fight commentator roast
- ✅ New weapons: dagger + spear
- ✅ Killcam slow-motion + WebAudio SFX
- ✅ Predict-then-watch streaks
- ✅ Per-weapon / per-zone Elo leaderboards
- ✅ Random A↔green/B↔blue mapping for true blind voting
- ✅ Spatial-awareness state payload (torso/head positions + velocity + relative geometry)
- ✅ JOINT-mode bow firing
- ✅ Strict CSP + COOP + HSTS preload headers + 11 KiB legacy-polyfill removal

Coming:
- 🟦 Daily challenge (rotating weapon/zone, shared global leaderboard)
- 🟦 OG-image generator for `/replay?id=…` (gorgeous social previews)
- 🟦 Client-side GIF/MP4 export of killcam
- 🟦 Spectator emoji reactions during live tournaments
- 🟦 2v2 team battles
- 🟦 Live LLM thought streaming during the THINK phase
- 🟦 BYOK (bring-your-own-key) mode so heavy users can bypass free-tier throttling
- 🟦 `tools/verify_models.py` — auto-prune dead OpenRouter model ids from the roster on push

---

## 📜 License

MIT — fork it, host your own tournament, plug in your own model.

---

## 🙏 Credits

- Inspired by [Toribash](https://www.toribash.com/) for the per-joint-control vibe and by [Chatbot Arena](https://lmarena.ai/) for the blind-voting Elo model.
- Built on [pymunk](http://www.pymunk.org/) (Chipmunk2D) for physics.
- Free LLM access via [OpenRouter](https://openrouter.ai/).
- Backend hosted on [Hugging Face Spaces](https://huggingface.co/spaces), frontend on [Vercel](https://vercel.com/).
