# examples/

Runnable, self-contained things a researcher can copy without reading the
engine. Everything here works offline with no API key.

## `minimal_bot.py` — the bot interface in ~40 lines

The smallest complete fighter. It shows the whole contract: subclass
`BotBrain`, set `label`, implement `decide(state)`, draw from `self._rng`,
return `_sanitize(...)`.

```bash
SDL_VIDEODRIVER=dummy PYTHONPATH=stickblade python3 examples/minimal_bot.py
SDL_VIDEODRIVER=dummy PYTHONPATH=stickblade \
    python3 examples/minimal_bot.py --opponent bot:pro --weapon spear --seed 7
```

To put it on the roster permanently, register it in `_BOT_REGISTRY` in
`stickblade/bots.py` (the script's `register()` shows the one-liner).

**Honest expectation:** this bot loses to `bot:greedy` at sword and beats
`bot:pro` at spear on seed 7. It is a template, not a baseline — the four
bots in `stickblade/bots.py` are the calibrated reference points.

## Fixtures

- **Match fixture:** `stickblade-web/public/demo_replay.json` — a real engine
  replay recorded offline (`./tools/run_match.py demo`), 12 turns, seed 101,
  verified clean by `./tools/run_match.py verify`.
- **Deterministic replay command:** `./tools/run_match.py simulate --seed 42`
  and `./tools/run_match.py verify <replay.json>`.
- **Python API tour:** `./tools/run_match.py spec --json`, then
  `GET /api/benchmark/spec` on a running backend.

See [docs/LOCAL_DEV.md](../docs/LOCAL_DEV.md) for the full tool inventory and
troubleshooting.
