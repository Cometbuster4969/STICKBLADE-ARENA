"""Raw Joint Control mode — true Toribash.

The LLM is the raw nervous system: each turn it sets a state for every joint:
    flex   -> drive joint toward its positive human limit at full power
    extend -> drive joint toward its negative limit at full power
    hold   -> lock the joint at its current angle
    relax  -> cut muscle power (joint goes floppy under gravity/momentum)

Footwork commands stay available (locomotion), and the engine's balance
assist stays on — without it every fight is pure floor-flopping.
"""
from moves import FOOTWORK

JOINTS = ["neck", "shoulder", "elbow", "grip", "off_shoulder", "off_elbow",
          "hip_f", "knee_f", "hip_b", "knee_b"]
JOINT_STATES = ["flex", "extend", "hold", "relax"]

# fraction of range used as the drive target (full limit looks hyper-rigid)
DRIVE_FRACTION = 0.97
FLEX_POWER = 3.2          # muscle power multiplier while flexing/extending
RELAX_POWER = 0.04


class JointController:
    """Drives one fighter from a raw joint-state dict for one turn.

    Replaces MoveController in the turn loop (same .update(t_frac) API).
    """

    def __init__(self, fighter, joint_states: dict, footwork: str):
        self.f = fighter
        self.footwork = footwork if footwork in FOOTWORK else "hold"
        self.states = {}
        for j in JOINTS:
            s = str(joint_states.get(j, "hold")).lower()
            self.states[j] = s if s in JOINT_STATES else "hold"
        self.applied = False
        self.lunged = False
        fighter.last_action = self._summary()

    def _summary(self):
        active = [f"{j}:{s}" for j, s in self.states.items() if s != "hold"]
        return "joints(" + (",".join(active[:4]) or "all hold") + ")"

    def _apply(self):
        for j, state in self.states.items():
            servo = self.f.servos[j]
            if state == "flex":
                servo.set_target(servo.hi * DRIVE_FRACTION)
                servo.set_power(FLEX_POWER)
            elif state == "extend":
                servo.set_target(servo.lo * DRIVE_FRACTION)
                servo.set_power(FLEX_POWER)
            elif state == "relax":
                servo.set_power(RELAX_POWER)
            else:  # hold — lock at the current angle with normal strength
                servo.set_target(servo.current_intuitive())
                servo.set_power(1.0)
        self.applied = True

    def update(self, t_frac):
        f = self.f
        if f.dead:
            return
        if not self.applied:
            self._apply()
        # footwork identical to macro mode
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


# ------------------------------------------------------------------ prompt
JOINT_SYSTEM_PROMPT = """You are the raw nervous system of a stickman swordsman in a physics duel (like Toribash).
Each turn you set a state for EVERY joint; physics then runs for 3 seconds.

Joint states: flex (drive to positive limit, full power) | extend (drive to negative limit) | hold (lock current angle) | relax (go floppy).
Joints: {joints}
  shoulder/elbow/grip control your SWORD ARM (grip tilts the sword in your hand).
  flexing shoulder raises the arm forward/up; extending swings it down/back.
  flexing elbow bends the arm; extending straightens it.
  hip_f/knee_f and hip_b/knee_b are your front and back legs (stance & balance).

WEAPON RULES (critical): only these sword zones are SHARP and deal damage: {sharp}.
Zone geometry: tip = far end of the blade; edge = side facing the enemy;
back_edge = side facing away; pommel = bottom of the handle.
A fast SHARP hit to the enemy head is an INSTANT KILL. Blunt contact only shoves.

Footwork (movement is separate from joints): {footwork}
  lunge = explosive forward burst | hop_back = jump backward.

Distance guide: <70 clinch, 70-150 strike range, 150-260 closing, >260 far.
Tactics hint: a swing = wind up (extend shoulder) one turn, then flex shoulder+elbow hard the next. A thrust = extend elbow while flexing shoulder, lunging forward.

Reply with ONLY a JSON object, no markdown:
{{"thought": "<max 30 words>", "joints": {{"neck": "...", "shoulder": "...", "elbow": "...", "grip": "...", "off_shoulder": "...", "off_elbow": "...", "hip_f": "...", "knee_f": "...", "hip_b": "...", "knee_b": "..."}}, "footwork": "..."}}"""


def build_joint_system_prompt(sharp_zones):
    return JOINT_SYSTEM_PROMPT.format(
        joints=", ".join(JOINTS),
        sharp=", ".join(sharp_zones).upper(),
        footwork=", ".join(FOOTWORK))


def sanitize_joint_reply(d):
    """Validate an LLM joint-mode reply into {thought, joints, footwork}."""
    joints_in = d.get("joints", {}) if isinstance(d.get("joints"), dict) else {}
    joints = {}
    for j in JOINTS:
        s = str(joints_in.get(j, "hold")).lower()
        joints[j] = s if s in JOINT_STATES else "hold"
    fw = d.get("footwork", "hold")
    if fw not in FOOTWORK:
        fw = "hold"
    return {"thought": str(d.get("thought", ""))[:160],
            "joints": joints, "footwork": fw}


# ------------------------------------------------------------------ mock
import random


class MockJointBrain:
    """Scripted joint-mode fighter so the mode works without API keys.
    Alternates wind-up / strike, walking in. Deliberately crude — raw joint
    mode is SUPPOSED to look chaotic."""

    label = "Mock-jointer"

    def __init__(self, sharp_zones, label=None):
        self.sharp = sharp_zones
        if label:
            self.label = label
        self.phase = 0

    def decide(self, state):
        d = state["distance"]
        wind = {"neck": "hold", "shoulder": "extend", "elbow": "flex",
                "grip": "hold", "off_shoulder": "extend", "off_elbow": "flex",
                "hip_f": "flex", "knee_f": "flex", "hip_b": "hold", "knee_b": "hold"}
        strike = {"neck": "hold", "shoulder": "flex", "elbow": "extend",
                  "grip": "extend", "off_shoulder": "extend", "off_elbow": "hold",
                  "hip_f": "hold", "knee_f": "hold", "hip_b": "flex", "knee_b": "extend"}
        if d > 200:
            mv = {"thought": "Walk in while winding the arm back.",
                  "joints": wind, "footwork": "advance"}
        elif self.phase % 2 == 0:
            mv = {"thought": "Wind up — coil the sword arm.",
                  "joints": wind, "footwork": "advance"}
        else:
            mv = {"thought": "Release! Whip the arm through.",
                  "joints": strike,
                  "footwork": "lunge" if d > 110 else "hold"}
        self.phase += 1
        # tiny chaos so mirror matches diverge
        if random.random() < 0.2:
            j = random.choice(JOINTS)
            mv["joints"][j] = random.choice(JOINT_STATES)
        return sanitize_joint_reply(mv)

    def decide_with_timeout(self, state):
        return self.decide(state)
