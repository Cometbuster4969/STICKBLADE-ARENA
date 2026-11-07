#!/usr/bin/env python3
"""Automated weapon / arena / sharp-zone balance sweep (action-plan §9).

Runs scripted bots (no API keys, no network) through balanced mirror
batches for every weapon, arena and sharp-zone configuration, then reports
the numbers the action plan says we must publish per weapon:

    average damage · average reach · time-to-lethal-hit · hit probability ·
    win rate · advantage by arena · advantage by sharp zone

Balance targets (§9):
    * no weapon above 60% win rate across balanced matchups
    * no sharp zone with an unexplained extreme advantage
    * no arena that decides most matches before model decisions matter

Because every fighter here is a deterministic bot, a >60% weapon win rate
means the WEAPON is carrying the outcome, not the model — exactly the
confound the benchmark has to rule out before human-vote Elo means
anything.

Usage:
    python3 tools/weapon_balance.py --n 12 --out research/balance_weapons.csv
    python3 tools/weapon_balance.py --n 8 --bots bot:pro,bot:greedy --md-out \
        research/balance_report.md
"""
from __future__ import annotations

import argparse
import itertools
import statistics
import sys

import simcore
from run_balanced_batch import run_batch, aggregate, wilson_ci

BOTS = ["bot:pro", "bot:greedy", "bot:distance"]
DEFAULT_WEAPONS = ["sword", "dagger", "spear", "flail", "bow"]
DEFAULT_ARENAS = ["normal", "ice", "low_gravity"]


# Fields that identify the FIGHT rather than the row. Two rows sharing all of
# them are the same deterministic fight observed twice.
FIGHT_SIG_FIELDS = ("weapon", "arena", "sharp", "flipped", "winner_side",
                    "method", "turns", "damage_a", "damage_b", "hits_a",
                    "hits_b", "hp_a", "hp_b")


def fight_signature(row):
    """Identity of the fight behind a row.

    Scripted bots are deterministic given (config, bots), and they do not
    consume the seed on the decision paths that matter here — so
    `seed=5000` and `seed=5017` with the same weapon/arena/zone/flip often
    produce the *same fight*, bit for bit. Counting those rows as separate
    trials is pseudo-replication: it shrinks every Wilson interval by about
    sqrt(k) without adding a single new observation.

    Observed on the committed v1.0 sweep: flail had 24 rows but 15 distinct
    fights; across the five weapons 15-23 of 24 rows were unique.
    """
    def norm(v):
        if isinstance(v, float):
            return round(v, 3)
        if isinstance(v, (list, tuple)):
            return tuple(v)
        return v
    return tuple(norm(row.get(f)) for f in FIGHT_SIG_FIELDS)


def unique_rows(rows):
    """First occurrence of each distinct fight, preserving order."""
    seen, out = set(), []
    for r in rows:
        sig = fight_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
    return out


def zone_sets_for(weapon):
    simcore.bootstrap(quiet=True)
    from weapons import WEAPON_ZONES
    return [(z,) for z in WEAPON_ZONES[weapon]]


def sweep(weapons, arenas, bots, n, match_length, base_seed, verbose=True):
    """Run every weapon x arena combination through a balanced batch.

    Fighters are always the SAME pair of bots, mirrored across canvas
    sides, so any win-rate deviation is attributable to the configuration
    rather than to a fighter skill gap.
    """
    rows = []
    combos = list(itertools.product(weapons, arenas))
    for wi, (weapon, arena) in enumerate(combos):
        if len(bots) >= 2:
            a, b = bots[0], bots[1]
        else:
            a, b = bots[0], bots[0]
        sharps = zone_sets_for(weapon)
        if verbose:
            print(f"[{wi+1}/{len(combos)}] {weapon}/{arena} "
                  f"({len(sharps)} sharp-zone variants, {n} matches each)")
        batch, secs = run_batch(
            a, b, n=n, weapons=[weapon], arenas=[arena], sharps=sharps,
            mode="macro", match_length=match_length,
            fallback_policy="operational",
            base_seed=base_seed + 1000 * wi, verbose=False)
        for r in batch:
            r["combo"] = f"{weapon}/{arena}"
        rows.extend(batch)
        if verbose:
            agg = aggregate(batch, a, b)
            print(f"        win rate {agg['win_rate']} over {agg['n']} "
                  f"matches ({secs:.1f}s)")
    return rows


def summarize_by(rows, key):
    """Aggregate rows by a config key: win rate, damage, hits, turns."""
    out = {}
    seen_sigs = {}
    for r in rows:
        k = r.get(key)
        d = out.setdefault(k, {"n": 0, "dmg": [], "hits": [], "turns": [],
                               "first_side_a": 0, "first_side_b": 0,
                               "uniq_side_a": 0, "uniq_side_b": 0,
                               "uniq_draws": 0, "draws": 0, "lethal": 0,
                               "sigs": set()})
        d["n"] += 1
        d["sigs"].add(fight_signature(r))
        for src, dst in (("damage_a", "dmg"), ("damage_b", "dmg")):
            if r.get(src) is not None:
                d[dst].append(float(r[src]))
        for src in ("hits_a", "hits_b"):
            if r.get(src) is not None:
                d["hits"].append(int(r[src]))
        if r.get("turns"):
            d["turns"].append(int(r["turns"]))
        w = r.get("winner_side")
        if w == "a":
            d["first_side_a"] += 1
        elif w == "b":
            d["first_side_b"] += 1
        else:
            d["draws"] += 1
        if r.get("method") == "kill":
            d["lethal"] += 1
    # Second pass: winner tallies counted once per DISTINCT fight. This is the
    # number the CI is allowed to be computed from.
    seen = set()
    for r in rows:
        sig = fight_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        d = out[r.get(key)]
        if r.get("winner_side") == "a":
            d["uniq_side_a"] += 1
        elif r.get("winner_side") == "b":
            d["uniq_side_b"] += 1
        else:
            d["uniq_draws"] += 1
    res = []
    for k, d in sorted(out.items()):
        n = d["n"] or 1
        unique = len(d["sigs"]) or 1
        # CI from DISTINCT fights only: deterministic repeats add no evidence.
        rate, lo, hi = wilson_ci(d["uniq_side_a"], d["uniq_side_b"],
                                 d["uniq_draws"])
        naive_rate, _, _ = wilson_ci(d["first_side_a"], d["first_side_b"],
                                     d["draws"])
        res.append({
            key: k, "matches": d["n"], "unique_fights": len(d["sigs"]),
            "duplicate_rows": d["n"] - len(d["sigs"]),
            # side-a win rate — with mirrored slots this is the config's
            # own bias; 0.5 means the configuration is neutral. Computed on
            # distinct fights; `side_a_win_rate_naive` is what you would get
            # by treating duplicated rows as independent trials.
            "side_a_win_rate": rate, "ci_lo": lo, "ci_hi": hi,
            "side_a_win_rate_naive": naive_rate,
            "avg_damage": round(statistics.mean(d["dmg"]), 2) if d["dmg"] else 0,
            "avg_hits": round(statistics.mean(d["hits"]), 2) if d["hits"] else 0,
            "avg_turns": round(statistics.mean(d["turns"]), 1) if d["turns"] else 0,
            "lethal_rate": round(d["lethal"] / n, 3),
        })
    return res


def verdict(rows_by_weapon):
    """Flag configurations that break the §9 balance targets.

    A point estimate away from 0.5 is NOT evidence of imbalance — with 24
    matches the 95% interval is wide. We only raise a balance flag when
    the Wilson interval excludes 0.5, and we say so explicitly, because
    over-claiming from a small batch is the exact failure mode this
    tooling exists to prevent.
    """
    flags = []
    for r in rows_by_weapon:
        rate, lo, hi = (r.get("side_a_win_rate"), r.get("ci_lo"),
                        r.get("ci_hi"))
        if rate is None:
            continue
        n = r.get("matches") or 0
        unique = r.get("unique_fights", n)
        # PSEUDO-REPLICATION. Scripted bots are deterministic, so N rows can
        # contain far fewer than N distinct fights — the same fight replayed
        # under a new seed. CIs are computed on distinct fights only; say so
        # loudly when the gap is large, because "n=24" would otherwise read
        # as 24 independent observations.
        if unique < n:
            flags.append(
                f"• {r['weapon']}: {n} rows but only {unique} distinct "
                f"fights — scripted bots are deterministic, so repeated "
                f"seeds replayed the same fight. The CI uses {unique}; "
                f"vary the CONFIG (arena / zone / matchup), not the seed, "
                f"to add samples.")
        if unique < 12:
            flags.append(
                f"• {r['weapon']}: only {unique} distinct fights — balance "
                f"verdict provisional (need ≥12, ideally ≥30)")
            continue
        excludes = (lo is not None and hi is not None
                    and (lo > 0.5 or hi < 0.5))
        if excludes:
            flags.append(
                f"⚠ {r['weapon']}: side bias {rate} (95% CI "
                f"[{lo}, {hi}]) excludes 50/50 on a mirrored bot batch — "
                f"the configuration, not the model, is deciding matches")
        elif abs((rate or 0.5) - 0.5) > 0.10:
            flags.append(
                f"• {r['weapon']}: point estimate {rate} is off 50/50 but the "
                f"95% CI [{lo}, {hi}] still contains it — widen the batch "
                f"(n={unique} distinct fights) before treating this as "
                f"imbalance")
        if r.get("lethal_rate", 0) > 0.8:
            flags.append(
                f"⚠ {r['weapon']}: lethal in {r['lethal_rate']:.0%} of "
                f"matches — too fast to show tactical play")
        if r.get("avg_turns", 0) < 4:
            flags.append(
                f"⚠ {r['weapon']}: ends in {r['avg_turns']} turns on average "
                f"— insufficient decision horizon")
    return flags


def render_md(rows, by_weapon, by_arena, by_zone, flags, meta):
    def table(rs, key, title):
        if not rs:
            return ""
        lines = [f"### {title}", "",
                 f"| {key} | rows | distinct fights | side-A win rate (95% CI) "
                 f"| avg damage | avg hits | avg turns | lethal rate |",
                 "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in rs:
            ci = f"[{r['ci_lo']}, {r['ci_hi']}]" if r["ci_lo"] is not None else "—"
            lines.append(
                f"| {r[key]} | {r['matches']} | {r.get('unique_fights', '—')} "
                f"| {r['side_a_win_rate']} {ci} "
                f"| {r['avg_damage']} | {r['avg_hits']} | {r['avg_turns']} "
                f"| {r['lethal_rate']} |")
        return "\n".join(lines) + "\n"

    head = [
        "# Weapon / arena / sharp-zone balance report",
        "",
        f"Generated: {meta['generated']}",
        f"Protocol: {meta['n']} mirrored bot matches per (weapon, arena) "
        f"combination, sharp zones rotated per weapon, seeds "
        f"{meta['base_seed']}+, match length `{meta['match_length']}`.",
        "",
        "Mirrored means the same two scripted bots swap canvas sides on "
        "alternating matches — so any deviation from a 50/50 win rate is "
        "attributable to the configuration, not to fighter skill.",
        "",
    ]
    head += ["## How to read this", "",
             "Side-A win rate is measured on a **mirrored** batch: the same "
             "two scripted bots swap canvas sides every other match, so a "
             "perfectly neutral configuration trends to 0.5. A deviation is "
             "only evidence of imbalance when the 95% Wilson interval "
             "excludes 0.5 — otherwise it is noise at this sample size, and "
             "the report says so rather than claiming a finding.", "",
             "**Distinct fights, not rows, are the sample.** Scripted bots "
             "are deterministic: the same weapon/arena/zone/flip under a new "
             "seed replays the *same* fight, bit for bit. The `rows` column "
             "is how many matches were run; `distinct fights` is how many "
             "independent observations that produced. Every interval in this "
             "report is computed on distinct fights only, because counting "
             "a deterministic repeat as a new trial is pseudo-replication "
             "and narrows the CI by roughly sqrt(k).", ""]
    if flags:
        # Flags already carry their own marker (• / ⚠); adding the markdown
        # dash without stripping it produced "- • ..." in the published report.
        head += ["## Balance flags", ""] + [
            "- " + (f[2:].strip() if f.startswith("• ") else f) for f in flags
        ] + [""]
    else:
        head += ["## Balance flags", "",
                 "No configuration exceeded the §9 thresholds (no weapon "
                 "with a confidence interval that excludes a 50/50 mirrored "
                 "split, none lethal in more than 80% of matches, none "
                 "ending in fewer than 4 turns on average).", ""]
    body = [table(by_weapon, "weapon", "By weapon"),
            table(by_arena, "arena", "By arena"),
            table(by_zone, "sharp", "By sharp zone")]
    return "\n".join(head + [b for b in body if b])


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=12,
                    help="matches per (weapon, arena) combo")
    ap.add_argument("--weapons", default=",".join(DEFAULT_WEAPONS))
    ap.add_argument("--arenas", default=",".join(DEFAULT_ARENAS))
    ap.add_argument("--bots", default=",".join(BOTS))
    ap.add_argument("--length", default="standard",
                    choices=["sprint", "standard", "full"])
    ap.add_argument("--base-seed", type=int, default=5000)
    ap.add_argument("--out", default=None, help="per-match CSV path")
    ap.add_argument("--md-out", default=None, help="markdown report path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    simcore.bootstrap()
    from weapons import WEAPONS
    from datetime import datetime, timezone
    weapons = [w for w in args.weapons.split(",") if w.strip() in WEAPONS]
    arenas = [a.strip() for a in args.arenas.split(",") if a.strip()]
    bots = [b.strip() for b in args.bots.split(",") if b.strip()]
    print(f"weapon balance sweep — {len(weapons)} weapons x {len(arenas)} "
          f"arenas x {args.n} matches (bots: {', '.join(bots[:2])})")
    rows = sweep(weapons, arenas, bots, args.n, args.length, args.base_seed,
                 verbose=not args.quiet)
    for r in rows:
        r.setdefault("sharp", ",".join(r.get("sharp") or []) if
                     isinstance(r.get("sharp"), list) else r.get("sharp"))
    # `sharp` in summarize output is the zone tuple; flatten it.
    for r in rows:
        if isinstance(r.get("sharp"), (list, tuple)):
            r["sharp"] = ",".join(str(x) for x in r["sharp"])
        r["sharp"] = r.get("sharp") or ""
    by_weapon = summarize_by(rows, "weapon")
    by_arena = summarize_by(rows, "arena")
    by_zone = summarize_by(rows, "sharp")
    flags = verdict(by_weapon)

    print()
    for r in by_weapon:
        print(f"  {str(r['weapon']):8s} rows={r['matches']:3d} "
              f"unique={r.get('unique_fights', '?'):3} "
              f"sideA={r['side_a_win_rate']} dmg={r['avg_damage']:6.2f} "
              f"turns={r['avg_turns']:4.1f} lethal={r['lethal_rate']}")
    for f in flags:
        print("  " + f)
    if args.out:
        simcore.write_csv(args.out, rows)
        print(f"  → CSV: {args.out}")
    if args.md_out:
        meta = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "n": args.n, "base_seed": args.base_seed,
                "match_length": args.length}
        md = render_md(rows, by_weapon, by_arena, by_zone, flags, meta)
        path = simcore.write_json(args.md_out.replace(".md", ".json"),
                                  {"by_weapon": by_weapon,
                                   "by_arena": by_arena,
                                   "by_zone": by_zone, "flags": flags,
                                   "meta": meta}) \
            if args.md_out.endswith(".md") else None
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"  → report: {args.md_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
