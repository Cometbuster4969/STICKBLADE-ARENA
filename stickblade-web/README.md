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

## Design system

Styling is one file — `app/globals.css` — holding the token set and every
component class. There is no CSS-in-JS and no UI library, and fonts ship
through `next/font/local` from `@fontsource/*`, so nothing reaches out to a
third-party font host at build or runtime (the CSP does not allow it).

Motion is split deliberately, and the split is the thing to preserve:

| Kind of motion | Where it lives | Why there |
|---|---|---|
| Scroll reveals, staggers, hover lift, hero entrance | CSS — `data-reveal`, `data-reveal-stagger`, `data-lift`, `data-hero-in` on `animation-timeline: view()` | A JS reveal ships `opacity:0` inline from the server and releases it only after hydration + IntersectionObserver. That is invisible to a non-JS reader, to a text-extracting crawler, and to LCP. CSS scroll-driven animation gives the same effect with the *visible* state as the default, so no support means no animation rather than no content. |
| Scroll-linked values, layout transitions, mount/unmount choreography, springs | framer-motion (`components/MotionSection.js`) | These need real JS: reading `scrollY`, animating an element as it reorders, or animating something that does not exist until a click. |

Rules worth knowing before editing:

- **Reduced motion is two-layered on purpose.** `components/MotionProvider.js`
  reads `lib/prefs.js` and drives framer's `MotionConfig`, while the
  `[data-motion="reduced"]` rules in `globals.css` and the
  `prefers-reduced-motion` guards handle the CSS half. Any new reveal must go
  through the `data-reveal` attributes so it inherits both.
- **`backdrop-filter` is allowed on exactly two things**: the sticky nav and the
  modal. A prior audit measured ~6 ms/frame on the mobile compositor for it,
  which is why `.panel` has none and fakes depth with a solid fill and an inset
  highlight instead. Do not add it back to a component that can repeat.
- `body` uses `overflow-x: clip`, not `hidden` — `hidden` turns `<body>` into a
  scroll container and breaks the sticky nav's `top: 0`.
- Nav and footer are full-bleed via `calc(50% - 50vw)` because `<main>` is
  capped at 1200px.
- New interactive primitives (all accept `direction`/`delay`): `MotionSection`,
  `StaggerContainer` + `StaggerItem`, `SlideIn`, `MotionCard`, `HeroAnimation`,
  `HeroScrollFade`, `Parallax`, `FloatingOrb`.

## Notes

- `public/player.js` is copied from `../stickblade/player.js` — if you change
  the player, copy it again (single source of truth is the backend repo).
- The canvas player is plain vanilla JS wrapped in a React component
  (`components/ReplayPlayer.js`) — no rendering libraries needed.
