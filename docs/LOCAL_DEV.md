# Local development guide

Everything here runs **offline, with no API key**. Without provider keys every
fight is played by scripted baselines (`mock:*`, `bot:*`) and flagged as a
fallback in its provenance record — which is exactly what you want while
working on the engine.

## First run

```bash
# system libs for pygame/pymunk (Debian/Ubuntu)
sudo apt-get install -y libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 \
                        libsdl2-ttf-2.0-0 libfreetype6

cd stickblade
pip install -r requirements.txt
pip install pytest                       # dev-only, deliberately not in requirements
SDL_VIDEODRIVER=dummy uvicorn server:app --reload --port 8000
```

```bash
cd stickblade-web
npm install
npm run dev                              # http://localhost:3000
```

The frontend defaults to **same-origin** API calls: `next.config.mjs` proxies
`/api/*` to `BACKEND_ORIGIN` (`http://127.0.0.1:8000` by default). No CORS, no
hard-coded host, works from a phone on the same LAN.

## Tests

```bash
python3 -m pytest tests -q                     # 117 cases, ~35 s, headless
python3 -m pytest tests -q -k physics          # one file
python3 -m pytest tests/test_replay_determinism.py -q -vv
```

`tests/conftest.py` sets `SDL_VIDEODRIVER=dummy` and raises the rate limits so
rapid-fire API tests don't trip `503 arena is busy`. It does not touch the
production defaults in `stickblade/security.py`.

## Offline tools

`tools/run_match.py` is the single entry point:

```bash
./tools/run_match.py spec                 # print the frozen spec
./tools/run_match.py spec --json          # machine-readable
./tools/run_match.py simulate --a mock:duelist --b bot:pro --seed 42
./tools/run_match.py verify <replay.json> # 8-check integrity audit
./tools/run_match.py demo                 # regenerate public/demo_replay.json
./tools/run_match.py batch --a bot:pro --b bot:greedy --n 20
./tools/run_match.py balance --n 8 --md-out research/balance_report.md
./tools/run_match.py export --db path/to/arena.db --out-dir research/exports/ --all-formats
./tools/run_match.py report --export research/exports/x.json --period 2026-09
./tools/run_match.py loadtest --backend http://localhost:8000 --waves 1,5
```

If a tool complains `ModuleNotFoundError: No module named 'server'`, run it
with `PYTHONPATH=stickblade` from the repo root.

## Troubleshooting

**`pygame.error: No available video device`**
Set `SDL_VIDEODRIVER=dummy`. Every headless path (tests, CI, tools) needs it.

**`503 arena is busy`**
The queue cap (`MAX_QUEUE`, default 10) is full — usually a batch run. Raise it
(`MAX_QUEUE=200`) or wait. This is the spend guard, not a bug.

**`429 Too Many Requests`**
Per-IP limits: 50 matches/hour, 100 votes/hour, 120 requests/minute. For local
work set `RL_MATCHES_PER_HOUR=10000 RL_VOTES_PER_HOUR=100000
RL_REQS_PER_MIN=100000 MAX_MATCHES_PER_DAY=100000`, or set `ADMIN_TOKEN` and
send `X-Admin-Token`.

**Seeded matches don't replay identically**
They should — this is enforced by `tests/test_replay_determinism.py`. If they
don't, a brain is drawing from Python's **global** `random` instead of its own
`self.rng`, or a scripted-vs-scripted match is being threaded. See
`stickblade/brains.py:708` and `stickblade/main.py:229`.

**`invalid sharp zones ['tip'] for weapon 'bow'`**
Sharp zones are per weapon. Valid sets: sword/dagger `tip, edge, back_edge,
pommel`; spear `tip, shaft, butt`; flail `ball, spikes, chain, handle`; bow
`arrowhead, arrow_shaft, bow_limb`.

**The demo fight flags an anti-gaming warning**
Regenerate it and check: `./tools/run_match.py demo && ./tools/run_match.py
verify stickblade-web/public/demo_replay.json`. Scripted fighters repeat
actions, so a demo that kills early often trips "repeated identical action" —
the committed demo (seed 101) was chosen because it is clean.

**`next build` fails fetching fonts**
It shouldn't — fonts are self-hosted from `@fontsource/*` via
`next/font/local`. If you see a Google Fonts error, a dependency didn't install;
run `npm install` again and check `@fontsource/inter` is in `package.json`.

**Stale `battle_log_*.json` files in the working tree**
Tools write logs to `os.devnull` by default now. Any you find came from a
direct `Match()` call without `log_path`.

**Database is empty after a restart**
Local SQLite lives in `STICKBLADE_DATA_DIR` (default `arena_data/`, relative to
where you started the process). Start from the same directory, or set the
variable to an absolute path.

## Repository conventions worth knowing

- Every claim you make in a PR needs a `file:line` citation
  ([AGENTS.md](../AGENTS.md) §0.5).
- Changing physics or prompting without a version bump invalidates every
  published result. The CI fingerprint assertion is the tripwire.
- Accessibility state lives on `<html data-motion|data-contrast|data-fx>` and is
  styled purely in CSS — don't add JS branches for it.
