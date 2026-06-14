"""Raw Joint Control mode — true Toribash.

The LLM is the raw nervous system: each turn it sets a state for every joint:
    flex   -> drive joint toward its positive human limit at full power
    extend -> drive joint toward its negative limit at full power
    hold   -> lock the joint at its current angle
    relax  -> cut muscle power (joint goes floppy under gravity/momentum)

Footwork commands stay available (locomotion), and the engine's balance
assist stays on — without it every fight is pure floor-flopping.

Bow extension (since v2): the reply may also include `"fire": true` which
launches one arrow at the enemy's torso roughly 1.2 s into the 3 s turn.
This is the *only* way to shoot in joint mode (you can still bash with the
stave by flailing your arm). For sword/flail the field is ignored.
"""
from moves import FOOTWORK

JOINTS = ["neck", "shoulder", "elbow", "grip", "off_shoulder", "off_elbow",
          "hip_f", "knee_f", "hip_b", "knee_b"]
JOINT_STATES = ["flex", "extend", "hold", "relax"]

# fraction of range used as the drive target (full limit looks hyper-rigid)
DRIVE_FRACTION = 0.97
FLEX_POWER = 3.2          # muscle power multiplier while flexing/extending
RELAX_POWER = 0.04

# When to release the arrow (fraction of the 3 s turn). Picked so that
# preceding `flex` impulses have had a moment to coil the off-arm into a
# convincing draw before the shot leaves.
BOW_FIRE_T = 0.40


class JointController:
    """Drives one fighter from a raw joint-state dict for one turn.

    Replaces MoveController in the turn loop (same .update(t_frac) API).

    arrow_mgr/enemy are optional. When the fighter's weapon is a bow and
    the LLM's reply contained `"fire": true`, an arrow is launched at the
    enemy's torso once per turn at BOW_FIRE_T.
    """

    def __init__(self, fighter, joint_states: dict, footwork: str,
                 fire: bool = False, arrow_mgr=None, enemy=None):
        self.f = fighter
        self.footwork = footwork if footwork in FOOTWORK else "hold"
        self.states = {}
        for j in JOINTS:
            s = str(joint_states.get(j, "hold")).lower()
            self.states[j] = s if s in JOINT_STATES else "hold"
        self.applied = False
        self.lunged = False
        # bow firing
        self.want_fire = bool(fire) and getattr(fighter, "weapon", "sword") == "bow"
        self.arrow_mgr = arrow_mgr
        self.enemy = enemy
        self.fired = False
        fighter.last_action = self._summary()

    def _summary(self):
        active = [f"{j}:{s}" for j, s in self.states.items() if s != "hold"]
        summary = "joints(" + (",".join(active[:4]) or "all hold") + ")"
        if self.want_fire:
            summary += " +fire"
        return summary

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
        # bow release
        if (self.want_fire and not self.fired and t_frac >= BOW_FIRE_T
                and self.arrow_mgr and self.enemy and not self.enemy.dead):
            from weapons import BOW_SHOTS
            # joint-mode shots use the medium 'quick_shot' profile: a real
            # power draw would need the LLM to explicitly coil first, which
            # joint mode can't easily encode. Quick_shot stays honest about
            # the fact the model just yanked the string.
            speed, lift = BOW_SHOTS.get("quick_shot", (640.0, 0.04))
            self.arrow_mgr.fire(self.enemy.pos(), speed, lift)
            self.fired = True
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
# Per-weapon body text inserted into the joint system prompt. Keeps prompt
# small for tiny free models while still being correct.
_WEAPON_BLOCKS = {
    "sword": (
        "WEAPON: SWORD (melee). Only these zones are SHARP and damaging: {sharp}.\n"
        "  Zone geometry: tip = far end of the blade; edge = side facing the enemy;\n"
        "  back_edge = side facing away; pommel = bottom of the handle.\n"
        "  shoulder/elbow/grip control your SWORD ARM (grip tilts the sword in your hand).\n"
        "  A sword swing = wind up one turn (extend shoulder), then flex shoulder+elbow\n"
        "  hard the next. A thrust = extend elbow while flexing shoulder, lunging forward.\n"
        "  A fast SHARP hit to the enemy head is an INSTANT KILL."
    ),
    "flail": (
        "WEAPON: FLAIL (chain weapon — momentum builds over multiple turns).\n"
        "  Sharp zones: {sharp}. ball=the head at any speed; spikes=the head at HIGH\n"
        "  speed; chain=the links; handle=the gripped stick.\n"
        "  shoulder/elbow/grip control the handle. To build momentum, whirl the arm\n"
        "  in a circle: alternate (flex shoulder + extend elbow) -> (extend shoulder\n"
        "  + flex elbow) for 1-2 turns BEFORE swinging through. Hit at peak speed."
    ),
    "bow": (
        "WEAPON: BOW (RANGED — fire arrows). Sharp zones: {sharp}.\n"
        "  arrowhead=front of a FIRED arrow; arrow_shaft=side of a fired arrow;\n"
        "  bow_limb=the bow itself as a melee club (last resort).\n"
        "  shoulder/elbow hold the bow steady; off_shoulder + off_elbow are the\n"
        "  DRAWING hand. To take a shot, FLEX off_shoulder + FLEX off_elbow this\n"
        "  turn (that 'draws the string') AND set \"fire\": true so an arrow leaves\n"
        "  at ~1.2 s into the turn aimed at the enemy's torso.\n"
        "  An arrowhead hit to the enemy head is an INSTANT KILL.\n"
        "  Keep distance >220 if you can; if the enemy clinches, hop_back."
    ),
}

JOINT_SYSTEM_PROMPT = """You are the raw nervous system of a stickman fighter in a physics duel (like Toribash).
Each turn you set a state for EVERY joint; physics then runs for 3 seconds.

Joint states: flex (drive to positive limit, full power) | extend (drive to negative limit) | hold (lock current angle) | relax (go floppy).
Joints: {joints}
  flexing shoulder raises the arm forward/up; extending swings it down/back.
  flexing elbow bends the arm; extending straightens it.
  hip_f/knee_f and hip_b/knee_b are your front and back legs (stance & balance).

{weapon_block}

You will receive the world coordinates of both fighters' torso and head every
turn under "me", "enemy" and "relative" — use them to PLAN your motion.
+x = right, +y = up. relative.dx/dy is enemy minus you. If relative.facing_enemy
is false you are looking the wrong way — your strikes will miss.

Footwork (movement is separate from joints): {footwork}
  lunge = explosive forward burst | hop_back = jump backward.

Distance guide: <70 clinch, 70-150 strike range, 150-260 closing, >260 far.

Reply with ONLY a JSON object, no markdown:
{{"thought": "<max 30 words>", "joints": {{"neck": "...", "shoulder": "...", "elbow": "...", "grip": "...", "off_shoulder": "...", "off_elbow": "...", "hip_f": "...", "knee_f": "...", "hip_b": "...", "knee_b": "..."}}, "footwork": "...", "fire": false}}"""


def build_joint_system_prompt(sharp_zones, weapon="sword"):
    """Build the joint-mode system prompt for a specific weapon."""
    block_tmpl = _WEAPON_BLOCKS.get(weapon, _WEAPON_BLOCKS["sword"])
    return JOINT_SYSTEM_PROMPT.format(
        joints=", ".join(JOINTS),
        weapon_block=block_tmpl.format(sharp=", ".join(sharp_zones).upper()),
        footwork=", ".join(FOOTWORK))


def sanitize_joint_reply(d):
    """Validate an LLM joint-mode reply into {thought, joints, footwork, fire}."""
    joints_in = d.get("joints", {}) if isinstance(d.get("joints"), dict) else {}
    joints = {}
    for j in JOINTS:
        s = str(joints_in.get(j, "hold")).lower()
        joints[j] = s if s in JOINT_STATES else "hold"
    fw = d.get("footwork", "hold")
    if fw not in FOOTWORK:
        fw = "hold"
    # `fire` is a coarse bool — accept truthy strings ("true"/"yes"/"1") too.
    raw_fire = d.get("fire", False)
    if isinstance(raw_fire, str):
        fire = raw_fire.strip().lower() in ("true", "yes", "1", "on", "fire")
    else:
        fire = bool(raw_fire)
    return {"thought": str(d.get("thought", ""))[:160],
            "joints": joints, "footwork": fw, "fire": fire}


# ------------------------------------------------------------------ mock
import random


class MockJointBrain:
    """Scripted joint-mode fighter so the mode works without API keys.
    Alternates wind-up / strike, walking in. Deliberately crude — raw joint
    mode is SUPPOSED to look chaotic.

    Now weapon-aware: with a bow it draws the off-hand and fires every turn
    at strike range; with a flail it whirls before swinging.
    """

    label = "Mock-jointer"

    def __init__(self, sharp_zones, label=None, weapon="sword"):
        self.sharp = sharp_zones
        if label:
            self.label = label
        self.weapon = weapon
        self.phase = 0

    def decide(self, state):
        d = state["distance"]
        if self.weapon == "bow":
            return self._decide_bow(state, d)

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

    def _decide_bow(self, state, d):
        # Draw the string (off arm) + steady the bow arm + fire if in range.
        draw = {"neck": "hold", "shoulder": "flex", "elbow": "hold",
                "grip": "hold", "off_shoulder": "flex", "off_elbow": "flex",
                "hip_f": "hold", "knee_f": "hold", "hip_b": "hold", "knee_b": "hold"}
        retreat = dict(draw)
        if d < 90:
            # Too close — bash with the stave instead of shooting.
            bash = {"neck": "hold", "shoulder": "flex", "elbow": "extend",
                    "grip": "extend", "off_shoulder": "hold", "off_elbow": "hold",
                    "hip_f": "hold", "knee_f": "hold", "hip_b": "flex", "knee_b": "hold"}
            return sanitize_joint_reply({
                "thought": "Too close to shoot — bash with the bow.",
                "joints": bash, "footwork": "hop_back", "fire": False,
            })
        return sanitize_joint_reply({
            "thought": "Draw the string and loose an arrow.",
            "joints": draw,
            "footwork": "retreat" if d < 200 else "hold",
            "fire": True,
        })

    def decide_with_timeout(self, state):
        return self.decide(state)
