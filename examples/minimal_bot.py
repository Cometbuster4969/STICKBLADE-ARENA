#!/usr/bin/env python3
"""
Minimal example bot — the smallest thing that can fight in Stickblade Arena.

Action-plan §25 asks for a "minimal example bot" so a researcher can see the
bot interface without reading bots.py. This one is ~40 lines of logic and has
exactly one idea: **attack when the enemy is in range, guard when it isn't,
and always lunge if we're behind on HP.**

It is deliberately *not* good. It exists to show the contract:

  1. Subclass `BotBrain` (or `Brain`).
  2. Set `label` — it is what shows on the canvas until the reveal.
  3. Implement `decide(state) -> {"action": …, "footwork": …, "thought": …}`.
  4. Draw randomness from `self._rng`, never from the global `random` module
     (the two fighters decide concurrently; a shared RNG makes seeded matches
     non-reproducible).
  5. Return `_sanitize(mv, self.actions)` so an out-of-vocabulary action is
     coerced and counted instead of crashing the match.

Run it against a built-in baseline:

    SDL_VIDEODRIVER=dummy PYTHONPATH=stickblade python3 examples/minimal_bot.py
    SDL_VIDEODRIVER=dummy PYTHONPATH=stickblade \\
        python3 examples/minimal_bot.py --opponent bot:pro --weapon spear --seed 7

Or drop it into the roster by adding it to `_BOT_REGISTRY` in
`stickblade/bots.py` (key "example" → id `bot:example`).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stickblade"))

from bots import BotBrain, _sanitize                      # noqa: E402
from main import Match                                    # noqa: E402
from recorder import ReplayRecorder, RecordingFX          # noqa: E402


class ExampleBot(BotBrain):
    """Guard at range, swing up close, gamble when losing."""

    label = "ExampleBot"

    # Rough "I can hit from here" distances per weapon. Real bots should
    # derive reach from the weapon geometry; this is an example, not a
    # strategy.
    REACH = {"sword": 95, "dagger": 75, "spear": 150, "flail": 130, "bow": 320}

    def decide(self, state):
        reach = self.REACH.get(self.weapon, 95)
        d = state.get("distance", 999)
        my_hp = state.get("my_hp", 100)
        foe_hp = state.get("foe_hp", 100)

        # Sharp-zone attacks are the ones this match is scored on.
        attacks = self._sharp_attacks()
        attack = self._rng.choice(attacks) if attacks else "ready"

        if d > reach:
            mv = {"action": "ready", "footwork": "advance",
                  "thought": "Out of range — close the distance."}
        elif my_hp < foe_hp - 15:
            # Behind on HP: commit. A guard here loses slowly instead of
            # winning quickly.
            mv = {"action": attack, "footwork": "lunge",
                  "thought": "Behind on HP — trade now rather than bleed out."}
        else:
            mv = {"action": attack, "footwork": "hold",
                  "thought": f"In range at {int(d)} — swing at the sharp zone."}
        return _sanitize(mv, self.actions)


def register():
    """Put this bot on the roster as `bot:example`.

    This is the real integration path: `make_bot()` looks the kind up in
    `_BOT_REGISTRY` at call time, so inserting here is enough for
    `Match("bot:example", …)` and for `--a bot:example` on the CLI tools.
    """
    import bots
    bots._BOT_REGISTRY["example"] = ExampleBot


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opponent", default="bot:greedy")
    ap.add_argument("--weapon", default="sword")
    ap.add_argument("--arena", default="normal",
                    choices=["normal", "ice", "low_gravity"])
    ap.add_argument("--sharp", default="tip")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--length", default="standard",
                    choices=["sprint", "standard", "full"])
    args = ap.parse_args(argv)

    import pygame
    pygame.init()
    pygame.display.set_mode((10, 10))
    register()

    rec = ReplayRecorder(every=4)
    fx = RecordingFX(rec)
    match = Match("bot:example", args.opponent, [args.sharp], fx,
                  log_path=os.devnull, weapon=args.weapon, arena=args.arena,
                  seed=args.seed, match_length=args.length)
    rec.attach(match)

    while match.phase != Match.PH_OVER:
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    # Record the terminal frames so the replay's last frame carries over=1
    # and verify_replay() doesn't report a false alarm.
    for _ in range(90):
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()

    print(f"bot:example vs {args.opponent} · {args.weapon}/{args.arena} "
          f"· {args.length} · seed {args.seed}")
    print(f"  result : {match.winner}")
    print(f"  turns  : {match.turn}")
    print(f"  hp     : {match.f1.name}={match.f1.hp:.1f}  "
          f"{match.f2.name}={match.f2.hp:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
