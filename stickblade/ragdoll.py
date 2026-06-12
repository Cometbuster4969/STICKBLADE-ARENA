"""Ragdoll fighter with human-like joint limits, servo muscles and a zoned sword."""
import math
import pymunk
from pymunk import Vec2d
import config as C

# Collision types
CT_GROUND = 1
CT_BODY = {1: 11, 2: 12}     # fighter id -> body collision type
CT_SWORD = {1: 21, 2: 22}

# Limb dimensions (length, mass, radius)
DIM = {
    "torso":   (56, 13.0, 5.0),
    "head":    (0,   3.5, 11.0),
    "uarm":    (26,  2.0, 3.4),
    "farm":    (24,  1.5, 3.0),
    "thigh":   (30,  4.5, 4.2),
    "shin":    (30,  3.2, 3.6),
}
SWORD_MASS = 1.9

NORMAL_FORCE = {
    "neck": 4.0e5, "shoulder": 1.1e6, "elbow": 8.0e5, "grip": 5.5e5,
    "off_shoulder": 8.0e5, "off_elbow": 6.0e5,
    "hip_f": 2.6e6, "knee_f": 2.2e6, "hip_b": 2.6e6, "knee_b": 2.2e6,
}
ARM_JOINTS = ("shoulder", "elbow", "grip")


class Servo:
    """Drives child's angle relative to parent toward an intuitive target.

    rel = child.angle - parent.angle ; rel_target = offset + sign * intuitive
    """

    def __init__(self, space, parent, child, pivot_world, sign, offset,
                 lim_lo, lim_hi, gain, base_force):
        self.space = space
        self.parent, self.child = parent, child
        self.sign, self.offset = sign, offset
        self.gain, self.base_force = gain, base_force
        self.lo, self.hi = lim_lo, lim_hi      # intuitive-angle limits
        self.target = 0.0
        piv = pymunk.PivotJoint(parent, child, pivot_world)
        piv.collide_bodies = False
        rl_a, rl_b = sorted((offset + sign * lim_lo, offset + sign * lim_hi))
        self.limit = pymunk.RotaryLimitJoint(parent, child, rl_a, rl_b)
        self.motor = pymunk.SimpleMotor(parent, child, 0.0)
        self.motor.max_force = base_force
        space.add(piv, self.limit, self.motor)

    def set_target(self, v):
        self.target = v

    def set_power(self, mult):
        self.motor.max_force = self.base_force * mult

    def current_intuitive(self):
        rel = self.child.angle - self.parent.angle
        return (rel - self.offset) / self.sign

    def flip(self):
        """Mirror this joint (fighter turned around): pose targets and limits
        now interpret intuitive angles in the opposite rotation direction."""
        self.sign = -self.sign
        a, b = sorted((self.offset + self.sign * self.lo,
                       self.offset + self.sign * self.hi))
        self.space.remove(self.limit)
        self.limit = pymunk.RotaryLimitJoint(self.parent, self.child, a, b)
        self.space.add(self.limit)

    def update(self):
        rel = self.child.angle - self.parent.angle
        rel_t = self.offset + self.sign * self.target
        err = rel_t - rel
        self.motor.rate = max(-26.0, min(26.0, -err * self.gain))


class Fighter:
    def __init__(self, space, x, facing, color, dark, name, fid,
                 weapon="sword"):
        self.space, self.x0, self.facing = space, x, facing
        self.color, self.dark, self.name, self.fid = color, dark, name, fid
        self.weapon = weapon
        self.enemy = None          # set by Match; enables enemy-seeking footwork
        self.hp = C.START_HP
        self.dead = False
        self.stun = 0.0
        self.lean_target = 0.0
        self.foot_mode = "hold"
        self.last_action = "ready"
        self.bodies, self.shapes, self.servos = {}, {}, {}
        self.filter = pymunk.ShapeFilter(group=fid)
        self._build(space, x, facing)
        self.stand_torso_y = self.bodies["torso"].position.y

    # ---------------- construction ----------------
    def _limb(self, key, name, pos, part):
        L, m, r = DIM[key]
        if L == 0:
            body = pymunk.Body(m, pymunk.moment_for_circle(m, 0, r))
            body.position = pos
            shape = pymunk.Circle(body, r)
        else:
            body = pymunk.Body(m, pymunk.moment_for_segment(m, (0, L / 2), (0, -L / 2), r))
            body.position = pos
            shape = pymunk.Segment(body, (0, L / 2), (0, -L / 2), r)
        shape.friction = 1.2
        shape.elasticity = 0.05
        shape.filter = self.filter
        shape.collision_type = CT_BODY[self.fid]
        shape.part = part
        shape.fighter = self
        self.space.add(body, shape)
        self.bodies[name], self.shapes[name] = body, shape
        return body

    def _build(self, space, x, f):
        gy = C.FLOOR_Y
        shin_y = gy + 15
        thigh_y = gy + 30 + 15
        hip_y = gy + 60
        torso_y = hip_y + 28
        neck_y = hip_y + 56
        head_y = neck_y + 13

        torso = self._limb("torso", "torso", (x, torso_y), "torso")
        head = self._limb("head", "head", (x, head_y), "head")
        ua = self._limb("uarm", "uarm", (x, neck_y - 6 - 13), "arm")
        fa = self._limb("farm", "farm", (x, neck_y - 6 - 26 - 12), "arm")
        oua = self._limb("uarm", "off_uarm", (x, neck_y - 6 - 13), "arm")
        ofa = self._limb("farm", "off_farm", (x, neck_y - 6 - 26 - 12), "arm")
        tf = self._limb("thigh", "thigh_f", (x, thigh_y), "leg")
        sf = self._limb("shin", "shin_f", (x, shin_y), "leg")
        tb = self._limb("thigh", "thigh_b", (x, thigh_y), "leg")
        sb = self._limb("shin", "shin_b", (x, shin_y), "leg")
        for nm in ("shin_f", "shin_b"):
            self.shapes[nm].friction = 1.6

        # ---- weapon (sword / flail / bow via weapons.py builders) ----
        hand = Vec2d(x, neck_y - 6 - 26 - 24)
        from weapons import BUILDERS
        sw, grip_cfg = BUILDERS.get(self.weapon, BUILDERS["sword"])(
            self, space, hand, f)

        # ---- joints:  (parent, child, pivot, sign, offset, lo, hi, gain) ----
        J = {
            "neck":        (torso, head, (x, neck_y + 2), f, 0, -0.4, 0.4, 7),
            "shoulder":    (torso, ua, (x, neck_y - 6), f, 0, -0.9, 3.05, 9),
            "elbow":       (ua, fa, (x, neck_y - 6 - 26), f, 0, 0.0, 2.55, 10),
            "grip":        (fa, sw, hand, f, grip_cfg["grip_offset"],
                            grip_cfg["grip_lo"], grip_cfg["grip_hi"], 11),
            "off_shoulder": (torso, oua, (x, neck_y - 6), f, 0, -0.9, 3.05, 8),
            "off_elbow":   (oua, ofa, (x, neck_y - 6 - 26), f, 0, 0.0, 2.55, 9),
            "hip_f":       (torso, tf, (x, hip_y), f, 0, -0.65, 1.9, 9),
            "knee_f":      (tf, sf, (x, gy + 30), -f, 0, 0.0, 2.3, 9),
            "hip_b":       (torso, tb, (x, hip_y), f, 0, -0.65, 1.9, 9),
            "knee_b":      (tb, sb, (x, gy + 30), -f, 0, 0.0, 2.3, 9),
        }
        for nm, (p, c, piv, sg, off, lo, hi, gn) in J.items():
            self.servos[nm] = Servo(self.space, p, c, piv, sg, off, lo, hi,
                                    gn, NORMAL_FORCE[nm])
        self.set_pose(STANCE)

    # ---------------- control ----------------
    def set_pose(self, pose):
        for k, v in pose.items():
            if k == "lean":
                self.lean_target = v
            elif k in self.servos:
                self.servos[k].set_target(v)

    def set_arm_power(self, mult):
        for j in ARM_JOINTS:
            self.servos[j].set_power(mult)

    def take_hit(self, dmg):
        if self.dead:
            return
        self.hp = max(0.0, self.hp - dmg)
        if dmg >= 10:
            self.stun = max(self.stun, 0.45 + dmg * 0.012)
        if self.hp <= 0:
            self.die()

    def die(self):
        self.dead = True
        for s in self.servos.values():
            s.motor.max_force = 1.5e4
            s.motor.rate = 0

    # ---------------- per-step physics ----------------
    def update(self, dt):
        if self.stun > 0:
            self.stun = max(0.0, self.stun - dt)
        if self.dead:
            return
        for s in self.servos.values():
            s.update()
        torso = self.bodies["torso"]
        weak = 0.25 if self.stun > 0 else 1.0
        # upright torque (active balance)
        tgt = -self.facing * self.lean_target
        torque = ((tgt - torso.angle) * 5.2e6 - torso.angular_velocity * 5.5e5) * weak
        torso.torque += max(-7e6, min(7e6, torque))
        # leg support force (keeps fighter standing, fails when stunned/dead)
        err = self.stand_torso_y - torso.position.y
        if err > -18:
            fy = (err * 3000 - torso.velocity.y * 520) * weak
            torso.apply_force_at_world_point(
                (0, max(0.0, min(5.2e4, fy))), torso.position)
        # footwork — move toward where the enemy ACTUALLY is (fighters can
        # cross during lunges; spawn-facing alone would walk them apart)
        fdir = self.move_dir()
        vx = torso.velocity.x
        if self.foot_mode == "advance" and vx * fdir < 215:
            torso.apply_force_at_world_point((fdir * 6.5e4, 0), torso.position)
        elif self.foot_mode == "lunge" and vx * fdir < 330:
            torso.apply_force_at_world_point((fdir * 9.0e4, 0), torso.position)
        elif self.foot_mode == "retreat" and -vx * fdir < 175:
            torso.apply_force_at_world_point((-fdir * 5.5e4, 0), torso.position)
        elif self.foot_mode == "hold":
            torso.apply_force_at_world_point((-vx * 95, 0), torso.position)

    # ---------------- queries ----------------
    def turn_around(self):
        """Fighters crossed: flip facing + mirror all joints so poses and
        strikes aim at the enemy again. Called between turns; the servos
        re-pose the body over the next few frames (brief scramble is fine)."""
        if self.dead:
            return
        self.facing *= -1
        for s in self.servos.values():
            s.flip()
        self.set_pose(STANCE)

    def move_dir(self):
        """+1/-1 toward the enemy's current position (falls back to facing)."""
        if self.enemy is not None:
            dx = self.enemy.bodies["torso"].position.x - self.bodies["torso"].position.x
            if abs(dx) > 2:
                return 1 if dx > 0 else -1
        return self.facing

    def pos(self):
        return self.bodies["torso"].position

    def tip_pos(self):
        return self.bodies["sword"].local_to_world((0, C.SWORD_TIP))

    def head_pos(self):
        return self.bodies["head"].position


STANCE = {
    "neck": 0.0, "shoulder": 0.7, "elbow": 1.15, "grip": 0.55,
    "off_shoulder": 0.35, "off_elbow": 0.95,
    "hip_f": 0.38, "knee_f": 0.42, "hip_b": -0.22, "knee_b": 0.3,
    "lean": 0.06,
}


def make_ground(space):
    seg = pymunk.Segment(space.static_body, (-300, C.FLOOR_Y), (C.WIDTH + 300, C.FLOOR_Y), 6)
    seg.friction = 1.5
    seg.elasticity = 0.05
    seg.collision_type = CT_GROUND
    space.add(seg)
    for wx in (60, C.WIDTH - 60):
        w = pymunk.Segment(space.static_body, (wx, 0), (wx, C.HEIGHT), 8)
        w.friction = 0.4
        w.collision_type = CT_GROUND
        space.add(w)
