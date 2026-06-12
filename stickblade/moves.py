"""Macro move library: each action is a keyframe timeline executed over one turn.

Keyframe = (t_frac, pose_dict, arm_power_multiplier)
Poses use intuitive joint angles (see ragdoll.Servo).
A keyframe pose may contain "fire": action_name -> launches an arrow (bow).
"""
from ragdoll import STANCE

# legacy aliases (sword); per-weapon lists live in weapons.WEAPON_ACTIONS
ACTIONS = ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
           "pommel_strike", "guard_high", "guard_low", "ready"]
FOOTWORK = ["advance", "retreat", "lunge", "hold", "hop_back"]

# Which sword zone each strike naturally leads with (for prompts/UI)
ACTION_ZONE = {
    "thrust": "tip", "overhead_slash": "edge", "horizontal_slash": "edge",
    "rising_slash": "back_edge", "pommel_strike": "pommel",
    # flail
    "spin_up": "ball", "overhead_smash": "spikes", "wide_swing": "spikes",
    "yank_back": "chain", "handle_jab": "handle",
    # bow
    "draw_shot": "arrowhead", "quick_shot": "arrowhead",
    "high_arc_shot": "arrowhead", "bow_bash": "bow_limb",
}

_G_HIGH = {"shoulder": 1.25, "elbow": 1.6, "grip": 1.05, "lean": 0.02,
           "off_shoulder": 0.3, "off_elbow": 1.1}
_G_LOW = {"shoulder": 0.35, "elbow": 0.95, "grip": -0.85, "lean": 0.1,
          "off_shoulder": 0.3, "off_elbow": 1.1}

MOVES = {
    "ready": [(0.0, dict(STANCE), 1.0)],
    "guard_high": [(0.0, _G_HIGH, 1.6), (0.85, dict(STANCE), 1.0)],
    "guard_low": [(0.0, _G_LOW, 1.6), (0.85, dict(STANCE), 1.0)],

    "thrust": [
        (0.0, {"shoulder": 0.95, "elbow": 2.05, "grip": 0.1, "lean": -0.06}, 1.2),
        (0.22, {"shoulder": 1.55, "elbow": 0.1, "grip": 0.0, "lean": 0.30,
                "off_shoulder": -0.5, "off_elbow": 0.4}, 3.6),
        (0.52, dict(STANCE), 1.0),
    ],
    "overhead_slash": [
        (0.0, {"shoulder": 2.95, "elbow": 1.35, "grip": 0.95, "lean": -0.18}, 1.4),
        (0.28, {"shoulder": 0.85, "elbow": 0.3, "grip": -0.75, "lean": 0.34,
                "off_shoulder": -0.4}, 4.0),
        (0.62, dict(STANCE), 1.0),
    ],
    "horizontal_slash": [
        (0.0, {"shoulder": 1.35, "elbow": 2.3, "grip": 0.7, "lean": -0.12}, 1.4),
        (0.26, {"shoulder": 1.5, "elbow": 0.1, "grip": -0.35, "lean": 0.3,
                "off_shoulder": -0.45}, 3.8),
        (0.6, dict(STANCE), 1.0),
    ],
    "rising_slash": [
        (0.0, {"shoulder": -0.45, "elbow": 0.55, "grip": -0.6, "lean": 0.2}, 1.4),
        (0.26, {"shoulder": 2.35, "elbow": 0.35, "grip": 0.9, "lean": -0.12,
                "off_shoulder": -0.3}, 3.8),
        (0.62, dict(STANCE), 1.0),
    ],
    "pommel_strike": [
        (0.0, {"shoulder": 1.55, "elbow": 2.35, "grip": 1.3, "lean": -0.05}, 1.4),
        (0.24, {"shoulder": 1.45, "elbow": 0.5, "grip": 1.4, "lean": 0.3,
                "off_shoulder": -0.4}, 3.4),
        (0.55, dict(STANCE), 1.0),
    ],

    # ---------------- flail (momentum weapon: circular arm motion) ----------
    "spin_up": [   # whirl overhead to build ball speed; light contact = "ball"
        (0.0, {"shoulder": 2.6, "elbow": 0.5, "grip": 0.9, "lean": -0.05}, 2.2),
        (0.25, {"shoulder": 1.0, "elbow": 1.6, "grip": -0.9, "lean": 0.05}, 2.6),
        (0.5, {"shoulder": 2.8, "elbow": 0.3, "grip": 1.2, "lean": -0.08}, 2.8),
        (0.75, {"shoulder": 1.2, "elbow": 1.4, "grip": -0.7, "lean": 0.05}, 2.8),
    ],
    "overhead_smash": [   # wind high then slam down — spikes if ball is fast
        (0.0, {"shoulder": 3.0, "elbow": 0.4, "grip": 1.2, "lean": -0.22}, 3.2),
        (0.35, {"shoulder": 1.35, "elbow": 0.1, "grip": -0.2, "lean": 0.38,
               "off_shoulder": -0.4}, 5.4),
        (0.9, dict(STANCE), 1.0),
    ],
    "wide_swing": [   # horizontal whirl into the enemy
        (0.0, {"shoulder": -0.5, "elbow": 0.6, "grip": -1.0, "lean": 0.1}, 3.0),
        (0.3, {"shoulder": 1.5, "elbow": 0.1, "grip": 0.6, "lean": 0.3,
                "off_shoulder": -0.45}, 5.4),
        (0.9, dict(STANCE), 1.0),
    ],
    "yank_back": [    # whip the chain back across — defensive cut
        (0.0, {"shoulder": 0.4, "elbow": 0.3, "grip": -1.2, "lean": 0.15}, 2.0),
        (0.3, {"shoulder": 2.2, "elbow": 1.8, "grip": 1.3, "lean": -0.15}, 3.4),
        (0.65, dict(STANCE), 1.0),
    ],
    "handle_jab": [   # short poke with the stick
        (0.0, {"shoulder": 0.9, "elbow": 2.0, "grip": 0.1, "lean": -0.05}, 1.4),
        (0.25, {"shoulder": 1.5, "elbow": 0.2, "grip": 0.0, "lean": 0.28}, 3.2),
        (0.55, dict(STANCE), 1.0),
    ],

    # ---------------- bow (ranged; "fire" key launches the arrow) ----------
    "draw_shot": [   # full draw: long aim, powerful arrow at t=0.55
        (0.0, {"shoulder": 1.5, "elbow": 0.2, "grip": 0.0, "lean": 0.04,
               "off_shoulder": 1.5, "off_elbow": 2.2}, 1.6),
        (0.55, {"fire": "draw_shot", "off_elbow": 0.3}, 1.6),
        (0.8, dict(STANCE), 1.0),
    ],
    "quick_shot": [  # snap shot: fires early, weaker
        (0.0, {"shoulder": 1.45, "elbow": 0.3, "grip": 0.0,
               "off_shoulder": 1.4, "off_elbow": 1.8}, 1.5),
        (0.25, {"fire": "quick_shot", "off_elbow": 0.3}, 1.5),
        (0.55, dict(STANCE), 1.0),
    ],
    "high_arc_shot": [  # lob over a guard
        (0.0, {"shoulder": 2.1, "elbow": 0.25, "grip": 0.3, "lean": -0.1,
               "off_shoulder": 2.0, "off_elbow": 2.2}, 1.6),
        (0.5, {"fire": "high_arc_shot", "off_elbow": 0.3}, 1.6),
        (0.8, dict(STANCE), 1.0),
    ],
    "bow_bash": [    # melee whack with the stave
        (0.0, {"shoulder": 2.4, "elbow": 1.2, "grip": 0.7, "lean": -0.15}, 1.6),
        (0.28, {"shoulder": 0.8, "elbow": 0.3, "grip": -0.6, "lean": 0.3}, 3.6),
        (0.62, dict(STANCE), 1.0),
    ],
}


class MoveController:
    """Drives one fighter through its chosen action + footwork for a turn.

    arrow_mgr/enemy are optional (bow support): when a keyframe contains
    "fire", an arrow is launched at the enemy's current torso position.
    """

    def __init__(self, fighter, action, footwork, arrow_mgr=None, enemy=None):
        self.f = fighter
        self.action = action if action in MOVES else "ready"
        self.footwork = footwork if footwork in FOOTWORK else "hold"
        self.keys = MOVES[self.action]
        self.idx = -1
        self.lunged = False
        self.arrow_mgr = arrow_mgr
        self.enemy = enemy
        fighter.last_action = self.action

    def update(self, t_frac):
        f = self.f
        if f.dead:
            return
        # keyframes
        while self.idx + 1 < len(self.keys) and t_frac >= self.keys[self.idx + 1][0]:
            self.idx += 1
            _, pose, power = self.keys[self.idx]
            fire = pose.get("fire")
            if fire and self.arrow_mgr and self.enemy and not self.enemy.dead:
                from weapons import BOW_SHOTS
                speed, lift = BOW_SHOTS.get(fire, (700.0, 0.05))
                self.arrow_mgr.fire(self.enemy.pos(), speed, lift)
            f.set_pose({k: v for k, v in pose.items() if k != "fire"})
            f.set_arm_power(power)
        # footwork
        if self.footwork == "lunge":
            f.foot_mode = "lunge" if t_frac < 0.45 else "hold"
            if not self.lunged and t_frac >= 0.06:
                self.lunged = True
                t = f.bodies["torso"]
                t.apply_impulse_at_world_point((f.facing * 9500, 1300), t.position)
        elif self.footwork == "hop_back":
            f.foot_mode = "retreat"
            if not self.lunged and t_frac >= 0.05:
                self.lunged = True
                t = f.bodies["torso"]
                t.apply_impulse_at_world_point((-f.facing * 8200, 4200), t.position)
        elif self.footwork in ("advance", "retreat"):
            f.foot_mode = self.footwork if t_frac < 0.8 else "hold"
        else:
            f.foot_mode = "hold"
