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

WEAPONS = ["sword", "flail", "bow"]

WEAPON_ZONES = {
    "sword": ["tip", "edge", "back_edge", "pommel"],
    "flail": ["ball", "spikes", "chain", "handle"],
    "bow":   ["arrowhead", "arrow_shaft", "bow_limb"],
}

# Macro actions per weapon (moves.py defines the timelines)
WEAPON_ACTIONS = {
    "sword": ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
              "pommel_strike", "guard_high", "guard_low", "ready"],
    "flail": ["spin_up", "overhead_smash", "wide_swing", "yank_back",
              "handle_jab", "guard_high", "guard_low", "ready"],
    "bow":   ["draw_shot", "quick_shot", "high_arc_shot", "bow_bash",
              "guard_high", "guard_low", "ready"],
}

# Which zone each attack action leads with (prompting + strategy stats)
WEAPON_ACTION_ZONE = {
    "sword": {"thrust": "tip", "overhead_slash": "edge",
              "horizontal_slash": "edge", "rising_slash": "back_edge",
              "pommel_strike": "pommel"},
    "flail": {"spin_up": "ball", "overhead_smash": "spikes",
              "wide_swing": "spikes", "yank_back": "chain",
              "handle_jab": "handle"},
    "bow":   {"draw_shot": "arrowhead", "quick_shot": "arrowhead",
              "high_arc_shot": "arrowhead", "bow_bash": "bow_limb"},
}

WEAPON_HINTS = {
    "sword": "tip=far end | edge=side facing enemy | back_edge=far side | pommel=handle butt.",
    "flail": ("ball=the head at ANY speed | spikes=the ball at HIGH speed (a slow ball "
              "is just 'ball') | chain=the links | handle=the stick. The flail builds "
              "momentum: spin_up first, then smash/swing hits MUCH harder."),
    "bow":   ("arrowhead=front of a FIRED arrow | arrow_shaft=side of a fired arrow | "
              "bow_limb=the bow itself as a melee club. draw_shot=power shot (slow, "
              "strong), quick_shot=snap shot (fast, weak), high_arc_shot=lobbed. "
              "You have unlimited arrows but each shot takes the whole turn. "
              "Arrows fly straight at the enemy's current position — they do NOT track."),
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


# ===================================================================== sword
def build_sword(fighter, space, hand, f):
    g0 = 0.55
    ang = math.pi + f * g0
    sw = pymunk.Body(1.9, pymunk.moment_for_segment(
        1.9, (0, C.SWORD_POMMEL), (0, C.SWORD_TIP), C.SWORD_R))
    grip_local = Vec2d(0, C.SWORD_HANDLE)
    sw.angle = ang
    sw.position = hand - grip_local.rotated(ang)
    blade = pymunk.Segment(sw, (0, C.SWORD_POMMEL), (0, C.SWORD_TIP), C.SWORD_R)
    blade.friction = 0.4
    blade.elasticity = 0.1
    blade.filter = fighter.filter
    from ragdoll import CT_SWORD
    blade.collision_type = CT_SWORD[fighter.fid]
    blade.fighter = fighter
    blade.part = "sword"
    space.add(sw, blade)
    fighter.bodies["sword"], fighter.shapes["sword"] = sw, blade
    return sw, {"grip_pivot": hand, "grip_offset": math.pi,
                "grip_lo": -1.45, "grip_hi": 1.45}


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


BUILDERS = {"sword": build_sword, "flail": build_flail, "bow": build_bow}


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
