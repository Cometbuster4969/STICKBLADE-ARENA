"""STICKBLADE ARENA — Tournament mode.

Auto-plays a series of duels, aggregates results, and writes a strategy report
comparing how each brain (LLM or mock) fights under different sharpness rules.

Usage:
    python tournament.py --p1 gpt --p2 gemini --matches 6 --sharp tip
    python tournament.py --p1 berserker --p2 duelist --matches 10 --sharp tip --sharp edge --sharp pommel
    python tournament.py --p1 gpt --p2 gemini --matches 4 --sharp tip --visual

Notes:
  * Sides are swapped every other match to cancel side/spawn bias.
  * Headless by default (fast). --visual shows each match in a window.
  * Output: tournaments/<timestamp>/  ->  per-match logs + report.json + report.md
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

import config as C
from moves import ACTION_ZONE

ATTACK_ACTIONS = set(ACTION_ZONE)          # actions that lead with a zone
GUARD_ACTIONS = {"guard_high", "guard_low", "ready"}


# ------------------------------------------------------------------ running
def run_match_headless(p1, p2, sharp, log_path, weapon="sword"):
    """Run one match as fast as possible without a window."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    from main import Match
    from render import FX
    if not pygame.get_init():
        pygame.init()
        pygame.display.set_mode((C.WIDTH, C.HEIGHT))
    fx = FX()
    m = Match(p1, p2, sharp, fx, log_path=log_path, weapon=weapon)
    frames = 0
    while m.phase != Match.PH_OVER and frames < 60 * 600:
        m.update(1 / 60, True)            # fast flag = 3x substeps
        fx.update(1 / 60)
        frames += 1
    return m


def run_match_visual(p1, p2, sharp, log_path, weapon="sword"):
    """Run one match in a window; auto-advances when the match ends."""
    import pygame
    from main import Match
    from render import Renderer, FX
    if not pygame.get_init():
        pygame.init()
    screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
    pygame.display.set_caption("STICKBLADE ARENA — Tournament")
    clock = pygame.time.Clock()
    rend = Renderer(screen)
    fx = FX()
    m = Match(p1, p2, sharp, fx, log_path=log_path, weapon=weapon)
    over_timer = 2.5
    import random as _r
    while True:
        dt = clock.tick(C.FPS) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or \
               (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit(0)
        m.update(dt, False)
        fx.update(dt)
        off = (_r.uniform(-fx.shake, fx.shake), _r.uniform(-fx.shake, fx.shake)) \
            if fx.shake > 0.3 else (0, 0)
        screen.blit(rend.bg, (0, 0))
        rend.draw_fx(screen, fx, off)
        for f in (m.f1, m.f2):
            rend.draw_fighter(screen, f, off)
            rend.draw_weapon(screen, f, sharp, off, arrows=m.arrows[f.fid] if m.arrows else None)
        rend.draw_hud(screen, m.f1, m.f2, m.turn, C.MAX_TURNS, sharp,
                      "THINKING…" if m.phase == Match.PH_THINK else "")
        rend.draw_thought(screen, m.f1, m.thoughts[0], 0)
        rend.draw_thought(screen, m.f2, m.thoughts[1], 1)
        if m.phase == Match.PH_OVER:
            txt = rend.f_big.render(m.winner, True, (255, 220, 90))
            screen.blit(txt, (C.WIDTH // 2 - txt.get_width() // 2, C.HEIGHT // 2 - 60))
            over_timer -= dt
            if over_timer <= 0:
                return m
        pygame.display.flip()


# ------------------------------------------------------------------ stats
class BrainStats:
    def __init__(self, kind):
        self.kind = kind
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.kills = 0
        self.point_wins = 0
        self.actions = Counter()
        self.footwork = Counter()
        self.dmg_dealt = 0.0
        self.dmg_taken = 0.0
        self.sharp_hits = 0
        self.blunt_hits = 0
        self.turns = 0

    def sharp_alignment(self, sharp_zones):
        """% of attack actions whose leading zone is actually sharp."""
        atk = sum(v for a, v in self.actions.items() if a in ATTACK_ACTIONS)
        if atk == 0:
            return None
        good = sum(v for a, v in self.actions.items()
                   if a in ATTACK_ACTIONS and ACTION_ZONE[a] in sharp_zones)
        return 100.0 * good / atk

    def aggression(self):
        tot = sum(self.actions.values())
        if tot == 0:
            return None
        atk = sum(v for a, v in self.actions.items() if a in ATTACK_ACTIONS)
        return 100.0 * atk / tot


def harvest(match, kinds_by_name, stats, sharp):
    """Pull per-brain stats out of a finished match's log + result."""
    res = match.result
    names = [match.f1.name, match.f2.name]
    for nm in names:
        st = stats[kinds_by_name[nm]]
        st.turns += res["turns"]
    if res["winner"] is None:
        for nm in names:
            stats[kinds_by_name[nm]].draws += 1
    else:
        wk = kinds_by_name[res["winner"]]
        lk = [kinds_by_name[n] for n in names if n != res["winner"]][0]
        stats[wk].wins += 1
        stats[lk].losses += 1
        if res["method"] == "kill":
            stats[wk].kills += 1
        elif res["method"] == "points":
            stats[wk].point_wins += 1
    for t in match.log:
        for nm in names:
            if nm in t:
                st = stats[kinds_by_name[nm]]
                st.actions[t[nm]["action"]] += 1
                st.footwork[t[nm]["footwork"]] += 1
        for h in t.get("hits", []):
            atk = stats[kinds_by_name[h["attacker"]]]
            vic = stats[kinds_by_name[h["victim"]]]
            atk.dmg_dealt += h["damage"]
            vic.dmg_taken += h["damage"]
            if h["sharp"]:
                atk.sharp_hits += 1
            else:
                atk.blunt_hits += 1


# ------------------------------------------------------------------ report
def fmt_pct(v):
    return "—" if v is None else f"{v:.0f}%"


def build_report(p1, p2, per_config, out_dir, n_matches):
    lines = ["# STICKBLADE ARENA — Tournament Report", "",
             f"**{p1.upper()} vs {p2.upper()}** — {n_matches} match(es) per sharpness config, "
             f"sides swapped each match.", ""]
    js = {"p1": p1, "p2": p2, "matches_per_config": n_matches, "configs": []}
    for sharp, (stats, results) in per_config.items():
        sharp_l = list(sharp)
        lines.append(f"## Sharp zones: {' + '.join(z.upper() for z in sharp_l)}")
        lines.append("")
        s1, s2 = stats[p1], stats[p2]
        lines.append(f"**Score: {p1} {s1.wins} — {s2.wins} {p2}"
                     + (f"  (draws: {s1.draws})" if s1.draws else "") + "**")
        lines.append("")
        lines.append("| Metric | " + p1 + " | " + p2 + " |")
        lines.append("|---|---|---|")
        rows = [
            ("Wins (kills / points)", f"{s1.wins} ({s1.kills}/{s1.point_wins})",
             f"{s2.wins} ({s2.kills}/{s2.point_wins})"),
            ("Damage dealt", f"{s1.dmg_dealt:.0f}", f"{s2.dmg_dealt:.0f}"),
            ("Sharp / blunt hits landed", f"{s1.sharp_hits} / {s1.blunt_hits}",
             f"{s2.sharp_hits} / {s2.blunt_hits}"),
            ("Aggression (attack turns)", fmt_pct(s1.aggression()), fmt_pct(s2.aggression())),
            ("Sharp-zone alignment*", fmt_pct(s1.sharp_alignment(sharp_l)),
             fmt_pct(s2.sharp_alignment(sharp_l))),
        ]
        for r in rows:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")
        lines.append("")
        for kind, st in ((p1, s1), (p2, s2)):
            top_a = ", ".join(f"{a}×{n}" for a, n in st.actions.most_common(3))
            top_f = ", ".join(f"{f}×{n}" for f, n in st.footwork.most_common(2))
            lines.append(f"- **{kind}** favoured: {top_a or '—'} | footwork: {top_f or '—'}")
        lines.append("")
        lines.append("| # | Winner | Method | Turns | Final HP | Log |")
        lines.append("|---|---|---|---|---|---|")
        for i, r in enumerate(results, 1):
            hp = " / ".join(f"{k}:{v}" for k, v in r["final_hp"].items())
            lines.append(f"| {i} | {r['winner'] or 'draw'} | {r['method']} "
                         f"| {r['turns']} | {hp} | {r['log']} |")
        lines.append("")
        js["configs"].append({
            "sharp": sharp_l,
            "score": {p1: s1.wins, p2: s2.wins, "draws": s1.draws},
            "matches": results,
            "stats": {k: {
                "wins": st.wins, "kills": st.kills, "point_wins": st.point_wins,
                "draws": st.draws, "damage_dealt": round(st.dmg_dealt, 1),
                "damage_taken": round(st.dmg_taken, 1),
                "sharp_hits": st.sharp_hits, "blunt_hits": st.blunt_hits,
                "aggression_pct": st.aggression(),
                "sharp_alignment_pct": st.sharp_alignment(sharp_l),
                "action_usage": dict(st.actions),
                "footwork_usage": dict(st.footwork),
            } for k, st in stats.items()},
        })
    lines.append("\\* % of attack moves whose leading sword zone was actually "
                 "sharp — measures whether the brain understood the weapon rules.")
    md = "\n".join(lines)
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(md)
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(js, f, indent=2)
    return md


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Run a STICKBLADE tournament.")
    ap.add_argument("--p1", default="gpt")
    ap.add_argument("--p2", default="gemini")
    ap.add_argument("--matches", type=int, default=4,
                    help="matches per sharpness config")
    ap.add_argument("--sharp", action="append", default=None,
                    help="repeatable; comma-combo of tip,edge,back_edge,pommel")
    ap.add_argument("--visual", action="store_true",
                    help="render every match in a window")
    ap.add_argument("--weapon", default="sword", choices=["sword", "flail", "bow"])
    args = ap.parse_args()

    # mirror tournament: keep stats separate per slot
    if args.p1 == args.p2:
        args.p1, args.p2 = f"{args.p1}#1", f"{args.p2}#2"

    configs = []
    for s in (args.sharp or ["tip"]):
        from weapons import WEAPON_ZONES
        allowed = WEAPON_ZONES[args.weapon]
        zones = tuple(z.strip() for z in s.split(",") if z.strip() in allowed)
        if zones and zones not in configs:
            configs.append(zones)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("tournaments", ts)
    os.makedirs(out_dir, exist_ok=True)

    total = len(configs) * args.matches
    print(f"=== TOURNAMENT: {args.p1.upper()} vs {args.p2.upper()} ===")
    print(f"{args.matches} match(es) x {len(configs)} sharpness config(s) "
          f"= {total} duels -> {out_dir}\n")

    per_config = {}
    n = 0
    for sharp in configs:
        stats = {args.p1: BrainStats(args.p1), args.p2: BrainStats(args.p2)}
        results = []
        for i in range(args.matches):
            n += 1
            swap = i % 2 == 1
            a, b = (args.p2, args.p1) if swap else (args.p1, args.p2)
            log_name = f"match_{'-'.join(sharp)}_{i+1:02d}.json"
            log_path = os.path.join(out_dir, log_name)
            print(f"[{n}/{total}] sharp={'+'.join(sharp)}  {a} (left) vs {b} (right) ... ",
                  end="", flush=True)
            t0 = time.time()
            runner = run_match_visual if args.visual else run_match_headless
            # strip mirror suffix for brain construction
            m = runner(a.split("#")[0], b.split("#")[0], list(sharp), log_path, weapon=args.weapon)
            # map fighter display names back to brain kinds
            kinds_by_name = {m.f1.name: a, m.f2.name: b}
            harvest(m, kinds_by_name, stats, sharp)
            res = dict(m.result)
            res["winner"] = kinds_by_name.get(res["winner"], res["winner"])
            res["final_hp"] = {kinds_by_name[k]: v for k, v in res["final_hp"].items()}
            res["log"] = log_name
            results.append(res)
            print(f"{res['winner'] or 'draw'} by {res['method']} "
                  f"({res['turns']} turns, {time.time()-t0:.1f}s)")
        per_config[sharp] = (stats, results)
        s1, s2 = stats[args.p1], stats[args.p2]
        print(f"  -> score [{'+'.join(sharp)}]: {args.p1} {s1.wins} — {s2.wins} {args.p2}"
              + (f" (draws {s1.draws})\n" if s1.draws else "\n"))

    md = build_report(args.p1, args.p2, per_config, out_dir, args.matches)
    print("=" * 60)
    print(f"Report written to {out_dir}/report.md and report.json")
    print("=" * 60)
    # console summary
    for sharp, (stats, _) in per_config.items():
        s1, s2 = stats[args.p1], stats[args.p2]
        print(f"  {'+'.join(sharp):<18} {args.p1} {s1.wins} — {s2.wins} {args.p2}"
              f"   | alignment: {fmt_pct(s1.sharp_alignment(list(sharp)))} vs "
              f"{fmt_pct(s2.sharp_alignment(list(sharp)))}")


if __name__ == "__main__":
    main()
