"""Macro move library: each action is a keyframe timeline executed over one turn.

Keyframe = (t_frac, pose_dict, arm_power_multiplier)
Poses use intuitive joint angles (see ragdoll.Servo).
"""
from ragdoll import STANCE

ACTIONS = ["thrust", "overhead_slash", "horizontal_slash", "rising_slash",
           "pommel_strike", "guard_high", "guard_low", "ready"]
FOOTWORK = ["advance", "retreat", "lunge", "hold", "hop_back"]

# Which sword zone each strike naturally leads with (for prompts/UI)
ACTION_ZONE = {
    "thrust": "tip", "overhead_slash": "edge", "horizontal_slash": "edge",
    "rising_slash": "back_edge", "pommel_strike": "pommel",
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
}


class MoveController:
    """Drives one fighter through its chosen action + footwork for a turn."""

    def __init__(self, fighter, action, footwork):
        self.f = fighter
        self.action = action if action in MOVES else "ready"
        self.footwork = footwork if footwork in FOOTWORK else "hold"
        self.keys = MOVES[self.action]
        self.idx = -1
        self.lunged = False
        fighter.last_action = self.action

    def update(self, t_frac):
        f = self.f
        if f.dead:
            return
        # keyframes
        while self.idx + 1 < len(self.keys) and t_frac >= self.keys[self.idx + 1][0]:
            self.idx += 1
            _, pose, power = self.keys[self.idx]
            f.set_pose(pose)
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
