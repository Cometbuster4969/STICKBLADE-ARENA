"""Sword-zone collision handling and damage calculation."""
import time
import pymunk
import config as C
from ragdoll import CT_BODY, CT_SWORD


def classify_zone(sword_body, contact_world, attacker, victim):
    """Return which sword zone made contact: tip / edge / back_edge / pommel."""
    import math
    local = sword_body.world_to_local(contact_world)
    y = local.y
    if y <= C.SWORD_HANDLE + 4:
        return "pommel"
    span = C.SWORD_TIP - C.SWORD_HANDLE
    if y >= C.SWORD_HANDLE + C.SWORD_TIP_FRAC * span:
        return "tip"
    # which flat of the blade faces the victim? (sword local +X axis in world)
    to_victim = victim.pos() - sword_body.position
    ca, sa = math.cos(sword_body.angle), math.sin(sword_body.angle)
    xaxis = pymunk.Vec2d(ca, sa)
    return "edge" if xaxis.dot(to_victim) >= 0 else "back_edge"


class CombatSystem:
    def __init__(self, space, fighters, sharp_zones, fx):
        self.space = space
        self.fighters = fighters       # {1: Fighter, 2: Fighter}
        self.sharp = set(sharp_zones)  # e.g. {"tip"} or {"edge","tip"}
        self.fx = fx                   # callbacks: fx.hit(pos, dmg, sharp, lethal)
        self.cooldowns = {}            # (atk_id, part_shape_id) -> time
        self.events = []               # log of this turn's hits
        self.sim_time = 0.0
        for atk in (1, 2):
            vic = 2 if atk == 1 else 1
            space.on_collision(CT_SWORD[atk], CT_BODY[vic],
                               post_solve=self._make_handler(atk, vic))
        # sword vs sword spark
        space.on_collision(CT_SWORD[1], CT_SWORD[2], post_solve=self._clash)

    def _clash(self, arb, space, data):
        if arb.is_first_contact and arb.total_ke > 2.0e5:
            pts = arb.contact_point_set.points
            if pts:
                self.fx.clash(pts[0].point_a)

    def _make_handler(self, atk_id, vic_id):
        def handler(arb, space, data):
            attacker = self.fighters[atk_id]
            victim = self.fighters[vic_id]
            if victim.dead or attacker.dead:
                return
            pts = arb.contact_point_set.points
            if not pts:
                return
            p = pts[0].point_a
            sword_shape, part_shape = arb.shapes
            if part_shape.collision_type == CT_SWORD[atk_id]:
                sword_shape, part_shape = part_shape, sword_shape
            # one damage event per swing: global per-attacker cooldown
            gkey = ("atk", atk_id)
            if self.sim_time - self.cooldowns.get(gkey, -99) < C.SWING_COOLDOWN:
                return
            key = (atk_id, id(part_shape))
            if self.sim_time - self.cooldowns.get(key, -99) < C.HIT_COOLDOWN:
                return
            sw = attacker.bodies["sword"]
            rel_v = (sw.velocity_at_world_point(p)
                     - part_shape.body.velocity_at_world_point(p)).length
            zone = classify_zone(sw, p, attacker, victim)
            part = getattr(part_shape, "part", "torso")
            sharp = zone in self.sharp
            dmg, lethal = self._damage(zone, part, rel_v, sharp)
            if dmg <= 0.2:
                return
            self.cooldowns[key] = self.sim_time
            self.cooldowns[gkey] = self.sim_time
            victim.take_hit(dmg if not lethal else 999)
            self.events.append({
                "attacker": attacker.name, "victim": victim.name,
                "zone": zone, "part": part, "speed": round(rel_v),
                "damage": round(dmg, 1), "sharp": sharp, "lethal": lethal,
            })
            self.fx.hit(p, dmg, sharp, lethal, part)
        return handler

    def _damage(self, zone, part, speed, sharp):
        if sharp:
            if speed < C.SHARP_SPEED_MIN:
                return 0.0, False
            dmg = min(C.DMG_CAP, (speed - C.SHARP_SPEED_MIN) * C.DMG_SCALE + 4)
            dmg *= C.PART_MULT.get(part, 1.0)
            lethal = part == "head" and speed >= C.KILL_HEAD_SPEED
            return dmg, lethal
        if speed < C.BLUNT_SPEED_MIN:
            return 0.0, False
        return min(C.BLUNT_CAP, (speed - C.BLUNT_SPEED_MIN) * 0.012 + 1.0), False

    def drain_events(self):
        ev, self.events = self.events, []
        return ev
