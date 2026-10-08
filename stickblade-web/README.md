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

The visual language is a **kinematics plate**: the site is laid out like an
engineering motion-study drawing, because that is what the product actually
is — duel geometry, measured and annotated. Cool paper (`--bg-0` #e7e9e2)
carries ink text and 1px pencil/ink rules; sheets (`--bg-2-solid`) are flat,
radius ≤ 6px, with no shadows, glows or gradient washes. Colour is semantic,
never decorative: `--red` marks danger (lethal tip, sharp zone), green/blue
are the two fighters' inks matching what `player.js` paints on the canvas,
amber is the pencil note for provisional/live states. Display type is
**Big Shoulders** in sentence case (condensed, drafting-title cadence);
Inter carries body copy; monospace is reserved for measurements — turns,
seeds, Elo — the way an instrument calls out numbers. The hero opens with the
subject itself: `components/HeroPlate.js` draws the duel as a labelled figure
(stick fighters, weapon arc, turn budget) in inline SVG. The replay canvas is
the one dark surface on purpose: it is a monitor, not a card.

There is no animation library. An earlier pass drove micro-interactions with
framer-motion; it was removed once every effect turned out to be expressible
as CSS (~48 kB first-load saved — `/` went 196 kB → 142 kB, and the dev
compile dropped from 1632 to 820 modules). The split below is the thing to
preserve:

| Kind of motion | Where it lives | Why there |
|---|---|---|
| Scroll reveals, staggers, hover lift, hero entrance | CSS — `data-reveal`, `data-reveal-stagger`, `data-lift`, `data-hero-in` on `animation-timeline: view()` | A JS reveal ships `opacity:0` inline from the server and releases it only after hydration + IntersectionObserver. That is invisible to a non-JS reader, to a text-extracting crawler, and to LCP. CSS scroll-driven animation gives the same effect with the *visible* state as the default, so no support means no animation rather than no content. |
| Press feedback, ambient loops, entrances, swaps, collapse height | CSS — `[data-press]`, `.loop-fade`, `.enter-*`, `.swap`, `.collapse` ("MOTION UTILITIES" in `globals.css`) | A spring on `:hover`, a breathing dot, and a popover fading out are transition/keyframe problems, not animation-library problems. Call sites carry the values as custom properties (`--ph`, `--hy`, `--ed`). |
| Reading rail | CSS on `animation-timeline: scroll(root)` (`.scroll-rail`) | Scroll-linked *values* needed a library only before scroll timelines existed. Guarded by `@supports`, so the default state is the final state. (The hero scroll-fade and parallax wrappers were retired with the plate redesign — one orchestrated entrance is the budget.) |
| Reduced-motion awareness, swap-out unmount timing, FLIP reordering | three hooks in `lib/motion.js` (~130 lines, dependency-free) | These genuinely need JS: a server render cannot know the ♿ switch state, React unmounting a node leaves CSS nothing to animate out, and nobody else in the stack remembers a rect to invert. |

Rules worth knowing before editing:

- **Reduced motion is two-layered on purpose.** `components/MotionProvider.js`
  applies `lib/prefs.js` to `<html>` on mount; the `[data-motion="reduced"]`
  and `prefers-reduced-motion` rules in `globals.css` then neutralise every
  animation and *transition* — which is why press feedback is a transition and
  entrances are `both`-filled keyframes ending in the natural state. JS-side
  skipping goes through `useReducedMotion()` from `lib/motion.js`. Any new
  reveal must go through the `data-reveal` attributes so it inherits the
  guards; anything scroll-linked must sit inside the `@supports` block,
  because a timeline animation ignores the duration kill.
- **Reveals are opt-in and fade-only.** `MotionSection`/`StaggerItem` emit
  `data-reveal` only when a direction is passed, and every direction currently
  resolves to `reveal-fade`: sections are meant to *be there*, not to
  announce themselves one by one. The one orchestrated moment is the hero
  entrance (`data-hero-in`); motion should mostly answer the user
  (`[data-press]`, `.swap`, `.collapse`, `.sel-rail`).
- **The visible state is always the default state.** Never write
  `opacity: 0` inline (or in a rule that an animation has to "undo") —
  that's the regression framer's `whileInView` introduced and CSS removes
  structurally.
- **`backdrop-filter` is allowed on exactly two things**: the sticky nav and the
  modal. A prior audit measured ~6 ms/frame on the mobile compositor for it,
  which is why `.panel` has none and sits flat — on a plate, a rule frames a
  sheet, it does not float it. Do not add it back to a component that can repeat.
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
