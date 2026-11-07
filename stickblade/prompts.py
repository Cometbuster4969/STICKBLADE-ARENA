"""The question: system prompt, state serialisation, footwork policy.

Split out of `brains.py` because the two halves of that file change under
different rules:

  * THIS MODULE is the evaluation interface. Any semantic change to
    `build_state()`, the SYSTEM_PROMPT template or the action vocabulary is a
    PROMPT change and must bump `PROMPT_VERSION`, which invalidates
    cross-version Elo on purpose.
  * `brains.py` is the transport layer — provider clients, retries, buddy
    pools, cooldowns, reasoning policies. Those change for operational
    reasons and must not touch ratings.

Keeping them in one 1,940-line file made it easy to "just fix the client"
while silently editing the prompt, which is the exact failure mode
PROMPT_VERSION exists to catch.

`brains` re-exports every public name defined here, so existing imports
(`from brains import build_state, PROMPT_VERSION`) are unchanged.
"""
from __future__ import annotations

import math

import config as C


# ============================================================================
# PROMPT_VERSION — the evaluation prompt schema version.
#
# What "prompt" means here: the full set of {system prompt template + state
# JSON schema + response format} that every model sees before deciding a move.
# Any semantic change to `build_state()`, SYSTEM_PROMPT template, ACTIONS
# vocabulary, or the required response shape must bump this number.
#
# WHY IT MATTERS: Elo ratings are only meaningful if all models were rated
# under the SAME question. Silently changing the prompt = silently
# invalidating every historical rating on the leaderboard. This constant
# is exposed via /api/version and the /api/leaderboard rows so external
# dataset consumers, correlation studies, and paper citations can pin
# their analysis to a specific prompt schema.
#
# Version 1 baseline (2026-07-18): sword/dagger/spear/flail/bow weapons,
# 3 arenas (normal/ice/low_gravity), macro/joint control modes, spatial
# state with rounded ints + facing_enemy boolean + arena-aware bow drop
# hints. See AGENTS.md §PROMPT_VERSION_LOG for the full change ledger.
#
# Version 2 (2026-09-08): additive ranged-mobility hints. ranged_hint gains
# enemy_approaching / closing_speed_px_s / distance_band / space_ahead_px /
# space_behind_px / recommended_footwork / consecutive_hold_turns, and the
# bow range_hint was rewritten from "keep distance >260 and shoot" (which
# produced matches where both archers stood still for 24 straight turns) to
# an explicit repositioning rule. No v1 field was removed or redefined, so
# this is a SOFT cutover — old ratings stay readable, they just aren't
# directly comparable to v2 bow cells. See AGENTS.md §10.5.
# ============================================================================
PROMPT_VERSION = 2

SYSTEM_PROMPT = """You are a stickman fighter in a physics-based duel (like Toribash).
Your weapon: a {weapon}. Each turn you pick ONE action and ONE footwork; physics then runs for 3 seconds.

WEAPON RULES (critical): only these weapon zones are DANGEROUS and deal real damage: {sharp}.
All other zones are blunt (tiny chip damage at best).
Zone geometry: {zone_hint}
Zone each action leads with: {zone_map}
A fast DANGEROUS-zone hit to the head is an INSTANT KILL. Blunt hits mostly just push.

Actions: {actions}
Footwork: {footwork}
  lunge = explosive forward burst | hop_back = jump backward (escape pressure)

SPATIAL AWARENESS: each turn you receive world coordinates of both fighters'
torso and head (`me`, `enemy`) plus relative geometry under `relative`
(dx, dy, head_dx, head_dy, enemy_is left/right/in_front, enemy_height_relative
higher/lower/level, facing_enemy true/false). +x is right, +y is up.
If `relative.facing_enemy` is false you are looking the WRONG WAY — your
strike will whiff; use the next turn to reorient (your engine will auto-flip
if you simply walk past them).
For ranged shots, `ranged_hint.aim_at_enemy_head` is the world point to aim
at. `ranged_hint.per_shot[action].vertical_drop_to_compensate` tells you
how many pixels the arrow will drop for each specific shot type — pick
the shot, then aim `drop` pixels HIGHER than the target head. All drop
values are arena-aware (low_gravity gives ~35% of normal drop).

MOVEMENT: `footwork` is the ONLY thing that moves you — no attack action
repositions your feet on its own, so a turn spent attacking with `hold`
footwork is a turn spent standing still. `ranged_hint.recommended_footwork`
is the backend's read of the current geometry (is the enemy closing, how
much floor is behind you, which band you are in) — treat it as a strong
default, not a command. `ranged_hint.consecutive_hold_turns` counts how
many turns in a row you have chosen `hold`; never let it exceed {max_holds}.
A motionless fighter is a free target and gives away the arena.

Distance guide: <70 = clinch range, 70-150 = strike range, 150-260 = closing range, >260 = far.
{range_hint}
ARENA MODIFIER (state.arena): `normal` = standard stone floor; `ice` = ~3x
less foot friction AND much lower air drag — lunges overshoot, recoveries
keep sliding, and a missed swing can carry you past the enemy (prefer
`advance`/`hold` over `lunge`, and `hop_back` slides further than usual);
`low_gravity` = gravity is ~35% normal — jumps float, arrows drop less so
aim flatter, knockdowns take longer to recover from.
Reply with ONLY a JSON object, no markdown:
{{"thought": "<your tactical reasoning, max 30 words>", "action": "...", "footwork": "..."}}"""

# ---- ranged mobility tuning (used by RANGE_HINTS below + bow_footwork) ----
MAX_CONSECUTIVE_HOLDS = 2      # standing still longer than this is a bug
# Control dead-zone for the bow policy. Deliberately MUCH wider than the
# "ideal" 300-450px shooting range, because one turn of footwork covers
# ~270-330px (measured: advance ≈ +324, retreat ≈ -266, hop_back ≈ -331 —
# see test_bow_mobility.py). A dead-zone narrower than a single stride makes
# bang-bang control overshoot every turn, and the duel degenerates into a
# limit cycle: too close → both back off → too far → both walk in → repeat,
# swinging ~600px per turn across the whole arena.
BOW_TOO_CLOSE = 200            # below this an archer is being overrun
BOW_TOO_FAR = 620              # above this arrow drop is not worth trusting
BOW_MID = 430                  # where a shuffling archer tries to keep the gap
WALL_MARGIN = 70               # px of floor needed behind you to backpedal

RANGE_HINTS = {
    "sword": "",
    "flail": "Your flail outranges a clinch — mid range (90-170) is your kill zone; spin_up first for spike-speed.\n",
    # Rewritten for prompt v2. The v1 text ("keep distance >260 and shoot;
    # if the enemy closes, hop_back or bow_bash") made `hold` the obviously
    # correct answer at every long-range turn, and because a shot action
    # never moves the feet (moves.MoveController drives movement purely from
    # `footwork`), two bow fighters would stand 420px apart and trade shots
    # without moving for the entire match. See test_bow_mobility.py.
    "bow": ("You are a RANGED fighter — shoot every turn you can, but DO NOT STAND STILL. "
            "Keep distance, and shoot while alternating `advance`, `retreat` and `hop_back`. "
            "At long range (>260): `retreat` if the enemy is closing, `advance` if they are "
            "moving away or you are pinned near a wall. In closing range (70-260): `retreat` "
            "to re-open the gap. Under 70: `hop_back`, and only use `bow_bash` when the enemy "
            "is literally touching you (<50). "
            f"Never choose `hold` for more than {MAX_CONSECUTIVE_HOLDS} consecutive turns — "
            "check `ranged_hint.consecutive_hold_turns` and `ranged_hint.recommended_footwork` "
            "every turn, and back off `space_behind_px` before retreating into the arena wall.\n"),
}


# ============================================================================
# Ranged mobility policy (prompt v2)
#
# Shared by the scripted fallback (MockBrain), the ScriptedPro baseline bot,
# and — as a suggestion — every real model via
# ranged_hint.recommended_footwork in build_state(). One implementation so
# the hint the model reads and the fallback that acts when the model fails
# can never disagree about what "good spacing" means.
#
# Distance bands mirror the prompt's distance guide:
#   clinch  <70   |   strike 70-150   |   closing 150-260   |   far >260
# Constants (MAX_CONSECUTIVE_HOLDS / KITE_BAND / WALL_MARGIN) are defined
# above RANGE_HINTS because the bow hint quotes the hold cap verbatim.
# ============================================================================
def distance_band(d):
    """Name the band a distance falls in (same thresholds as the prompt)."""
    if d < 70:
        return "clinch"
    if d < 150:
        return "strike"
    if d <= 260:
        return "closing"
    return "far"


def side_phase(me_x, enemy_x):
    """0 for the fighter currently on the left, 1 for the one on the right.

    Used to de-synchronise the two archers' shuffle so they don't mirror
    each other. Mirroring is what made the naive fix worse than the bug:
    both retreating on the same turn adds ~270px of separation each, so the
    pair sprinted to opposite walls and then sprinted back. With opposite
    phases one advances while the other backpedals — both move, and the gap
    barely changes (measured: advance ≈ +324px/turn, retreat ≈ -266px/turn),
    which is the walk-forward-while-backpedalling dance a real ranged duel
    looks like.
    """
    return 0 if me_x <= enemy_x else 1


def bow_footwork(d, approaching=False, hold_streak=0, space_behind=None,
                 turn=0, phase=0):
    """Pick bow footwork so the archer shoots *while repositioning*.

    d             separation in px
    approaching   enemy closing on us this turn
    hold_streak   consecutive `hold` turns so far (fighter.foot_streak)
    space_behind  px of floor between us and the wall we would backpedal
                  into (None = unknown / treat as roomy)
    turn          match turn, drives the alternating shuffle
    phase         side_phase() of this fighter, so the two archers shuffle
                  out of step instead of mirroring each other

    `hold` is only ever returned when nothing better is available (we are
    already backed against the wall AND the enemy isn't pressing), and even
    then the MAX_CONSECUTIVE_HOLDS cap forces a move on the next turn.
    """
    room = WALL_MARGIN if space_behind is None else space_behind
    can_back_off = room > WALL_MARGIN
    # Only ONE of the two archers corrects a bad gap at a time (the phase-0
    # one, i.e. whoever is currently on the left). If both corrected, the gap
    # would change by two strides a turn and blow straight past the dead-zone
    # into the opposite error. Gating corrections this way is safe against a
    # MELEE opponent too: a charging swordsman trips `approaching` (rule 2
    # below), which is never gated, so the archer always kites out.
    lead = (phase == 0)
    # Exactly one archer shuffles per turn; the other holds. Both moving in
    # the same direction pins them against opposite walls, and one chasing
    # the other collapses the gap into a clinch (measured: 420 -> 100px in
    # three turns). Alternating the mover keeps the gap breathing inside the
    # band while still putting a visible step on the floor every turn.
    mover = ((turn + phase) % 2 == 0)

    if d < 70:                      # clinch — both get off them
        foot = "hop_back" if can_back_off else "advance"
    elif approaching:               # they're closing — kite, no gating
        foot = "retreat" if can_back_off else "advance"
    elif d < BOW_TOO_CLOSE:         # being overrun — one of us backs off
        foot = ("retreat" if can_back_off else "hold") if lead else "hold"
    elif d > BOW_TOO_FAR:           # out of effective range — one walks in
        foot = "advance" if lead else "hold"
    elif not mover:                 # partner is stepping this turn: plant
        foot = "hold"
    else:
        # Our turn to shuffle: step toward the middle of the band so the gap
        # breathes instead of drifting into a wall or a clinch.
        foot = ("retreat" if can_back_off else "advance") if d < BOW_MID \
            else "advance"

    # Hard cap on standing still. If the policy above said `hold` and we're
    # already at the cap, take whichever direction still has floor.
    if foot == "hold" and hold_streak >= MAX_CONSECUTIVE_HOLDS:
        foot = "retreat" if can_back_off else "advance"
    return foot


def _xy(v):
    """Round a pymunk Vec2d to ints for a compact JSON payload."""
    return [int(round(v.x)), int(round(v.y))]


def _vel(body):
    """Round a body velocity to int px/s."""
    v = body.velocity
    return [int(round(v.x)), int(round(v.y))]


def build_state(me, foe, turn, max_turns, last_events, arena="normal",
                blindfolded=False):
    """Game state handed to the LLM each turn.

    Now includes full spatial awareness: torso + head positions (and velocities)
    for both fighters in world coordinates, weapon-tip / off-hand positions,
    relative geometry (Δx, Δy, who's above whom, who's facing the enemy), plus
    a few derived ranged-combat hints (line-of-sight clearance, vertical lead
    needed for an arrow shot, etc.). All values rounded to ints so the JSON
    payload stays small.

    ---- BLINDFOLDED MODE (Tier S #3) ----
    When `blindfolded=True`, the following pre-computed spatial hints are
    STRIPPED from the state:
        - relative.enemy_is        (categorical: right/left/in_front)
        - relative.enemy_height_relative  (categorical: higher/lower/level)
        - relative.facing_enemy    (boolean)
    The raw absolute positions + velocities + facing scalars remain, so
    the model has to compute these categorical judgments from coords
    itself. This isolates 'can the model do 2D spatial reasoning' from
    'can the model react to pre-parsed booleans'. Blindfolded matches
    occupy their own elo cell — never averaged with normal matches.

    ---- PROMPT VERSIONING ----
    The exact contents of this state (which fields, what units, what
    parseable hints) IS the benchmark's evaluation prompt. Any semantic
    change here (add/remove/rename fields, change unit, change rounding
    granularity) makes historical Elo INCOMPARABLE to future Elo — the
    models are answering a different question, so cross-version ratings
    are apples-to-oranges.

    Blindfolded mode does NOT bump PROMPT_VERSION because it's an
    additive VARIANT (opt-in per match, separate elo cell) not a
    replacement. Normal-mode matches see the same state as v1 baseline.

    When you change the meaning of what `build_state()` returns:
      1. Bump PROMPT_VERSION below (v1 -> v2 -> v3).
      2. Note the change in AGENTS.md §PROMPT_VERSION_LOG.
      3. Decide: reset the elo table (clean cutover) OR accept comparability
         loss on old data (soft cutover — UI still labels ratings vN based
         on when they were earned).
    Cosmetic changes (rewording a docstring, refactoring the code that
    BUILDS this dict without changing the OUTPUT) do NOT require a bump.

    The version is a public field on /api/version so external tooling
    (dataset consumers, replay downloaders, correlation studies) can
    key off the exact prompt schema that produced any given rating.
    """
    me_torso = me.pos()
    foe_torso = foe.pos()
    me_head = me.head_pos()
    foe_head = foe.head_pos()

    d = (foe_torso - me_torso).length
    dx = foe_torso.x - me_torso.x
    dy = foe_torso.y - me_torso.y

    head_dx = foe_head.x - me_head.x
    head_dy = foe_head.y - me_head.y
    head_dist = (foe_head - me_head).length

    # Are we actually pointing the right way? (facing is +1 right, -1 left)
    facing_enemy = (dx > 0 and me.facing > 0) or (dx < 0 and me.facing < 0)

    # Off-hand (the bow-string hand for bows; the second fist otherwise)
    off_hand = me.bodies["off_farm"].local_to_world((0, -12))

    # Weapon tip / business end
    weapon = getattr(me, "weapon", "sword")
    if weapon == "bow":
        # bow "tip" not meaningful — give the off-hand draw point instead
        weapon_tip = off_hand
    else:
        weapon_tip = me.tip_pos()

    # Velocities (helpful so the LLM can predict where to aim)
    me_vel = _vel(me.bodies["torso"])
    foe_vel = _vel(foe.bodies["torso"])

    # ---------- Ranged combat helpers (bow-aiming hints) ----------
    # Arena-aware gravity: low_gravity scales space.gravity to 35%, so
    # the drop model expects at any given flight time is much smaller.
    # Previously this used C.GRAVITY[1] unconditionally, telling low-grav
    # bow fighters to aim for a drop ~2.86x too large — the model
    # overcompensated and hoisted every shot high. (See main.py line 74.)
    g_scale = 0.35 if arena == "low_gravity" else 1.0
    g_eff   = abs(C.GRAVITY[1]) * g_scale
    # Per-shot-type flight time + drop. Was a flat 700 px/s guess before,
    # which was 40%% too slow for a draw_shot (980 px/s) and 8%% too fast
    # for a quick_shot (640 px/s). The drop grows with t^2, so those
    # errors compounded into ~30-90 px of aim bias depending on distance.
    # Emitting per-shot values lets the LLM pick the shot type first,
    # then aim precisely — no need for it to guess our internal average.
    def _drop_for(speed):
        t = d / speed
        return {"flight_time_s": round(t, 2),
                "vertical_drop_to_compensate": round(0.5 * g_eff * t * t)}
    # Kept for backwards compat with any external consumer that reads
    # `arrow_flight_time_s` / `vertical_drop_to_compensate` directly.
    # Uses draw_shot as the reference since it's the highest-damage
    # (and most-used) bow action.
    flight_t = round(d / 980.0, 2)
    gravity_drop = round(0.5 * g_eff * flight_t * flight_t)

    # ---------- Ranged MOBILITY helpers (prompt v2) ----------
    # The v1 state told a model everything about where things ARE and
    # nothing about where it should GO. With `hold` a legal answer at every
    # distance, both the scripted policy and real models converged on
    # standing still and shooting — a 24-turn bow match where nobody moved.
    # These fields are the backend's read of the same geometry the model
    # could compute itself, published so it doesn't have to:
    #   closing_speed_px_s  >0 = the gap is shrinking this instant
    #   space_ahead/behind  floor left before the arena wall (px)
    #   consecutive_hold_turns  how statue-like we've been
    #   recommended_footwork    bow_footwork() verdict for this exact state
    d_safe = d if d > 1e-6 else 1e-6
    ux, uy = dx / d_safe, dy / d_safe
    # Radial closing speed along the me->enemy axis: positive means the
    # separation is shrinking (enemy walking at us faster than we retreat).
    # me_vel/foe_vel are already the rounded [vx, vy] lists from _vel().
    closing = (foe_vel[0] - me_vel[0]) * ux + (foe_vel[1] - me_vel[1]) * uy
    enemy_approaching = closing > 20.0          # ~20 px/s: above idle drift
    # How much floor is on each side of us. `facing` is +1 right / -1 left,
    # so "behind" is the side we would backpedal into.
    space_ahead = (C.WIDTH - me_torso.x) if me.facing > 0 else me_torso.x
    space_behind = me_torso.x if me.facing > 0 else (C.WIDTH - me_torso.x)
    hold_streak = int(getattr(me, "foot_streak", 0))
    recommended = bow_footwork(d, approaching=enemy_approaching,
                               hold_streak=hold_streak,
                               space_behind=space_behind, turn=turn,
                               phase=side_phase(me_torso.x, foe_torso.x))

    rel = []
    for e in last_events:
        rel.append({"by": e["attacker"], "zone": e["zone"], "hit_part": e["part"],
                    "damage": e["damage"], "was_sharp": e["sharp"]})

    return {
        # core combat
        "turn": turn, "turns_left": max_turns - turn,
        "arena": arena,                       # normal | ice | low_gravity
        "my_hp": round(me.hp, 1), "enemy_hp": round(foe.hp, 1),
        # In blindfolded mode we skip `distance` (derivable from torso
        # coords) and the my_height/enemy_height categorical labels
        # (derivable from y vs stand_torso_y). Model must compute these
        # from raw positions.
        **({} if blindfolded else {
            "distance": round(d),
            "my_height": "knocked_down" if me_torso.y < me.stand_torso_y - 30 else "standing",
            "enemy_height": "knocked_down" if foe_torso.y < foe.stand_torso_y - 30 else "standing",
        }),
        "enemy_last_action": foe.last_action,
        "my_last_action": me.last_action,
        "enemy_sword_tip_distance_to_me": round((foe.tip_pos() - me_torso).length),
        "last_turn_hits": rel,

        # ---------- NEW: spatial awareness ----------
        # All positions are absolute world coordinates: +x = right, +y = up.
        "me": {
            "torso": _xy(me_torso),
            "head":  _xy(me_head),
            "weapon_tip": _xy(weapon_tip),
            "off_hand":   _xy(off_hand),
            "facing": me.facing,         # +1 right, -1 left
            "velocity": me_vel,           # px/s
        },
        "enemy": {
            "torso": _xy(foe_torso),
            "head":  _xy(foe_head),
            "facing": foe.facing,
            "velocity": foe_vel,
        },
        # Relative geometry (enemy minus me, signed in world coords).
        # In blindfolded mode we drop the categorical hints ("enemy_is",
        # "enemy_height_relative", "facing_enemy") and keep only raw
        # deltas. The model has to derive left/right/higher/lower/facing
        # from dx/dy itself. See docstring "BLINDFOLDED MODE".
        "relative": {
            "dx": int(round(dx)),
            "dy": int(round(dy)),
            "head_dx": int(round(head_dx)),
            "head_dy": int(round(head_dy)),
            "head_to_head_distance": int(round(head_dist)),
            **({} if blindfolded else {
                "enemy_is": ("right" if dx > 8 else "left" if dx < -8 else "in_front"),
                "enemy_height_relative": (
                    "higher" if dy > 18 else "lower" if dy < -18 else "level"),
                "facing_enemy": bool(facing_enemy),
            }),
        },
        # Ranged combat helpers (mostly useful for bow / flail leads).
        "ranged_hint": {
            # Kept for back-compat; matches draw_shot as the reference.
            "arrow_flight_time_s": flight_t,
            "vertical_drop_to_compensate": gravity_drop,
            # Per-shot-type breakdown so the model can pick a shot AND
            # aim it correctly in the same turn. All arena-aware — the
            # `vertical_drop_to_compensate` values here reflect the
            # actual gravity of state.arena (0.35x under low_gravity).
            "per_shot": {
                "draw_shot":     _drop_for(980.0),
                "quick_shot":    _drop_for(640.0),
                "high_arc_shot": _drop_for(760.0),
            },
            "gravity_scale": g_scale,   # 1.0 normal / ice, 0.35 low_gravity
            # aim point if you want to hit the enemy HEAD with a flat arrow
            "aim_at_enemy_head": _xy(foe_head),
            # ---- prompt v2: mobility (see "Ranged MOBILITY helpers") ----
            # Present in blindfolded mode too: these are movement facts, not
            # the categorical spatial hints (enemy_is / height / facing) that
            # blindfolding strips on purpose.
            "enemy_approaching": bool(enemy_approaching),
            "closing_speed_px_s": int(round(closing)),
            "distance_band": distance_band(d),
            "space_ahead_px": int(round(max(0.0, space_ahead))),
            "space_behind_px": int(round(max(0.0, space_behind))),
            "consecutive_hold_turns": hold_streak,
            "recommended_footwork": recommended,
            "max_consecutive_holds": MAX_CONSECUTIVE_HOLDS,
        },
    }
