# STICKBLADE ARENA — Web Frontend (Next.js)

The polished, Vercel-ready frontend for the Stickblade Arena backend
(`../stickblade/server.py`).

## Pages

| Route | What |
|---|---|
| `/` | Fight page — model dropdowns (+ custom OpenRouter id), sharp-zone picker, canvas replay player, blind voting, mini leaderboard, shareable replay link |
| `/leaderboard` | Full Elo boards with per-weapon tabs: Fencers (tip), Sabreurs (edge), Tricksters (back edge), Brawlers (pommel) |
| `/history` | Recent duels — anonymous until voted, ▶ watch links |
| `/replay?id=…` | Shareable replay page with voting (the viral loop) |

## Run locally

```bash
# 1. start the backend
cd ../stickblade && uvicorn server:app --port 8000

# 2. start the frontend
npm install
npm run dev          # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE` defaults to `http://localhost:8000`.

## Deploy to Vercel (free)

1. Push this folder to a GitHub repo (or import directly).
2. vercel.com → New Project → import the repo.
3. Set one env var:
   `NEXT_PUBLIC_API_BASE = https://<your-space>.hf.space`
4. Deploy. Optionally lock the backend down with
   `CORS_ORIGINS=https://your-app.vercel.app` on the Space.

## Notes

- `public/player.js` is copied from `../stickblade/player.js` — if you change
  the player, copy it again (single source of truth is the backend repo).
- The canvas player is plain vanilla JS wrapped in a React component
  (`components/ReplayPlayer.js`) — no rendering libraries needed.
