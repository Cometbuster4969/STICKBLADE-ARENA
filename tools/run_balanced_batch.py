#!/usr/bin/env python3
"""Balanced matchup batch runner (action-plan §4).

An isolated public match tells you almost nothing: one fighter might have
gotten the favourable spawn, the faster provider, or the lucky sharp zone.
This runner produces a *balanced batch* per matchup so the win rate means
something:

  * equal number of matches with A on canvas side A and B on canvas side A
    (removes any positional / colour / rendering asymmetry)
  * fixed, recorded seeds (re-runnable, auditable)
  * optional rotation over weapons / arenas / sharp zones so no single
    configuration dominates the estimate
  * strict fallback policy by default — a batch that silently fell back to
    scripted brains is not research data
  * per-match provenance + a Wilson 95% interval on the win rate

Runs entirely offline with mock:/bot: fighters, or against real models if
API keys are configured (the engine handles provider routing + failover).

Usage:
    python3 tools/run_balanced_batch.py \\
        --a mock:duelist --b bot:pro --n 30 --weapon sword \\
        --out research/batches/duelist_vs_pro.csv

    # rotate weapons and arenas across the batch
    python3 tools/run_balanced_batch.py --a bot:greedy --b bot:distance \\
        --n 24 --weapons sword,spear,bow --arenas normal,ice --json-out x.json
"""
from __future__ import annotations

import argparse
import math
import sys
import time

import simcore


def wilson_ci(wins: int, losses: int, draws: int, z: float = 1.96):
    """95% Wilson score interval on the win rate (draws count as half)."""
    n = wins + losses + draws
    if n == 0:
        return None, None, None
    p = (wins + 0.5 * draws) / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(p, 4), round(max(0.0, centre - half), 4), \
        round(min(1.0, centre + half), 4)


def build_plan(n, weapons, arenas, sharps, base_seed):
    """Generate `n` balanced match configs.

    Slot order alternates (A-vs-B, then B-vs-A) so neither fighter is
    always on the same canvas side; weapon/arena/sharp rotate
    round-robin so every configuration is sampled evenly (or as evenly
    as n allows).
    """
    plan = []
    for i in range(n):
        plan.append({
            "idx": i,
            "flip": bool(i % 2),                       # swap canvas sides
            "weapon": weapons[i % len(weapons)],
            "arena": arenas[i % len(arenas)],
            "sharp": sharps[i % len(sharps)],
            "seed": (base_seed + i) if base_seed is not None else None,
        })
    return plan


def run_batch(a, b, n=30, weapons=("sword",), arenas=("normal",),
              sharps=(("tip",),), mode="macro", match_length="standard",
              fallback_policy="strict", base_seed=1000, verbose=True):
    plan = build_plan(n, list(weapons), list(arenas), list(sharps), base_seed)
    rows = []
    t0 = time.time()
    for cfg in plan:
        left, right = (b, a) if cfg["flip"] else (a, b)
        match, replay = simcore.run_headless_match(
            left, right, sharp=list(cfg["sharp"]), weapon=cfg["weapon"],
            arena=cfg["arena"], mode=mode, match_length=match_length,
            fallback_policy=fallback_policy, seed=cfg["seed"])
        row = simcore.summarize(match, replay)
        row.update({"batch_idx": cfg["idx"], "flipped": cfg["flip"],
                    "pair": f"{a} vs {b}"})
        rows.append(row)
        if verbose:
            print(f"  [{cfg['idx']+1:3d}/{n}] {cfg['weapon']:6s}/"
                  f"{cfg['arena']:11s} seed={cfg['seed']} "
                  f"winner={row['winner_model'] or 'draw'} "
                  f"({row['method']}, {row['turns']} turns)")
    return rows, time.time() - t0


def aggregate(rows, a, b):
    """Win/loss/draw tally from A's point of view + Wilson interval."""
    wins = losses = draws = 0
    for r in rows:
        w = r.get("winner_model")
        if not w:
            draws += 1
        elif w == a:
            wins += 1
        elif w == b:
            losses += 1
        else:
            draws += 1
    rate, lo, hi = wilson_ci(wins, losses, draws)
    return {"model_a": a, "model_b": b, "n": len(rows), "wins": wins,
            "losses": losses, "draws": draws, "win_rate": rate,
            "win_rate_lo": lo, "win_rate_hi": hi,
            "powered": len(rows) >= 30}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True, help="model/bot id for fighter A")
    ap.add_argument("--b", required=True, help="model/bot id for fighter B")
    ap.add_argument("--n", type=int, default=30,
                    help="matches per matchup (30 = minimum powered batch)")
    ap.add_argument("--weapons", default="sword")
    ap.add_argument("--arenas", default="normal")
    ap.add_argument("--sharps", default="tip",
                    help="comma list of comma-free zone sets, e.g. 'tip,edge'")
    ap.add_argument("--mode", default="macro", choices=["macro", "joint"])
    ap.add_argument("--length", default="standard",
                    choices=["sprint", "standard", "full"])
    ap.add_argument("--fallback-policy", default="strict",
                    choices=["strict", "operational", "demo"])
    ap.add_argument("--base-seed", type=int, default=1000)
    ap.add_argument("--out", default=None, help="write per-match CSV here")
    ap.add_argument("--json-out", default=None,
                    help="write per-match + aggregate JSON here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    simcore.bootstrap()
    from weapons import WEAPONS, WEAPON_ZONES
    weapons = [w.strip() for w in args.weapons.split(",") if w.strip()]
    weapons = [w for w in weapons if w in WEAPONS] or ["sword"]
    arenas = [x.strip() for x in args.arenas.split(",") if x.strip()]
    sharps = []
    for z in args.sharps.split(","):
        z = z.strip()
        if z:
            sharps.append((z,))
    if not sharps:
        sharps = [(WEAPON_ZONES[weapons[0]][0],)]

    print(f"balanced batch: {args.a} vs {args.b} — {args.n} matches "
          f"({', '.join(weapons)} / {', '.join(arenas)})")
    rows, secs = run_batch(args.a, args.b, n=args.n, weapons=weapons,
                           arenas=arenas, sharps=sharps, mode=args.mode,
                           match_length=args.length,
                           fallback_policy=args.fallback_policy,
                           base_seed=args.base_seed,
                           verbose=not args.quiet)
    agg = aggregate(rows, args.a, args.b)
    agg.update({"weapons": weapons, "arenas": arenas, "mode": args.mode,
                "match_length": args.length,
                "fallback_policy": args.fallback_policy,
                "base_seed": args.base_seed, "elapsed_s": round(secs, 1)})
    print()
    print(f"  {args.a}: {agg['wins']}W {agg['losses']}L {agg['draws']}D "
          f"of {agg['n']}  win rate {agg['win_rate']} "
          f"[{agg['win_rate_lo']}, {agg['win_rate_hi']}] (95% Wilson)")
    if not agg["powered"]:
        print(f"  ⚠ n={agg['n']} < 30 — underpowered, treat as provisional")
    if args.out:
        simcore.write_csv(args.out, rows)
        print(f"  → CSV: {args.out}")
    if args.json_out:
        simcore.write_json(args.json_out, {"aggregate": agg, "matches": rows})
        print(f"  → JSON: {args.json_out}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
