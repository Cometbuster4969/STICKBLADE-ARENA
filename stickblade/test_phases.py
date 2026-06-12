"""Phases 2-5 verification harness (headless)."""
import os, glob, json, math
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import config as C
from main import Match
from render import Renderer, FX
from ragdoll import STANCE

pygame.init()
screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
rend = Renderer(screen)

def joint_violations(m):
    """Check hinge joints stay within human limits (with small solver slack)."""
    bad = []
    SLACK = 0.12
    LIMITS = {"elbow": (0.0, 2.55), "off_elbow": (0.0, 2.55),
              "knee_f": (0.0, 2.3), "knee_b": (0.0, 2.3),
              "shoulder": (-0.9, 3.05), "hip_f": (-0.65, 1.9), "hip_b": (-0.65, 1.9)}
    for f in (m.f1, m.f2):
        for nm, (lo, hi) in LIMITS.items():
            s = f.servos[nm]
            rel = s.child.angle - s.parent.angle
            intuit = (rel - s.offset) / s.sign
            if intuit < lo - SLACK or intuit > hi + SLACK:
                bad.append((f.name, nm, round(intuit, 2)))
    return bad

def settle_check(m):
    """Fighters should plant feet and keep torso near stand height in first second."""
    drops = []
    for f in (m.f1, m.f2):
        drops.append(round(f.stand_torso_y - f.bodies['torso'].position.y, 1))
    return drops

# ---------- run a full mock duel: berserker vs duelist, sharp=tip ----------
fx = FX()
m = Match("berserker", "duelist", ["tip"], fx)
violations, frames = [], 0
settled = None
while m.phase != Match.PH_OVER and frames < 60 * 300:
    m.update(1/60, False)
    fx.update(1/60)
    frames += 1
    if frames == 90:
        settled = settle_check(m)
    if frames % 5 == 0:
        violations += joint_violations(m)

print("== PHASE 2 ==")
print(f"match completed: phase={m.phase}, turns={m.turn}, frames={frames}")
print(f"torso drop after settle (px, + = sank): {settled}  (expect small, < 25)")
print(f"joint limit violations sampled every 5 frames: {len(violations)}")
if violations[:5]:
    print("  examples:", violations[:5])
print(f"fighters stayed in arena: f1.x={m.f1.pos().x:.0f}, f2.x={m.f2.pos().x:.0f} (0..{C.WIDTH})")

# ---------- Phase 3: combat events ----------
print("\n== PHASE 3 ==")
log_file = sorted(glob.glob("battle_log_*.json"))[-1]
log = json.load(open(log_file))
hits = [h for t in log["turns"] for h in t.get("hits", [])]
sharp_hits = [h for h in hits if h["sharp"]]
blunt_hits = [h for h in hits if not h["sharp"]]
lethal = [h for h in hits if h["lethal"]]
print(f"total hits: {len(hits)} | sharp(tip): {len(sharp_hits)} | blunt: {len(blunt_hits)} | lethal: {len(lethal)}")
zone_ok = all(h["zone"] == "tip" for h in sharp_hits)
print(f"all sharp damage came from TIP zone only: {zone_ok}")
if blunt_hits:
    mx = max(h["damage"] for h in blunt_hits)
    print(f"max blunt damage: {mx} (cap {C.BLUNT_CAP}) -> {'OK' if mx <= C.BLUNT_CAP else 'FAIL'}")
if sharp_hits:
    print("sample sharp hit:", sharp_hits[0])
print("winner:", log["winner"])

# ---------- Phase 4: fallback & brain wiring (no keys in sandbox) ----------
print("\n== PHASE 4 ==")
from brains import make_brain, build_state, GPTBrain, _extract_json, _sanitize
b = make_brain("gpt", ["pommel"])     # no key -> should print fallback notice
print("gpt slot resolved to:", b.label)
b2 = make_brain("gemini", ["pommel"])
print("gemini slot resolved to:", b2.label)

# timeout/failure fallback path: a brain whose decide() raises
class BrokenBrain(GPTBrain.__mro__[1]):  # Brain
    label = "GPT"
    def decide(self, state):
        raise RuntimeError("simulated network failure")
bb = BrokenBrain(["pommel"])
st = build_state(m.f1, m.f2, 1, 24, [])
r = bb.decide_with_timeout(st)
print("fallback move on API failure:", r["action"], "/", r["footwork"])
print("fallback thought tag:", r["thought"][:55])

# JSON parser robustness (markdown fences, prose around JSON)
tests = [
    '```json\n{"thought":"hit pommel","action":"pommel_strike","footwork":"lunge"}\n```',
    'Sure! Here is my move: {"thought":"x","action":"thrust","footwork":"advance"} hope that helps',
    '{"action":"INVALID_MOVE","footwork":"warp","thought":"bad"}',
]
for t in tests:
    print("parse ->", _sanitize(_extract_json(t)))

# prompt contains the sharpness rules?
print("system prompt mentions POMMEL:", "POMMEL" in bb.sys)

# ---------- Phase 5: log integrity ----------
print("\n== PHASE 5 ==")
print("log file:", log_file)
print("keys:", sorted(log.keys()))
t1 = log["turns"][0]
names = [k for k in t1 if k not in ("turn", "hits")]
print("per-turn entries for both fighters:", names)
sample = t1[names[0]]
print("model output schema ok:", sorted(sample.keys()) == ["action", "footwork", "thought"])
print("turns logged:", len(log["turns"]), "| sharp zones recorded:", log["sharp"])
