"""Run a headless match and export a browser replay.

Usage:
    python record_match.py --p1 berserker --p2 duelist --sharp tip
    python record_match.py --p1 gpt --p2 gemini --sharp edge --out my_duel

Outputs:
    replays/<name>.html   self-contained, open in any browser
    replays/<name>.json   raw replay data (future web API payload)
"""
import argparse
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

import config as C  # noqa: E402
from main import Match  # noqa: E402
from recorder import ReplayRecorder, RecordingFX  # noqa: E402


def record(p1, p2, sharp, out_name=None, max_minutes=10, mode="macro", weapon="sword"):
    if not pygame.get_init():
        pygame.init()
        pygame.display.set_mode((C.WIDTH, C.HEIGHT))
    os.makedirs("replays", exist_ok=True)
    name = out_name or f"{p1}_vs_{p2}_{'-'.join(sharp)}_{int(time.time())}"
    rec = ReplayRecorder(every=2)
    fx = RecordingFX(rec)
    match = Match(p1, p2, sharp, fx, mode=mode, weapon=weapon,
                  log_path=os.path.join("replays", name + "_log.json"))
    rec.attach(match)
    import time as _t
    deadline = _t.time() + max_minutes * 60
    sim_frames = 0
    while match.phase != Match.PH_OVER and _t.time() < deadline \
            and sim_frames < 60 * 60 * 10:
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
        if match.phase == Match.PH_THINK:
            _t.sleep(0.02)
        else:
            sim_frames += 1
    # a few extra frames so the death/final pose settles on screen
    for _ in range(90):
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    if match.result is None:
        match._finish()
    j = rec.save_json(os.path.join("replays", name + ".json"))
    h = rec.save_html(os.path.join("replays", name + ".html"))
    return match, j, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", default="berserker")
    ap.add_argument("--p2", default="duelist")
    ap.add_argument("--sharp", default="tip")
    ap.add_argument("--out", default=None, help="output file basename")
    ap.add_argument("--mode", default="macro", choices=["macro", "joint"])
    ap.add_argument("--weapon", default="sword",
                    choices=["sword", "dagger", "spear", "flail", "bow"])
    args = ap.parse_args()
    from weapons import WEAPON_ZONES
    allowed = WEAPON_ZONES.get(args.weapon, C.ALL_ZONES)
    sharp = [z.strip() for z in args.sharp.split(",") if z.strip() in allowed] or [allowed[0]]

    print(f"Recording: {args.p1} vs {args.p2} | sharp: {'+'.join(sharp)} | mode: {args.mode} ...")
    t0 = time.time()
    m, j, h = record(args.p1, args.p2, sharp, args.out, mode=args.mode, weapon=args.weapon)
    kb = os.path.getsize(j) // 1024
    print(f"{m.winner}  ({m.result['turns']} turns, {time.time()-t0:.1f}s)")
    print(f"  replay JSON : {j} ({kb} KB)")
    print(f"  replay HTML : {h}  <-- open this in your browser")


if __name__ == "__main__":
    main()
