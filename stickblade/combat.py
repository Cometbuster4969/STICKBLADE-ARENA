"""Sword-zone collision handling and damage calculation."""
import time
import pymunk
import config as C
from ragdoll import CT_BODY, CT_SWORD


def classify_zone(sword_body, contact_world, attacker, victim,
                  contact_shape=None, rel_speed=0.0):
    """Return which weapon zone made contact, weapon-aware."""
    import math
    weapon = getattr(attacker, "weapon", "sword")

    if weapon == "flail":
        from weapons import classify_flail_zone
        return classify_flail_zone(attacker, contact_shape, contact_world,
                                   rel_speed)

    if weapon == "bow":
        if contact_shape is not None and \
           getattr(contact_shape, "part", "") == "arrow":
            from weapons import ARROW_LEN
            local = contact_shape.body.world_to_local(contact_world)
            return "arrowhead" if local.y >= ARROW_LEN * 0.6 else "arrow_shaft"
        return "bow_limb"

    # ---- single-segment blade (sword / dagger / spear) ----
    # Read per-weapon geometry off the attacker; falls back to global SWORD_*
    # for legacy callers (older replays / tests).
    geo = getattr(attacker, "geo", None) or {
        "handle": C.SWORD_HANDLE, "pommel": C.SWORD_POMMEL,
        "tip": C.SWORD_TIP, "tip_frac": C.SWORD_TIP_FRAC,
    }
    local = sword_body.world_to_local(contact_world)
    y = local.y
    handle, tip = geo["handle"], geo["tip"]
    span = tip - handle
    if y <= handle + 4:
        # Pole weapons call the back-end "butt"; blades call it "pommel".
        return "butt" if attacker.weapon == "spear" else "pommel"
    if y >= handle + geo["tip_frac"] * span:
        return "tip"
    # Mid-shaft on a spear is just "shaft"; on blades it's edge/back_edge.
    if attacker.weapon == "spear":
        return "shaft"
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
        from weapons import CT_ARROW
        for atk in (1, 2):
            vic = 2 if atk == 1 else 1
            space.on_collision(CT_SWORD[atk], CT_BODY[vic],
                               post_solve=self._make_handler(atk, vic))
            space.on_collision(CT_ARROW[atk], CT_BODY[vic],
                               post_solve=self._make_handler(atk, vic))
        # weapon vs weapon spark
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
            from weapons import CT_ARROW
            p = pts[0].point_a
            sword_shape, part_shape = arb.shapes
            atk_types = (CT_SWORD[atk_id], CT_ARROW[atk_id])
            if part_shape.collision_type in atk_types:
                sword_shape, part_shape = part_shape, sword_shape
            # one damage event per swing: global per-attacker cooldown
            gkey = ("atk", atk_id)
            if self.sim_time - self.cooldowns.get(gkey, -99) < C.SWING_COOLDOWN:
                return
            key = (atk_id, id(part_shape))
            if self.sim_time - self.cooldowns.get(key, -99) < C.HIT_COOLDOWN:
                return
            hit_body = sword_shape.body          # actual striking body
            rel_v = (hit_body.velocity_at_world_point(p)
                     - part_shape.body.velocity_at_world_point(p)).length
            # arrows: post_solve speed is already absorbed; use pre-impact
            if getattr(sword_shape, "part", "") == "arrow":
                rel_v = max(rel_v, getattr(hit_body, "pre_speed", 0.0))
            zone = classify_zone(attacker.bodies["sword"], p, attacker,
                                 victim, contact_shape=sword_shape,
                                 rel_speed=rel_v)
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
