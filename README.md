<div align="center">

# ⚔️ STICKBLADE ARENA

### Watch AI models sword-fight with real physics. Vote blind. Build the leaderboard.

**🎮 [PLAY NOW → stickblade-arena.vercel.app](https://stickblade-arena.vercel.app)**

*An LLM-vs-LLM physics combat benchmark — like Chatbot Arena, but instead of
comparing text, two language models control ragdoll stickmen in a weapons duel,
and **you** decide which part of the weapon is dangerous.*

</div>

---

## 🎯 What is this?

Most AI benchmarks compare text answers. **Stickblade Arena tests something
different: can a language model understand a body, a weapon, and a fight?**

Two stickmen — each piloted by a different LLM — duel in a physics simulation.
Every turn, each model receives the battle state as JSON (health, distance,
enemy's last move, what hit last turn) and must reason its way to a decision.
The physics engine executes it. No scripts, no animations-on-rails: momentum,
joint limits, and collisions decide what actually happens.

**The twist that makes it a benchmark:** before each match, *you* choose which
zones of the weapon deal damage. Only the sword's tip? Models must figure out
that slashing is useless and fence with thrusts. Only the pommel? The optimal
strategy flips to close-range brawling. The rules are stated in each model's
prompt — *the strategy is up to the model.* Blind human votes turn the results
into per-weapon-rule Elo rankings, because **the best fencer is not
necessarily the best brawler.**

## 🕹 How to play (30 seconds)

1. Open **[stickblade-arena.vercel.app](https://stickblade-arena.vercel.app)**
2. Pick **Fighter A** and **Fighter B** from the dropdowns (or type any
   [OpenRouter model id](https://openrouter.ai/models))
3. Choose a **weapon** — 🗡 sword, ⛓ flail, or 🏹 bow
4. Choose the **control mode** — 🎯 MACRO or 🧠 JOINT
5. Toggle the **dangerous zones** (the twist!)
6. **⚔ FIGHT** → watch the duel → **vote blind** for who fought better
7. Identities + Elo changes are revealed *after* your vote

> First visit after a quiet period may take ~1–2 minutes — the free backend
> wakes from sleep. Subsequent fights are fast.

## ⚔ The arsenal

| Weapon | Damage zones (you pick) | What it tests |
|---|---|---|
| 🗡 **Sword** | `tip` · `edge` · `back_edge` · `pommel` | Spacing & timing. Tip-only ⇒ fencing; pommel-only ⇒ clinch fighting |
| ⛓ **Flail** | `ball` · `spikes` · `chain` · `handle` | Multi-turn planning. **Spikes only count at high speed** — models must learn to spin up momentum before striking. Real chain physics |
| 🏹 **Bow** | `arrowhead` · `arrow_shaft` · `bow_limb` | Distance discipline. Ballistic arrows with gravity drop; kite or get clubbed — `bow_limb`-only turns it into a melee staff duel |

## 🧠 Two control modes

| | 🎯 MACRO (tactician) | 🧠 JOINT (raw nervous system) |
|---|---|---|
| The LLM outputs | one tactical action + footwork per turn (`thrust`, `spin_up`, `lunge`…) | a state for **all 10 joints**: `flex / extend / hold / relax` |
| Looks like | actual weapon fighting | emergent, chaotic, true-Toribash flailing |
| Measures | tactical reasoning & rule adaptation | raw spatial/embodied reasoning — notoriously hard for LLMs |

## 🏆 Leaderboards

- **Blind voting** — fighters appear only as "Fighter A/B" until you vote (the
  LMSYS trick that keeps votes honest)
- **Elo per weapon-rule** — separate rankings for tip-fencers, spike-brawlers,
  arrowhead-archers… every danger-zone config is its own ladder
- **Permanent & communal** — every visitor's vote lands in the same cloud
  database. [Check the standings →](https://stickblade-arena.vercel.app/leaderboard)
- **Replays are shareable** — every match gets a link with full playback:
  blood, sparks, damage numbers, slow-mo kills, and **each model's per-turn
  reasoning in thought bubbles**

## 🔬 Under the hood

```
Browser (Next.js on Vercel)
   │  pick fighters / weapon / zones → POST /api/match
   ▼
FastAPI backend (Hugging Face Spaces, Docker)
   │  per turn: freeze → JSON state → both LLMs reply → physics runs 3 s
   │  Pymunk engine: servo-muscle ragdolls, joint limits, chain links,
   │  ballistic arrows, zone-classified collision damage
   │  records every frame → replay JSON
   ▼
OpenRouter (any LLM, free models included)      Supabase (matches, votes, Elo, replays)
```

- **Physics:** 11-body ragdolls with human joint limits (knees don't bend
  backward), active balance, momentum-based damage = zone × impact speed ×
  body part. A fast dangerous-zone **headshot is an instant kill** (slow-mo
  included).
- **Brains:** one OpenRouter key unlocks 100+ models; `:free` models cost
  nothing. No keys? Built-in scripted mock fighters keep everything playable.
- **Replays:** the canvas player re-creates the entire fight client-side from
  ~200 KB of frame data — scrub, slow-mo, frame-step.
- **Protection:** per-IP rate limits, global daily spend cap, custom model ids
  restricted to free models, blind-vote integrity (one vote per match).

## 🚀 Run it yourself

```bash
git clone https://github.com/Cometbuster4969/STICKBLADE-ARENA
cd STICKBLADE-ARENA/stickblade
pip install -r requirements.txt

# desktop duel (no API keys needed — mock AIs):
python main.py --p1 mock:berserker --p2 mock:duelist --weapon sword --sharp tip

# full web arena at http://localhost:8000:
uvicorn server:app --port 8000

# real LLMs (free signup at openrouter.ai):
export OPENROUTER_API_KEY=sk-or-...
python main.py --p1 meta-llama/llama-3.3-70b-instruct:free \
               --p2 openai/gpt-oss-120b:free --weapon flail --sharp spikes
```

**Research tooling included:**

```bash
# auto-play N matches per rule-set, generate a strategy report
# (win rates, aggression %, sharp-zone alignment %, favoured actions):
python tournament.py --p1 gpt --p2 gemini --matches 6 \
                     --weapon sword --sharp tip --sharp edge --sharp pommel

# record any matchup as a self-contained browser replay:
python record_match.py --p1 mock:duelist --p2 mock:berserker --weapon bow --sharp arrowhead
```

## 📁 Repository layout

| Path | What | Deployed on |
|---|---|---|
| [`stickblade/`](stickblade/) | Physics engine, LLM brains, FastAPI server, tournament tools — [full docs](stickblade/README.md) | [Hugging Face Spaces](https://huggingface.co/spaces) (Docker, free) |
| [`stickblade-web/`](stickblade-web/) | Next.js frontend — fight page, leaderboards, shareable replays — [docs](stickblade-web/README.md) | [Vercel](https://vercel.com) (free) |
| [`stickblade/DEPLOY.md`](stickblade/DEPLOY.md) | **The $0 deployment guide** — Supabase → OpenRouter → HF Spaces → Vercel | |

## 🗺 Roadmap ideas

- Mixed-weapon duels (sword vs bow!)
- Per-weapon rollup leaderboards & macro/joint-separated Elo
- Replay gallery of the best kills
- Team battles (2v2 with shared LLM context)

PRs and issues welcome.

## 📜 License

[MIT](LICENSE) — build your own arena, run your own benchmark.

---

<div align="center">

**[⚔ Enter the arena →](https://stickblade-arena.vercel.app)**

*Find out which AI actually knows how to hold a sword.*

</div>
