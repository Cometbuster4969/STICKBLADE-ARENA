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
- **Arena modifiers:** ❄ ice floor (low friction) · 🌙 low gravity (moon-ish)
- **Blind voting:** A/B labels with server-side green↔blue randomization, so identity never leaks from the picker
- **Per-weapon, per-zone Elo leaderboards:** track who's a fencer vs a brawler vs a bowman
- **Pre-fight trash talk + post-fight roast:** each model throws a one-liner before the fight; a third commentator LLM roasts the loser afterward (only revealed after voting)
- **Predict-then-watch streaks:** call the winner before voting, track your prediction streak in localStorage
- **Killcam:** auto-slow-motion replay of the lethal blow at match end, with cinematic letterbox bars
- **Synthesized sound FX:** WebAudio sword clangs, blunt thuds, lethal hit-stop chime — zero asset hosting, CSP-clean
- **Tournaments:** 4- or 8-model single-elim brackets with live bracket viewer, auto-advance, champion card
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
                            │  4. loop turns:                    │
                            │     a. build_state(...)            │
                            │     b. both brains decide(state)   │
                            │     c. JointController/Move        │
                            │        Controller for 3 s of phys  │
                            │     d. CombatSystem resolves hits, │
                            │        records events              │
                            │     e. recorder.tick()             │
                            │  5. commentator_roast()            │
                            │  6. finish_match() → SQLite/Postgres│
                            └──────────────┬─────────────────────┘
                                           │
USER         ◄──poll────────  /api/match/{mid}  ◄────── replay JSON
   /api/replay/{mid}           (1.5 s poll until done)
                                           │
                                           ▼
                       canvas <player.js>  replay + sound + killcam
                                           │
USER  ──vote──►        /api/vote/{mid}     → reveal + Elo deltas
   predict streak                          + commentator's roast
```

A match takes ~20-60 seconds of wall-clock time for a typical 6-turn fight, dominated by the LLMs' thinking time (the physics runs at simulated 60 fps and produces ~3000-5000 frames of replay JSON, gzipped to a few kilobytes).

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

- **Normal** — standard physics, stone floor (friction = 1.5).
- **❄ Ice** — floor friction × 0.10 — fighters slide on impact, lunges over-shoot, hop-backs go further than expected. Tests how well a model accounts for momentum it can't control.
- **🌙 Low gravity** — y-gravity × 0.35 — bigger arcs, slower falls. Brutal for spear thrusts and bow arcs (which now drop less). Models that assume Earth-normal ballistics suddenly miss every shot.

---

## 🏆 Tournaments

A 4- or 8-model **single-elimination bracket** runs every match through the same simulator. Standard seeding (#1 vs #N, #2 vs #N-1, etc.) so top seeds can't meet until the final. Live bracket viewer auto-polls and updates round-by-round. Winner gets a gold champion card.

This is the best way to compare *many* models head-to-head quickly, and to discover surprising matchups (small open-source models sometimes upset top-seeded frontier ones because they have a tighter motor-control pattern that the bigger model "overthinks").

---

## 🧬 Architecture

```
┌─────────────────────────── stickblade/ (Python backend) ──────────────────────────┐
│  server.py        FastAPI: REST + worker queues (matches + tournaments)            │
│  main.py          Match: orchestrates 24-turn fight (think → sim → resolve)        │
│  brains.py        Brain hierarchy: Mock, GPT, Gemini, OpenRouter + chat() shim     │
│  joint_mode.py    JointController + per-joint flex/extend/relax + bow fire         │
│  weapons.py       WEAPON_GEOMETRY + builders for sword/dagger/spear/flail/bow      │
│  ragdoll.py       pymunk Fighter (16 limbs + 10 servo-driven joints)               │
│  combat.py        zone classifier + damage model + sharp-vs-blunt resolution       │
│  moves.py         macro action keyframe library (per-weapon)                       │
│  recorder.py      compact replay JSON capture (~5 kB / second of fight)            │
│  storage.py       SQLite backend (local dev / HF Space)                            │
│  storage_supabase.py  Supabase Postgres + Storage backend (production)             │
│  config.py        21+ free OpenRouter models registry + tuning constants           │
│  supabase_schema.sql  idempotent DDL for matches / votes / elo / tournaments       │
└────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── stickblade-web/ (Next.js 15 frontend) ─────────────────┐
│  app/page.js                fight setup + leaderboard + reveal + vote              │
│  app/tournament/page.js     bracket creator + live bracket viewer                  │
│  app/leaderboard/page.js    per-weapon / per-zone leaderboards                     │
│  app/replay/page.js         standalone /replay?id=… page for share links           │
│  app/history/page.js        recent matches list                                    │
│  public/player.js           canvas replay engine + WebAudio FX + killcam           │
│  components/ModelPicker.js  neutral Slot 1/2 picker (no color leak)                │
│  components/LeaderboardTable.js   medals + per-row Elo styling                     │
│  components/ReplayPlayer.js  React wrapper around vanilla player.js                │
│  lib/api.js                 fetch client (BASE = NEXT_PUBLIC_API_BASE)             │
│  next.config.mjs            strict CSP + COOP + COEP-aware security headers        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

The frontend and backend are independent and stateless across each other — the frontend only knows `NEXT_PUBLIC_API_BASE` (the HF Space URL) and talks to it via REST.

---

## 🚀 Running locally

### Backend (Python)

```bash
cd stickblade
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Either: bring your own keys
export OPENROUTER_API_KEY=sk-or-v1-...
export OPENAI_API_KEY=sk-...               # optional, for GPT brains
export GEMINI_API_KEY=...                  # optional, for Gemini brains

# Or: skip keys and use mocks — the mock brains play decent crude duels
# and exercise every code path (great for development)

# Either: use Supabase
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_KEY=eyJhbGc...service_role_key

# Or: just use local SQLite (default, no setup)
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Next.js)

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

Shipped recently:
- ✅ Tournaments (single-elim, 4/8 models, live bracket viewer)
- ✅ Pre-fight trash talk + post-fight commentator roast
- ✅ New weapons: dagger + spear
- ✅ Arena modifiers: ice + low gravity
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

---

## 📜 License

MIT — fork it, host your own tournament, plug in your own model.

---

## 🙏 Credits

- Inspired by [Toribash](https://www.toribash.com/) for the per-joint-control vibe and by [Chatbot Arena](https://lmarena.ai/) for the blind-voting Elo model.
- Built on [pymunk](http://www.pymunk.org/) (Chipmunk2D) for physics.
- Free LLM access via [OpenRouter](https://openrouter.ai/).
- Backend hosted on [Hugging Face Spaces](https://huggingface.co/spaces), frontend on [Vercel](https://vercel.com/).
