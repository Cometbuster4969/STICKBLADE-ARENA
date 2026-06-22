"""Weapon system: sword, flail, bow.

Each weapon defines:
  - physics construction (bodies/shapes/joints attached to the forearm)
  - damage zones (what can be "sharpened" by the user)
  - which macro actions it supports
  - per-step behavior (e.g. arrow flight)

Zones per weapon:
  sword: tip, edge, back_edge, pommel
  flail: ball, spikes, chain, handle      (spikes = ball moving FAST)
  bow:   arrowhead, arrow_shaft, bow_limb (limb = melee whack with the bow)
"""
import math
import pymunk
from pymunk import Vec2d
import config as C

WEAPONS = ["sword", "flail", "bow", "dagger", "spear"]

WEAPON_ZONES = {
    "sword":  ["tip", "edge", "back_edge", "pommel"],
    "dagger": ["tip", "edge", "back_edge", "pommel"],   # same anatomy, shorter
    "spear":  ["tip", "shaft", "butt"],                 # long pole + spike
    "flail":  ["ball", "spikes", "chain", "handle"],
    "bow":    ["arrowhead", "arrow_shaft", "bow_limb"],
}

# Per-blade geometry (used by build_blade, render.py, combat.py, player.js).
# pommel/handle/tip are pymunk local-Y; r = capsule radius; mass in kg.
# tip_frac = fraction of the blade-span (handle->tip) counted as "tip" zone.
WEAPON_GEOMETRY = {
    "sword":  {"pommel": -34.0, "handle": -26.0, "tip": 52.0, "tip_frac": 0.72, "r": 2.6, "mass": 1.9},
    "dagger": {"pommel": -18.0, "handle": -12.0, "tip": 22.0, "tip_frac": 0.55, "r": 2.2, "mass": 0.8},
    "spear":  {"pommel": -10.0, "handle":  -6.0, "tip": 98.0, "tip_frac": 0.85, "r": 2.0, "mass": 2.3},
}

# Macro actions per weapon (moves.py defines the timelines)
WEAPON_ACTIONS = {
    "sword":  ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
               "pommel_strike", "guard_high", "guard_low", "ready"],
    # Dagger: same vocabulary as sword (the engine reuses the same keyframes;
    # the dagger just hits faster because the blade is lighter & shorter).
    "dagger": ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
               "pommel_strike", "guard_high", "guard_low", "ready"],
    # Spear: pole weapon — same macros but the long shaft favors thrusts.
    "spear":  ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
               "pommel_strike", "guard_high", "guard_low", "ready"],
    "flail":  ["spin_up", "overhead_smash", "wide_swing", "yank_back",
               "handle_jab", "guard_high", "guard_low", "ready"],
    "bow":    ["draw_shot", "quick_shot", "high_arc_shot", "bow_bash",
               "guard_high", "guard_low", "ready"],
}

# Which zone each attack action leads with (prompting + strategy stats)
WEAPON_ACTION_ZONE = {
    "sword":  {"thrust": "tip", "overhead_slash": "edge",
               "horizontal_slash": "edge", "rising_slash": "back_edge",
               "pommel_strike": "pommel"},
    # dagger leads zones identically to a sword
    "dagger": {"thrust": "tip", "overhead_slash": "edge",
               "horizontal_slash": "edge", "rising_slash": "back_edge",
               "pommel_strike": "pommel"},
    # spear: slashes brush with the shaft; only thrust + pommel_strike are
    # "tip" / "butt" plays. We coarsely remap the legacy actions:
    "spear":  {"thrust": "tip", "overhead_slash": "shaft",
               "horizontal_slash": "shaft", "rising_slash": "shaft",
               "pommel_strike": "butt"},
    "flail":  {"spin_up": "ball", "overhead_smash": "spikes",
               "wide_swing": "spikes", "yank_back": "chain",
               "handle_jab": "handle"},
    "bow":    {"draw_shot": "arrowhead", "quick_shot": "arrowhead",
               "high_arc_shot": "arrowhead", "bow_bash": "bow_limb"},
}

WEAPON_HINTS = {
    "sword":  "tip=far end | edge=side facing enemy | back_edge=far side | pommel=handle butt.",
    "dagger": ("tip=far end | edge=enemy-facing side | back_edge=far side | pommel=handle butt. "
               "DAGGER is short and light — your range is TINY. You MUST close to clinch "
               "distance (<70) before strikes land. Once inside, your attacks recover faster "
               "than a sword's."),
    "spear":  ("tip=spike at the far end | shaft=long pole between your hands and the tip | "
               "butt=the back end. SPEAR has the longest reach of any melee weapon (~100 px). "
               "Use thrust at distance 120-180 — that's your kill zone. Don't let the enemy "
               "close inside the shaft; if they clinch, pommel_strike or back out."),
    "flail":  ("ball=the head at ANY speed | spikes=the ball at HIGH speed (a slow ball "
               "is just 'ball') | chain=the links | handle=the stick. The flail builds "
               "momentum: spin_up first, then smash/swing hits MUCH harder."),
    "bow":    ("YOU ARE AN ARCHER — your damage comes from SHOOTING ARROWS, not "
               "from melee. draw_shot/quick_shot/high_arc_shot all FIRE an arrow "
               "at the enemy; bow_bash is a last-resort emergency melee strike "
               "with the bow stave and should ONLY be used when the enemy is "
               "literally touching you (distance < 50). At every other distance, "
               "PICK A SHOT ACTION. Zone meanings: arrowhead=front of a FIRED "
               "arrow (sharp tip damage), arrow_shaft=side of a fired arrow, "
               "bow_limb=the bow stave when used as a club. draw_shot=power "
               "shot (slow wind-up, hits hard), quick_shot=snap shot (fast, "
               "weaker), high_arc_shot=lobbed shot to clear obstacles or guards. "
               "You have unlimited arrows. Each shot consumes the whole turn. "
               "Arrows fly straight at the enemy's CURRENT position — they do "
               "NOT track, so if the enemy is moving, lead the shot or pick "
               "quick_shot for less flight time."),
}

# flail: ball must move at least this fast for "spikes" zone to apply
SPIKE_SPEED = 200.0

# bow shot parameters per action: (speed, angle_up_radians)
BOW_SHOTS = {
    "draw_shot": (980.0, 0.06),
    "quick_shot": (640.0, 0.04),
    "high_arc_shot": (760.0, 0.55),
}
ARROW_LEN = 34.0
ARROW_MASS = 0.4
MAX_LIVE_ARROWS = 6        # per fighter; oldest culled
ARROW_LIFE = 6.0           # seconds before an arrow despawns

CT_ARROW = {1: 31, 2: 32}  # collision types (extends ragdoll's CT_*)


# ===================================================================== blade (sword / dagger / spear)
def build_blade(fighter, space, hand, f):
    """Generic single-segment hand weapon. Geometry is per-weapon (see
    WEAPON_GEOMETRY); sword / dagger / spear all use this builder. The active
    geo is also stashed onto the fighter so combat.py / render.py / the
    web player can render the correct length."""
    geo = WEAPON_GEOMETRY[fighter.weapon]
    fighter.geo = geo            # exposed for combat + render
    g0 = 0.55
    ang = math.pi + f * g0
    sw = pymunk.Body(geo["mass"], pymunk.moment_for_segment(
        geo["mass"], (0, geo["pommel"]), (0, geo["tip"]), geo["r"]))
    grip_local = Vec2d(0, geo["handle"])
    sw.angle = ang
    sw.position = hand - grip_local.rotated(ang)
    blade = pymunk.Segment(sw, (0, geo["pommel"]), (0, geo["tip"]), geo["r"])
    blade.friction = 0.4
    blade.elasticity = 0.1
    blade.filter = fighter.filter
    from ragdoll import CT_SWORD
    blade.collision_type = CT_SWORD[fighter.fid]
    blade.fighter = fighter
    blade.part = "sword"
    space.add(sw, blade)
    fighter.bodies["sword"], fighter.shapes["sword"] = sw, blade
    # dagger gets a tighter grip cone (less wrist range), spear gets more
    grip_range = {"sword": 1.45, "dagger": 1.25, "spear": 1.65}.get(fighter.weapon, 1.45)
    return sw, {"grip_pivot": hand, "grip_offset": math.pi,
                "grip_lo": -grip_range, "grip_hi": grip_range}


# back-compat alias (old callers may import build_sword by name)
build_sword = build_blade


# ===================================================================== flail
FLAIL_HANDLE_LEN = 26.0
FLAIL_LINKS = 3
FLAIL_LINK_LEN = 9.0
FLAIL_BALL_R = 7.0
FLAIL_BALL_MASS = 1.1


def build_flail(fighter, space, hand, f):
    from ragdoll import CT_SWORD
    ang = math.pi + f * 0.55
    # handle (rigid stick gripped like a sword)
    hb = pymunk.Body(0.9, pymunk.moment_for_segment(0.9, (0, -8), (0, FLAIL_HANDLE_LEN), 2.6))
    grip_local = Vec2d(0, 0)
    hb.angle = ang
    hb.position = hand - grip_local.rotated(ang)
    hs = pymunk.Segment(hb, (0, -8), (0, FLAIL_HANDLE_LEN), 2.6)
    hs.friction = 0.4
    hs.filter = fighter.filter
    hs.collision_type = CT_SWORD[fighter.fid]
    hs.fighter = fighter
    hs.part = "weapon"
    space.add(hb, hs)
    fighter.bodies["sword"] = hb           # "sword" slot = the gripped body
    fighter.shapes["sword"] = hs

    # chain links
    prev = hb
    prev_anchor = (0, FLAIL_HANDLE_LEN)
    chain_bodies = []
    for i in range(FLAIL_LINKS):
        lb = pymunk.Body(0.18, pymunk.moment_for_segment(0.18, (0, 0), (0, FLAIL_LINK_LEN), 1.6))
        world_anchor = prev.local_to_world(prev_anchor)
        lb.angle = ang
        lb.position = world_anchor - Vec2d(0, 0).rotated(ang)
        ls = pymunk.Segment(lb, (0, 0), (0, FLAIL_LINK_LEN), 1.6)
        ls.friction = 0.3
        ls.filter = fighter.filter
        ls.collision_type = CT_SWORD[fighter.fid]
        ls.fighter = fighter
        ls.part = "weapon"
        space.add(lb, ls)
        piv = pymunk.PivotJoint(prev, lb, world_anchor)
        piv.collide_bodies = False
        space.add(piv)
        fighter.bodies[f"flail_link{i}"] = lb
        fighter.shapes[f"flail_link{i}"] = ls
        chain_bodies.append(lb)
        prev, prev_anchor = lb, (0, FLAIL_LINK_LEN)

    # ball
    bb = pymunk.Body(FLAIL_BALL_MASS, pymunk.moment_for_circle(FLAIL_BALL_MASS, 0, FLAIL_BALL_R))
    world_anchor = prev.local_to_world(prev_anchor)
    bb.position = world_anchor + Vec2d(0, FLAIL_BALL_R).rotated(ang)
    bs = pymunk.Circle(bb, FLAIL_BALL_R)
    bs.friction = 0.25
    bs.elasticity = 0.2
    bs.filter = fighter.filter
    bs.collision_type = CT_SWORD[fighter.fid]
    bs.fighter = fighter
    bs.part = "weapon"
    space.add(bb, bs)
    piv = pymunk.PivotJoint(prev, bb, world_anchor)
    piv.collide_bodies = False
    space.add(piv)
    fighter.bodies["flail_ball"] = bb
    fighter.shapes["flail_ball"] = bs
    return hb, {"grip_pivot": hand, "grip_offset": math.pi,
                "grip_lo": -1.75, "grip_hi": 1.75}


# ===================================================================== bow
BOW_LEN = 46.0   # half-length of the bow stave


def build_bow(fighter, space, hand, f):
    from ragdoll import CT_SWORD
    ang = math.pi + f * 0.25
    bb = pymunk.Body(1.1, pymunk.moment_for_segment(1.1, (0, -BOW_LEN), (0, BOW_LEN), 2.4))
    bb.angle = ang
    bb.position = hand
    stave = pymunk.Segment(bb, (0, -BOW_LEN), (0, BOW_LEN), 2.4)
    stave.friction = 0.5
    stave.filter = fighter.filter
    stave.collision_type = CT_SWORD[fighter.fid]
    stave.fighter = fighter
    stave.part = "weapon"
    space.add(bb, stave)
    fighter.bodies["sword"] = bb
    fighter.shapes["sword"] = stave
    return bb, {"grip_pivot": hand, "grip_offset": math.pi,
                "grip_lo": -1.1, "grip_hi": 1.1}


BUILDERS = {
    "sword":  build_blade,
    "dagger": build_blade,
    "spear":  build_blade,
    "flail":  build_flail,
    "bow":    build_bow,
}


# ===================================================================== arrows
class ArrowManager:
    """Spawns, tracks and culls arrows for one fighter."""

    def __init__(self, space, fighter):
        self.space = space
        self.f = fighter
        self.arrows = []          # [(body, shape, born_time)]
        self.time = 0.0

    def fire(self, target_pos, speed, lift):
        bow = self.f.bodies["sword"]
        start = bow.position + Vec2d(self.f.facing * 18, 8)
        d = (Vec2d(*target_pos) - start)
        if d.length < 1:
            d = Vec2d(self.f.facing, 0)
        # ballistic compensation: aim above target to cancel gravity drop
        flight_t = d.length / max(speed, 1.0)
        drop = 0.5 * abs(C.GRAVITY[1]) * flight_t * flight_t
        aim = Vec2d(d.x, d.y + drop)
        direction = aim.normalized().rotated(
            lift * (1 if d.x * self.f.facing >= 0 else -1))
        ang = math.atan2(direction.y, direction.x) - math.pi / 2
        ab = pymunk.Body(ARROW_MASS, pymunk.moment_for_segment(
            ARROW_MASS, (0, 0), (0, ARROW_LEN), 1.4))
        ab.position = start
        ab.angle = ang
        ab.velocity = direction * speed
        ash = pymunk.Segment(ab, (0, 0), (0, ARROW_LEN), 1.4)
        ash.friction = 0.8
        ash.filter = self.f.filter
        ash.collision_type = CT_ARROW[self.f.fid]
        ash.fighter = self.f
        ash.part = "arrow"
        self.space.add(ab, ash)
        self.arrows.append([ab, ash, self.time])
        if len(self.arrows) > MAX_LIVE_ARROWS:
            self._remove(self.arrows.pop(0))

    def _remove(self, rec):
        try:
            self.space.remove(rec[0], rec[1])
        except Exception:
            pass

    def update(self, dt):
        self.time += dt
        keep = []
        for rec in self.arrows:
            body = rec[0]
            body.pre_speed = body.velocity.length   # pre-collision speed
            # despawn old or stopped arrows
            if self.time - rec[2] > ARROW_LIFE or \
               (body.velocity.length < 30 and self.time - rec[2] > 0.8):
                self._remove(rec)
                continue
            # align arrow with velocity while flying fast (no tumble)
            v = body.velocity
            if v.length > 120:
                body.angle = math.atan2(v.y, v.x) - math.pi / 2
                body.angular_velocity = 0
            keep.append(rec)
        self.arrows = keep

    def positions(self):
        """For replay capture: [(x, y, angle), ...]"""
        return [(round(r[0].position.x, 1), round(r[0].position.y, 1),
                 round(r[0].angle, 3)) for r in self.arrows]


# ===================================================================== zones
def classify_flail_zone(fighter, contact_shape, contact_world, rel_speed):
    part = None
    for name in ("flail_ball",) + tuple(f"flail_link{i}" for i in range(FLAIL_LINKS)):
        if name in fighter.shapes and fighter.shapes[name] is contact_shape:
            part = name
            break
    if part is None:
        return "handle"
    if part == "flail_ball":
        return "spikes" if rel_speed >= SPIKE_SPEED else "ball"
    return "chain"


def classify_bow_zone(contact_shape):
    if getattr(contact_shape, "part", "") == "arrow":
        # head vs shaft decided by contact point along the arrow in combat.py
        return "arrowhead"
    return "bow_limb"
