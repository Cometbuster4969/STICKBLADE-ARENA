# ⚔️ STICKBLADE ARENA

**LLM-vs-LLM physics combat benchmark.** Two ragdoll stickmen — each controlled
by a different language model — duel with real physics. **You** pick the
weapon, decide which part of it is dangerous, and vote blind on who fought
better. Elo leaderboards reveal which models actually understand a body,
a weapon, and a fight.

```
   🗡 SWORD          ⛓ FLAIL                🏹 BOW
   tip · edge ·      ball · spikes(fast) ·   arrowhead · arrow_shaft ·
   back_edge ·       chain · handle          bow_limb
   pommel
```

Like LMSYS Chatbot Arena — but instead of comparing text, you watch
GPT-OSS sword-fight Llama, vote blind, and build per-weapon-rule Elo
rankings ("best fencer" ≠ "best brawler").

## Repository layout

| Folder | What | Deploy to |
|---|---|---|
| [`stickblade/`](stickblade/) | Game engine (Pygame + Pymunk), LLM brains, FastAPI arena server, tournament tools | Hugging Face Spaces (Docker, free) |
| [`stickblade-web/`](stickblade-web/) | Polished Next.js frontend: fight page, leaderboards, shareable replays | Vercel (free) |

## 60-second start (no API keys needed)

```bash
cd stickblade
pip install -r requirements.txt

# desktop duel, mock AIs:
python main.py --p1 mock:berserker --p2 mock:duelist --weapon sword --sharp tip

# or the full web arena at http://localhost:8000 :
uvicorn server:app --port 8000
```

Add real LLMs with one key (free models included):

```bash
export OPENROUTER_API_KEY=sk-or-...   # free signup at openrouter.ai
```

## Highlights

- **Real physics** — joint-limited ragdolls (knees can't bend backward),
  momentum, a flail with actual chain dynamics, ballistic arrows
- **Two control modes** — 🎯 MACRO (LLM picks tactical moves) and
  🧠 JOINT (LLM drives all 10 joints raw, true-Toribash chaos)
- **The sharpness twist** — only zones *you* select deal damage; a fast
  dangerous-zone headshot is an instant kill (slow-mo included)
- **Blind voting + Elo** — model names hidden until you vote; per-weapon-rule
  leaderboards stored in SQLite or Supabase
- **Replays everywhere** — every match becomes a scrubbable browser replay
  with blood, sparks, damage numbers and each model's per-turn reasoning
- **Research tooling** — tournament runner with strategy reports
  (aggression %, sharp-zone alignment %, action histograms) + full JSON logs
- **Built-in security** — rate limits, daily spend caps, free-model-only
  custom ids, locked CORS

## Documentation

- **[stickblade/README.md](stickblade/README.md)** — full engine & server docs
- **[stickblade/DEPLOY.md](stickblade/DEPLOY.md)** — $0 deployment guide
  (Supabase → OpenRouter → HF Spaces → Vercel)
- **[stickblade-web/README.md](stickblade-web/README.md)** — frontend docs

## License

[MIT](LICENSE)
