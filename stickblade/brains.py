"""LLM brains (GPT / Gemini) + scripted mock fighters.

Each brain receives a JSON game state and must return:
  {"thought": "...", "action": <ACTIONS>, "footwork": <FOOTWORK>}
"""
import json
import math
import random
import re
import threading
import time as _time
from collections import deque
import config as C
from moves import ACTIONS, FOOTWORK, ACTION_ZONE


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


# Ring buffer of recent brain failures. Exposed via /api/debug/brain_errors
# so we can diagnose 'why is every match falling back?' without HF logs auth.
# Each entry: {"t": unix_ts, "label": brain.label, "model": model_id or "",
#              "attempt": idx+1, "of": total_attempts, "err": err_str[:200]}
_RECENT_ERRORS = deque(maxlen=80)


_KEY_LEAK_RE = re.compile(r"(?i)(bearer|api[_-]?key|token)[=:\s]+\S+|sk-[a-zA-Z0-9_-]{16,}")


def _log_brain_err(label, model, attempt, total, err):
    """Append a brain failure to the public /api/debug/brain_errors buffer.
    BYOK safety: strip any accidentally-leaked bearer tokens / sk-* keys
    before storing, since the buffer is served over an unauthenticated
    read-only endpoint."""
    safe = _KEY_LEAK_RE.sub("<hidden>", str(err))[:200]
    _RECENT_ERRORS.append({
        "t": int(_time.time()),
        "label": label, "model": model or "",
        "attempt": attempt, "of": total,
        "err": safe,
    })

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


# ============================================================================
# STRUCTURED-OUTPUT SCHEMA (Tier-A #1: strict json_schema enforcement)
#
# For providers that support `response_format={"type":"json_schema",...}` we
# constrain generation at the API level so the model can't emit malformed
# JSON or off-vocabulary actions/footwork values. Cuts the fallback rate
# for the ~15-20%% of turns where a small model would otherwise return
# {"action": "flexing"} or a trailing-comma JSON blob.
#
# `_decide_json_schema(allowed_actions)` returns the schema for a given
# weapon's action vocabulary. Kept as a function (not a module-level dict)
# because ACTIONS varies per weapon — the sword vocab is different from the
# bow vocab, so each brain's schema must match its own weapon's allowed set.
#
# Which providers accept this shape:
#   * OpenAI direct (chat.completions.create with response_format=schema): YES
#   * Gemini (config.response_schema): YES via a slightly different translation
#   * OpenRouter: partial — support varies per underlying model, so we DO NOT
#     enable it there yet (would silently 400 half the roster). Follow-up:
#     probe support per-model at startup and toggle. Tier B roadmap item.
#   * Groq: same partial-support story as OR. Deferred.
# The `_sanitize()` post-filter still runs even for schema-enforced replies
# — belt-and-braces defense against schema drift or provider bugs.
# ============================================================================
def _decide_json_schema(allowed_actions):
    """Return the OpenAI-flavored strict json_schema for a decide() reply.
    `allowed_actions` is the weapon-specific action vocabulary (see
    weapons.WEAPON_ACTIONS). FOOTWORK is weapon-agnostic."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "duel_move",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["thought", "action", "footwork"],
                "properties": {
                    "thought":  {"type": "string", "maxLength": 240},
                    "action":   {"type": "string", "enum": list(allowed_actions)},
                    "footwork": {"type": "string", "enum": list(FOOTWORK)},
                },
            },
        },
    }


def _gemini_response_schema(allowed_actions):
    """Gemini's structured-output surface uses `response_schema` (a proto-
    ish shape), not OpenAI's json_schema wrapper. Same semantic constraint,
    different wire format. See google-genai types.Schema docs."""
    from google.genai import types
    return types.Schema(
        type="OBJECT",
        required=["thought", "action", "footwork"],
        properties={
            "thought":  types.Schema(type="STRING"),
            "action":   types.Schema(type="STRING", enum=list(allowed_actions)),
            "footwork": types.Schema(type="STRING", enum=list(FOOTWORK)),
        },
    )


def _extract_json(text):
    # Defensive against None/empty (some providers return empty body on a
    # silent rate-limit; we want a clean ValueError that decide_with_timeout's
    # retry loop catches, not a TypeError from re.sub(None)).
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    text = re.sub(r"```(json)?", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json in response")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        # Most JSON parse failures are trailing commas / unescaped quotes
        # from small models. Try one cleanup pass before giving up so the
        # retry loop only sees genuinely-broken responses.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", m.group(0))   # trailing commas
        return json.loads(cleaned)


def _sanitize(d, allowed=None):
    """Coerce a model/bot reply into the engine's action vocabulary.

    Invalid-action tracking (benchmark spec v1.0 §rules.invalid_action_handling):
    when the caller's action/footwork is outside the weapon's vocabulary we
    coerce it (as before) AND flag the reply with `_invalid_action` /
    `_invalid_footwork`. Those flags are the raw material for the
    invalid-action rate the action plan asks us to publish per model
    (§1: "Invalid-action rate"). Flags are only added when they fire, so
    well-behaved replies stay byte-identical to before.
    """
    allowed = allowed or ACTIONS
    raw_a = d.get("action", "ready")
    raw_f = d.get("footwork", "hold")
    a = raw_a if raw_a in allowed else "ready"
    f = raw_f if raw_f in FOOTWORK else "hold"
    t = str(d.get("thought", ""))[:160]
    out = {"action": a, "footwork": f, "thought": t}
    if a != raw_a:
        out["_invalid_action"] = str(raw_a)[:40]
    if f != raw_f:
        out["_invalid_footwork"] = str(raw_f)[:40]
    return out


def _model_id_of(brain) -> str:
    """Canonical model id for telemetry ('groq:' prefix re-added for Groq)."""
    mid = getattr(brain, "model", "") or ""
    if mid and isinstance(brain, GroqBrain) and not mid.startswith("groq:"):
        mid = "groq:" + mid
    if not mid:
        # MockBrain / baseline bots carry no `.model`. Report the roster id
        # ("mock:berserker", "bot:pro") so provenance lines up with the
        # model ids users actually picked, not internal class labels.
        pers = getattr(brain, "p", None)
        if pers:
            return f"mock:{pers}"
        lbl = getattr(brain, "label", "") or ""
        return {"RandomBot": "bot:random", "GreedyBot": "bot:greedy",
                "DistanceBot": "bot:distance",
                "ScriptedPro": "bot:pro"}.get(lbl, lbl or type(brain).__name__)
    return mid


def _provider_of(brain) -> str:
    """Which infrastructure actually served a decision (for fallback stats)."""
    cls = type(brain).__name__
    if "Mock" in cls or cls.endswith("Bot") or "Bot" in cls:
        return "scripted"
    if isinstance(brain, GroqBrain):
        return "groq"
    if cls == "GPTBrain":
        return "openai"
    if cls == "GeminiBrain":
        return "google"
    return _PROVIDER_HOST.get(getattr(brain, "model", ""), "openrouter")


def _phase_of(state):
    """side_phase() for whoever `me` is in this state (left archer = 0)."""
    me = (state.get("me") or {}).get("torso") or (0, 0)
    en = (state.get("enemy") or {}).get("torso") or (0, 0)
    return side_phase(me[0], en[0])


def _distance_of(state):
    """Torso separation in px, blindfolded-safe.

    Blindfolded matches strip the derived `distance` field (the model is
    supposed to compute it from raw coordinates), but the SCRIPTED brains —
    MockBrain's fallback and the baseline bots — still need a number, and
    reading state["distance"] directly raised KeyError on every blindfolded
    turn. Falling back to the raw torso coords keeps those brains working
    without weakening the blindfolded prompt for real models.
    """
    d = state.get("distance")
    if isinstance(d, (int, float)):
        return float(d)
    me = (state.get("me") or {}).get("torso") or (0, 0)
    en = (state.get("enemy") or {}).get("torso") or (0, 0)
    return math.hypot(en[0] - me[0], en[1] - me[1])


def _mobility_of(state):
    """(hold_streak, space_behind, approaching) from state.ranged_hint.

    Tolerant of hand-built states (older tests, frozen eval packs) that
    predate prompt v2: missing fields degrade to "no floor constraint,
    nobody pressing, haven't been standing still".
    """
    rh = state.get("ranged_hint") or {}
    sb = rh.get("space_behind_px")
    return (int(rh.get("consecutive_hold_turns") or 0),
            None if sb is None else float(sb),
            bool(rh.get("enemy_approaching")))


def _trim(text, max_words=25):
    """Clamp model output to <= max_words and strip stray punctuation."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip('"\'`')
    words = text.split(" ")
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return text[:280]


# ============================================================
# Resilience: buddy-model pools + adaptive timeouts
# ============================================================
# When the LLM originally chosen for a turn fails, decide_with_timeout()
# tries 1-2 BUDDY models from the same capability tier before giving up
# and using a scripted mock. Goal: keep the match feeling real even when
# the OpenRouter free pool has a hiccup or one provider is down.
#
# Buddies are SAME-TIER alternates. We don't downgrade a 405B model to a
# 3B model — that would tank match quality silently. Pools below are
# grouped by rough capability + speed so the swap is invisible to the user.
#
# Refresh against `https://openrouter.ai/api/v1/models` if the free pool
# rotates (see tools/verify_models.py).

_BUDDY_POOLS = {
    # Large / slow / strong. Ordered by preference. Every entry is a
    # live model as of the 2026-07-28 roster sync (see config.py for
    # the removal ledger — dead :free slugs are gone from both).
    # Groq entries are cross-provider (independent infrastructure from
    # OpenRouter) so they're the best failover when OR throttles.
    "large": [
        # Cross-provider first: Groq's gpt-oss-120b, different upstream
        # from OR's OpenInference hosting — hits when OR itself is down.
        "groq:openai/gpt-oss-120b",
        "groq:moonshotai/kimi-k2-instruct",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    ],
    # Mid / balanced (fast enough for 15s budget). Groq's llama-3.3-70b
    # runs on Groq's LPU (~10x faster than OR paid) with a 288x larger
    # daily quota — best mid-tier failover we have. OR :free 70B twin
    # was yanked 2026-07-28; Groq's is now the only 70B option.
    "mid": [
        "groq:llama-3.3-70b-versatile",        # cross-provider LPU-hosted 70B
        # groq:qwen/qwen3-32b and groq:meta-llama/llama-4-scout-17b-16e-instruct
        # were removed here after Groq 404'd both. See config.py comment block
        # for the deprecation ledger.
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
        "groq:openai/gpt-oss-20b",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ],
    # Small / fast (good for snap-shot scenarios where speed matters).
    # Groq's llama-3.1-8b-instant is the fastest LLM on the internet
    # right now — sub-second responses even under load.
    "small": [
        "groq:llama-3.1-8b-instant",           # fastest option, cross-provider
        "nvidia/nemotron-nano-9b-v2:free",
        "cohere/north-mini-code:free",
    ],
}

# Map each model to its tier so buddies come from the right pool.
_MODEL_TIER = {}
for tier, ids in _BUDDY_POOLS.items():
    for mid in ids:
        _MODEL_TIER[mid] = tier
# Paid models map to "mid" as a reasonable buddy tier (we don't burn paid
# budget on retries of free-tier failures; if a paid model fails we fall
# back to free mid-tier).
_MODEL_TIER.update({
    "openai/gpt-4o-mini":         "mid",
})


# ----------------------------------------------------------------------
# Per-model reasoning policy
# ----------------------------------------------------------------------
# Hand-curated from OpenRouter's GET /api/v1/models catalog (the 'reasoning'
# block on each model entry). Three categories:
#
#   None       → omit the `reasoning` param entirely. Either the model has
#                no reasoning capability at all, OR it's mandatory-reasoning
#                and rejects any attempt to disable (sending `enabled:false`
#                makes gpt-oss-* 400 the request).
#   {disable}  → safe to disable; we send `enabled: false, exclude: true`.
#                Non-reasoning models silently ignore, reasoning models that
#                allow disable actually turn off CoT.
#
# This map is verified against the live catalog on 2026-06-30. Any model id
# not listed defaults to "try to disable, fall back gracefully if rejected"
# — see _reasoning_policy().
#
# Rationale: previous attempts used substring matching on the model id
# ("gpt-oss", "nemotron", "thinking", etc.) which silently missed gemma-4,
# poolside-laguna, cohere-north and a bunch of others, AND mis-handled
# gpt-oss (mandatory-reasoning — disabling it errors). Catalog-driven is
# the only correct approach.
_REASONING_DISABLE = {"enabled": False, "exclude": True}

# Models where sending the reasoning param at all is wrong:
#   - mandatory-reasoning (will 400 if we ask to disable)
#   - vanilla non-reasoning (no-op, just cleaner to omit)
_REASONING_OMIT = {
    # vanilla non-reasoning (no reasoning block in catalog)
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "qwen/qwen3-coder:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "openai/gpt-4o-mini",
}

# Mandatory-reasoning models. These reject `enabled: false` (400) and will
# ALWAYS do hidden CoT no matter what we send. Best we can do is use the
# lowest supported effort and exclude reasoning from response. Listed
# separately so callers can also know to grant more max_tokens headroom.
_REASONING_MANDATORY = {
    "openai/gpt-oss-120b:free":  {"effort": "low", "exclude": True},
    "openai/gpt-oss-20b:free":   {"effort": "low", "exclude": True},
}


def _reasoning_policy(model_id: str):
    """Return the `reasoning` request block for a given model, or None
    if the param should be omitted entirely. Catalog-driven; see comment
    above for the curation rules.
    """
    if not model_id:
        return None
    if model_id in _REASONING_OMIT:
        return None
    if model_id in _REASONING_MANDATORY:
        return dict(_REASONING_MANDATORY[model_id])
    # Default: try to disable. Covers the catalog-listed reasoning models
    # that DO allow disable (gemma-4-*, nemotron-3-*, laguna-*, cohere-north,
    # nemotron-nano-*) plus any future model not yet in our curated set.
    return dict(_REASONING_DISABLE)


def _max_tokens_for(model_id: str, joint_mode: bool) -> int:
    """Adaptive output token cap. Mandatory-reasoning models need ~3x the
    headroom because they always do CoT; we can only ask for `effort: low`
    which still uses ~20%% of the cap on thinking."""
    base = 1200 if joint_mode else 800
    if model_id in _REASONING_MANDATORY:
        return base * 3  # 2400 macro / 3600 joint
    return base


def _buddies_for(brain, k=2):
    """Return up to k buddy model ids from the same tier as `brain.model`,
    excluding the original AND any model currently in 429 cooldown.
    Prefers buddies from a DIFFERENT provider host than the original, since
    the most common failure mode is 'upstream provider throttled' (free
    Llama-family models mostly go to Venice; if Venice is 429ing on one
    Llama, the other Llamas will be too — no point retrying them).
    Returns [] for non-OpenRouter brains.
    """
    model_id = getattr(brain, "model", None)
    if not model_id or "/" not in model_id:
        return []
    if not C.OPENROUTER_API_KEY:
        return []                           # no key, can't construct buddies
    tier = _MODEL_TIER.get(model_id, "mid") # unknown ids default to mid tier
    pool = [m for m in _BUDDY_POOLS.get(tier, []) if m != model_id]
    # Remove cooling-down models (429'd recently, upstream still throttled)
    now = _time.time()
    pool = [m for m in pool if _COOLDOWN.get(m, 0) < now]
    # Reorder: put buddies with a DIFFERENT provider host first. When the
    # original 429s it's almost always because that specific provider is
    # throttling globally, so a same-provider buddy will 429 too. Falling
    # back to a different provider is the only way to recover.
    origin_prov = _PROVIDER_HOST.get(model_id, "")
    if origin_prov:
        pool.sort(key=lambda m: _PROVIDER_HOST.get(m, "") == origin_prov)
    return pool[:k]


# ----------------------------------------------------------------------
# Per-model 429 circuit breaker
# ----------------------------------------------------------------------
# OpenRouter reports the upstream provider's Retry-After. If a model 429s,
# we blacklist it for `Retry-After` seconds (default 15s if header missing)
# so subsequent turns in the same match don't waste API calls / stall the
# retry ladder waiting for the throttle to clear on its own.
_COOLDOWN = {}  # {model_id: unix_ts_ready_at}
_COOLDOWN_LOCK = threading.Lock()


def _mark_cooldown(model_id, seconds):
    if not model_id:
        return
    with _COOLDOWN_LOCK:
        _COOLDOWN[model_id] = _time.time() + max(1.0, min(float(seconds), 60.0))


# ----------------------------------------------------------------------
# Provider host map (hand-curated from OpenRouter catalog, 2026-07-02).
# When a model 429s, we prefer buddies from a DIFFERENT provider — since
# the throttle almost always originates at the upstream host, not at OR.
# ----------------------------------------------------------------------
_PROVIDER_HOST = {
    # Venice hosts most Llama-family and Nous free models
    "meta-llama/llama-3.3-70b-instruct:free":       "venice",
    "meta-llama/llama-3.2-3b-instruct:free":        "venice",
    "nousresearch/hermes-3-llama-3.1-405b:free":    "venice",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "venice",
    # Google AI Studio hosts Gemma
    "google/gemma-4-31b-it:free":                   "google",
    "google/gemma-4-26b-a4b-it:free":               "google",
    # OpenInference hosts gpt-oss + some nvidia + qwen-coder
    "openai/gpt-oss-120b:free":                     "openinference",
    "openai/gpt-oss-20b:free":                      "openinference",
    "qwen/qwen3-coder:free":                        "openinference",
    "qwen/qwen3-next-80b-a3b-instruct:free":        "alibaba",
    # Nvidia self-hosts nemotron
    "nvidia/nemotron-3-super-120b-a12b:free":       "nvidia",
    "nvidia/nemotron-3-ultra-550b-a55b:free":       "nvidia",
    "nvidia/nemotron-3-nano-30b-a3b:free":          "nvidia",
    "nvidia/nemotron-nano-9b-v2:free":              "nvidia",
    # Others
    "poolside/laguna-m.1:free":                     "poolside",
    "poolside/laguna-xs.2:free":                    "poolside",
    "cohere/north-mini-code:free":                  "cohere",
    "liquid/lfm-2.5-1.2b-instruct:free":            "liquid",
    # Paid (OR routes to Azure/Anthropic/etc; unlikely to be free-tier-throttled)
    "openai/gpt-4o-mini":                           "azure",
    # Groq — independent provider entirely (LPU-based, not GPU). Given
    # a single provider tag so the buddy-diversity sort correctly treats
    # a same-provider Groq buddy as 'closer' than an OR buddy when the
    # original was Groq. In practice cross-OR-to-Groq is the failover
    # we actually care about.
    "groq:llama-3.3-70b-versatile":                 "groq",
    "groq:llama-3.1-8b-instant":                    "groq",
    # Removed 2026-07-XX: Groq deprecated llama-4-scout + qwen3-32b (both
    # 404 from Groq API). See config.py for the ledger.
    "groq:openai/gpt-oss-120b":                     "groq",
    "groq:openai/gpt-oss-20b":                      "groq",
    "groq:deepseek-r1-distill-llama-70b":           "groq",
    "groq:moonshotai/kimi-k2-instruct":             "groq",
}


def _timeout_for(model_id):
    """Adaptive per-model timeout. Tiny models that take >10s are stuck
    (their inference is fast), while reasoning models genuinely need 25-30s
    on a complex prompt. Flat 30s was killing reasoning chains too early
    AND waiting too long on tiny stuck models."""
    if not model_id:
        return C.LLM_TIMEOUT
    mid = model_id.lower()
    # Small fast models
    if any(t in mid for t in ("3b", "1.2b", "9b", "nano", "lfm", "small")):
        return 10.0
    # Large reasoning models
    if any(t in mid for t in ("120b", "405b", "550b", "deepseek-r1", "thinking", "reasoning")):
        return min(C.LLM_TIMEOUT, 25.0)
    # Default mid-tier
    return min(C.LLM_TIMEOUT, 18.0)


class Brain:
    label = "BASE"
    # True for brains that decide WITHOUT any network call (mocks + the
    # scripted bot baselines). main.py uses this to resolve both fighters
    # synchronously instead of in threads: the think phase steps physics
    # once per frame while it waits, so a thread-scheduling delay would
    # silently change how many physics steps happen before the turn starts
    # and break seeded reproducibility (action-plan §8).
    scripted = False

    def __init__(self, sharp_zones, mode="macro", weapon="sword", rng=None):
        # Per-instance RNG. Decisions for the two fighters are computed in
        # PARALLEL THREADS (main.py), so any scripted brain that draws from
        # the GLOBAL random module makes a seeded match non-reproducible:
        # which fighter consumes which draw depends on thread scheduling.
        # Every scripted brain must therefore draw from self.rng.
        self.rng = rng if rng is not None else random
        from weapons import (WEAPON_ACTIONS, WEAPON_ACTION_ZONE, WEAPON_HINTS)
        self.sharp = sharp_zones
        self.mode = mode
        self.weapon = weapon
        self.actions = WEAPON_ACTIONS.get(weapon, ACTIONS)
        if mode == "joint":
            from joint_mode import build_joint_system_prompt
            self.sys = build_joint_system_prompt(sharp_zones, weapon)
        else:
            zmap = " | ".join(f"{a}->{z}" for a, z in
                              WEAPON_ACTION_ZONE.get(weapon, {}).items())
            self.sys = SYSTEM_PROMPT.format(
                weapon=weapon,
                sharp=", ".join(sharp_zones).upper(),
                zone_hint=WEAPON_HINTS.get(weapon, ""),
                zone_map=zmap,
                actions=", ".join(self.actions), footwork=", ".join(FOOTWORK),
                max_holds=MAX_CONSECUTIVE_HOLDS,
                range_hint=RANGE_HINTS.get(weapon, ""))
        self.history = []
        # Token accounting (action-plan §33): every provider that bills us
        # also reports what it billed, so cost per match can be MEASURED
        # instead of estimated from prompt length. Accumulated across every
        # call this brain makes, including retries and buddy fallbacks —
        # a match that fell back still cost the tokens it burned.
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0,
                      "calls": 0}

    def _record_usage(self, prompt_tokens, completion_tokens):
        """Add one API call's reported token counts.

        Only counts non-negative ints: a provider that omits usage must
        contribute nothing rather than a bogus zero-weighted average.
        """
        try:
            pt = int(prompt_tokens or 0)
            ct = int(completion_tokens or 0)
        except (TypeError, ValueError):
            return
        if pt < 0 or ct < 0:
            return
        self.usage["prompt_tokens"] += pt
        self.usage["completion_tokens"] += ct
        self.usage["calls"] += 1

    def usage_snapshot(self):
        return dict(self.usage)

    def _clean(self, raw):
        """Mode-aware sanitization of a parsed LLM reply."""
        if self.mode == "joint":
            from joint_mode import sanitize_joint_reply
            return sanitize_joint_reply(raw)
        return _sanitize(raw, self.actions)

    def decide(self, state):
        """Blocking; called from worker thread. Returns sanitized dict."""
        raise NotImplementedError

    # ---------- free-form chat (trash talk / commentary) -----------------
    def chat(self, system, user, max_tokens=80, temperature=0.95):
        """Stateless one-shot completion. Override in concrete brains.
        Default: a small library of canned trash talk so the mocks aren't
        dead silent. Returns a plain string."""
        return ""

    def chat_with_timeout(self, system, user, max_tokens=80,
                          temperature=0.95, fallback=""):
        out = {}
        def run():
            try:
                out["r"] = self.chat(system, user, max_tokens=max_tokens,
                                     temperature=temperature)
            except Exception as e:
                out["err"] = str(e)[:80]
        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(min(C.LLM_TIMEOUT, 15))   # quips shouldn't block long
        return _trim(out.get("r") or fallback)

    def decide_with_timeout(self, state):
        """Resilient decide() with retry, buddy-model fallback, and adaptive
        timeout — only resorts to the scripted mock as a true last resort.

        Failure ladder (each step takes <2s extra wall clock):
          1. Original model, 1st attempt, adaptive timeout for its size
          2. Original model, 2nd attempt with +50% timeout (handles transient
             rate-limits, empty responses, JSON parse errors, network blips)
          3. Buddy model #1 (similar capability tier, different provider)
          4. Buddy model #2 (further-removed alternate)
          5. Scripted mock (last resort, banner shown to user)
        """
        import time as _t

        # Step 1+2: retry the originally-chosen model first — UNLESS it's
        # in the 429 cooldown map from a recent throttle. If so, skip
        # straight to buddies (no point burning a 15s wait for a model
        # we know is currently blocked upstream).
        own_model = getattr(self, "model", "")
        in_cooldown = _COOLDOWN.get(own_model, 0) > _t.time()
        attempts = []
        if not in_cooldown:
            attempts = [
                (self, _timeout_for(own_model)),
                (self, _timeout_for(own_model) * 1.5),
            ]

        # Steps 3+4: try up to 2 buddy models if the original keeps failing.
        # Buddies only apply to OpenRouter brains (same client, same key, just
        # a different model id). GPT/Gemini brains use different clients and
        # don't have an equivalent — they get the same model retried twice.
        # _buddies_for() already filters out cooling-down buddies and orders
        # by provider diversity (different upstream host first).
        # Reuse the same OpenRouter key the original used (server env OR
        # a per-match BYOK key). Without this, BYOK matches would fall
        # back to the server's key on the first 429, defeating the point
        # of BYOK. Non-OR brains have no ._client so this is a no-op.
        origin_key = None
        client = getattr(self, "_client", None)
        if client is not None:
            auth = client.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                origin_key = auth[7:]
        for buddy_id in _buddies_for(self, k=3 if in_cooldown else 2):
            try:
                # Route by prefix: 'groq:*' → GroqBrain (Groq API endpoint),
                # anything else → OpenRouterBrain. This is the cross-provider
                # failover in action — a throttled OR buddy pool selection
                # can drop us onto Groq entirely, using an independent key
                # against independent infrastructure.
                if buddy_id.startswith("groq:"):
                    # BYOK is OR-only for now — don't leak an OR user key
                    # into a Groq call. Groq falls back to its env var.
                    buddy = GroqBrain(
                        self.sharp, buddy_id,
                        label=self.label + "→buddy",
                        mode=self.mode, weapon=self.weapon)
                else:
                    buddy = OpenRouterBrain(
                        self.sharp, buddy_id,
                        label=self.label + "→buddy",
                        mode=self.mode, weapon=self.weapon,
                        api_key=origin_key if getattr(self, "_byok", False) else None)
                attempts.append((buddy, _timeout_for(buddy_id)))
            except Exception:
                # Provider not configured / brain init failed — skip silently.
                # If GROQ_API_KEY isn't set, groq: buddies just get skipped
                # and we fall back to OR-only buddies + mock as before.
                pass

        # If EVERYTHING is cooling down (rare — every buddy 429'd recently)
        # give the original ONE shot with big timeout; it might be back.
        if not attempts:
            attempts = [(self, _timeout_for(own_model) * 1.5)]

        last_err = "no attempts"
        for idx, (brain, timeout_s) in enumerate(attempts):
            # Re-check cooldown right before firing — a previous buddy's
            # 429 may have just marked THIS buddy's model as cool too
            # (e.g. shared per-org RPM on Groq). Was: queued buddies
            # would fire even when we already knew they'd 429.
            candidate_model = getattr(brain, "model", "")
            candidate_key = ("groq:" + candidate_model
                             if isinstance(brain, GroqBrain)
                             else candidate_model)
            if idx > 0 and candidate_key and \
                    _COOLDOWN.get(candidate_key, 0) > _t.time():
                remaining = round(_COOLDOWN[candidate_key] - _t.time(), 1)
                print(f"[brain] {self.label} skip attempt {idx+1}/{len(attempts)}"
                      f" — {candidate_key} cooling {remaining}s")
                continue
            out = {}
            def _run():
                try:
                    out["r"] = brain.decide(state)
                except Exception as e:
                    out["err"] = str(e)[:200]
            th = threading.Thread(target=_run, daemon=True)
            th.start()
            th.join(timeout_s)

            if "r" in out and out["r"]:
                if idx > 0:
                    print(f"[brain] {self.label} recovered on attempt {idx+1} "
                          f"using {getattr(brain,'model',brain.label)}")
                mv = out["r"]
                # Provenance stamps (benchmark spec v1.0): which model and
                # which provider actually produced this decision, and after
                # how many ladder rungs. Consumed by Match._record_turn()
                # and surfaced in the replay + dataset export.
                try:
                    mv["_model_used"] = _model_id_of(brain)
                    mv["_provider_used"] = _provider_of(brain)
                    mv["_attempt"] = idx + 1
                    # §33: the tokens this decision actually billed, from the
                    # provider's own usage block. Covers retries and buddy
                    # fallbacks, because those cost money too.
                    snap = brain.usage_snapshot()
                    mv["_usage"] = snap
                except Exception:
                    pass
                return mv

            last_err = out.get("err") or f"timeout({timeout_s:.0f}s)"
            print(f"[brain] {self.label} attempt {idx+1}/{len(attempts)} "
                  f"failed: {last_err[:120]}")
            _log_brain_err(self.label,
                           getattr(brain, "model", ""),
                           idx + 1, len(attempts), last_err)

            # FAST-FAIL on reasoning_burnout: the model just spent its entire
            # token budget on hidden CoT. Retrying with +50% budget might
            # work but usually doesn't — and a buddy from a different family
            # almost always does. Skip the redundant 2nd attempt on the same
            # model and jump to the first buddy (idx 2) immediately.
            if idx == 0 and "reasoning_burnout" in last_err and len(attempts) > 2:
                # Drop attempt #2 (same-model retry); buddies stay queued.
                attempts.pop(1)

            # FAST-FAIL on "unavailable for free" (OpenRouter yanked the
            # :free suffix off this model). Same rationale as
            # reasoning_burnout above: retrying with more time won't
            # restore the free slug; only path forward is a buddy from
            # a different family. Saves ~20s per turn when a user picks
            # a slug that OR has rotated off free since our roster last
            # synced. Roster curation (config.py) also catches this at
            # the source, but this fast-fail belt-and-braces the case
            # where OR yanks a slug between roster syncs.
            if idx == 0 and "unavailable for free" in last_err and len(attempts) > 2:
                attempts.pop(1)

            # Tiny backoff between attempts so we don't immediately re-hit a
            # rate-limit window. Capped at 2s so total recovery stays under
            # ~10s extra wall clock in the worst case.
            if idx < len(attempts) - 1:
                _t.sleep(min(0.5 * (idx + 1), 2.0))

        # ---------------- All attempts exhausted → scripted fallback --------
        # Pick a personality based on the brain's label so when BOTH fighters
        # fall back in the same match they don't produce identical sequences.
        personality = "berserker" if (hash(self.label) & 1) else "duelist"
        if self.mode == "joint":
            from joint_mode import MockJointBrain
            fb = MockJointBrain(self.sharp, weapon=self.weapon).decide(state)
        else:
            # CRITICAL: pass weapon=self.weapon so the mock fallback picks
            # weapon-appropriate actions. Without this it defaults to 'sword'
            # and a bow fighter ends up swinging the bow like a sword instead
            # of shooting arrows (and a flail fighter ignores spin_up etc.).
            fb = MockBrain(self.sharp, personality,
                           weapon=self.weapon).decide(state)

        print(f"[brain] {self.label} ALL {len(attempts)} attempts failed, "
              f"using mock {personality}: {last_err[:80]}")
        fb["thought"] = "[fallback] " + fb["thought"]
        fb["_fallback"] = True
        fb["_model_used"] = f"scripted:{personality}"
        fb["_provider_used"] = "scripted"
        fb["_attempt"] = len(attempts)
        # The failed provider calls are still billable. Attribute the
        # primary brain's accumulated usage rather than hiding it: a match
        # that fell back is exactly the case a budget needs to see.
        try:
            fb["_usage"] = self.usage_snapshot()
        except Exception:
            pass
        return fb


# ---------------------------------------------------------------- mock AI
PERSONALITIES = {
    "duelist":  "patient counter-fighter",
    "berserker": "relentless aggression",
}


_MOCK_QUIPS = {
    "berserker": [
        "I don't fence. I delete.",
        "Hope your save file is recent.",
        "Stand still. It'll hurt less.",
        "Three swings. None of them yours.",
    ],
    "duelist": [
        "Patience always wins. I've already won.",
        "I read your intent two turns ago.",
        "Come closer. I dare you.",
        "Your zone is bad and you should feel bad.",
    ],
}


class MockBrain(Brain):
    scripted = True

    def __init__(self, sharp_zones, personality="duelist", label=None,
                 weapon="sword", rng=None):
        super().__init__(sharp_zones, "macro", weapon, rng=rng)
        self.p = personality
        self.label = label or f"Mock-{personality}"

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        # Mocks don't actually call any model — pick a personality-appropriate
        # canned line. Works for both pre-fight quips and the commentary
        # roast (commentator role plays a generic "duelist" pool).
        pool = _MOCK_QUIPS.get(self.p, _MOCK_QUIPS["duelist"])
        # Flavour text must not advance the decision RNG — see the note in
        # pre_fight_quip. Pick from a snapshot of the stream instead.
        peek = random.Random()
        try:
            peek.setstate(self.rng.getstate())
        except (AttributeError, TypeError, ValueError):
            peek.seed()
        return peek.choice(pool)

    def _sharp_attacks(self):
        atk = [a for a in self.actions
               if ACTION_ZONE.get(a) and ACTION_ZONE[a] in self.sharp]
        fallback = {"sword": ["thrust"], "flail": ["wide_swing"],
                    "bow": ["draw_shot"]}
        return atk or fallback.get(self.weapon, ["thrust"])

    def _bow_move(self, state, d):
        """Bow policy: shoot every turn, and move while doing it.

        The regression this replaces chose `footwork: "hold"` on every
        long-range turn. A shot action never moves the fighter — movement
        comes only from `footwork` (moves.MoveController.update) — so two
        archers parked 420px apart and traded arrows for 24 turns without
        either of them taking a step. footwork now comes from the shared
        bow_footwork() policy, which alternates advance/retreat, kites when
        the enemy closes, refuses to backpedal into a wall, and caps
        consecutive holds at MAX_CONSECUTIVE_HOLDS.
        """
        hold_streak, space_behind, approaching = _mobility_of(state)
        if d <= 50:
            # in actual physical contact — only NOW use the bow as a club
            action, thought = "bow_bash", "He's on top of me — bash and jump away."
        elif d <= 120:
            action, thought = "quick_shot", "Point-blank shot, then create distance."
        elif d <= 260:
            action, thought = "quick_shot", "He's closing — snap shot and give ground."
        else:
            # self.rng, not the module `random`: the two fighters decide in
            # concurrent threads, so a global RNG makes a seeded match
            # replay differently run to run. See Brain.__init__.
            action = self.rng.choice(["draw_shot", "high_arc_shot"])
            thought = "Full draw, then change distance — never a statue."
        return {"action": action,
                "footwork": bow_footwork(d, approaching=approaching,
                                         hold_streak=hold_streak,
                                         space_behind=space_behind,
                                         turn=state.get("turn", 0),
                                         phase=_phase_of(state)),
                "thought": thought}

    def decide(self, state):
        # _distance_of / .get("my_height") instead of state["distance"] and
        # state["my_height"]: blindfolded matches strip both derived fields,
        # and this brain is (a) selectable as mock:duelist / mock:berserker
        # and (b) the last-resort fallback for any model that times out — so
        # a blindfolded match used to KeyError the moment it fell back.
        d = _distance_of(state)
        hits_on_me = [h for h in state["last_turn_hits"] if h["by"] != self.label]
        atk = self._sharp_attacks()
        if state.get("my_height", "standing") == "knocked_down":
            return _sanitize({"action": "guard_high", "footwork": "hop_back",
                              "thought": "I'm down — cover up and create space."})
        if self.weapon == "bow":
            # Always prefer SHOOTING over melee with a bow. The previous logic
            # had bow_bash as a 50% pick at clinch range which looked weird —
            # archers don't beat people with their bow when an arrow at 0 ft
            # still works. Only bash if literally on top of the enemy.
            return _sanitize(self._bow_move(state, d), self.actions)
        if self.p == "berserker":
            if d > 200:
                mv = {"action": self.rng.choice(atk), "footwork": "lunge",
                      "thought": "Close the gap hard, swing on arrival."}
            elif d > 90:
                mv = {"action": self.rng.choice(atk), "footwork": "advance",
                      "thought": "In range next step — commit to the kill zone."}
            else:
                mv = {"action": self.rng.choice(atk + atk + ["pommel_strike"]),
                      "footwork": "advance", "thought": "Point blank. Overwhelm."}
        else:
            if hits_on_me and state["my_hp"] < 50:
                mv = {"action": "guard_high", "footwork": "hop_back",
                      "thought": "Taking damage — reset distance, defend high line."}
            elif d > 240:
                # Bow is handled by the early-return above; only melee reaches
                # this branch, so no need to special-case it here.
                mv = {"action": "ready", "footwork": "advance",
                      "thought": "Walk in behind guard, no wasted swings."}
            elif d > 130:
                mv = {"action": self.rng.choice(atk), "footwork": "lunge",
                      "thought": "Perfect entry distance — explosive sharp attack."}
            elif d < 70:
                mv = {"action": self.rng.choice(atk), "footwork": "hop_back",
                      "thought": "Too close, cut on the way out."}
            else:
                mv = {"action": self.rng.choice(atk), "footwork": self.rng.choice(["hold", "advance"]),
                      "thought": "Strike range. Aim the sharp zone at his head."}
        # Pass self.actions so weapon-specific moves (wide_swing / spin_up
        # for flail, thrust_over for spear, etc.) survive sanitization. The
        # default ACTIONS list is sword-only; without this a flail mock's
        # 'wide_swing' silently downgraded to 'ready' and the fighter just
        # stood there whenever the API fell back to the mock brain.
        return _sanitize(mv, self.actions)


# ---------------------------------------------------------------- real LLMs
class GPTBrain(Brain):
    label = "GPT"

    def __init__(self, sharp_zones, model=C.OPENAI_MODEL, mode="macro", weapon="sword"):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        from openai import OpenAI
        self.client = OpenAI(api_key=C.OPENAI_API_KEY)

    def decide(self, state):
        msgs = [{"role": "system", "content": self.sys}]
        msgs += self.history[-6:]
        user = json.dumps(state)
        msgs.append({"role": "user", "content": user})
        # Tier-A #1: strict json_schema enforcement. OpenAI direct supports
        # this reliably (unlike OpenRouter where per-model support varies).
        # `self.actions` is the weapon-specific action vocabulary set by
        # Brain.__init__ via WEAPON_ACTIONS. If the schema call ever fails
        # (SDK version quirk / model deprecation), fall back to plain JSON
        # mode so the match still resolves through a real API call rather
        # than the mock brain.
        try:
            r = self.client.chat.completions.create(
                model=self.model, messages=msgs, temperature=0.8, max_tokens=150,
                response_format=_decide_json_schema(self.actions))
        except Exception:
            r = self.client.chat.completions.create(
                model=self.model, messages=msgs, temperature=0.8, max_tokens=150,
                response_format={"type": "json_object"})
        txt = r.choices[0].message.content
        try:
            u = getattr(r, "usage", None)
            self._record_usage(getattr(u, "prompt_tokens", None),
                               getattr(u, "completion_tokens", None))
        except Exception:
            pass
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            temperature=temperature, max_tokens=max_tokens)
        try:
            u = getattr(r, "usage", None)
            self._record_usage(getattr(u, "prompt_tokens", None),
                               getattr(u, "completion_tokens", None))
        except Exception:
            pass
        return r.choices[0].message.content or ""


class GeminiBrain(Brain):
    label = "GEMINI"

    def __init__(self, sharp_zones, model=C.GEMINI_MODEL, mode="macro", weapon="sword"):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        from google import genai
        self.client = genai.Client(api_key=C.GEMINI_API_KEY)
        self.convo = []

    def decide(self, state):
        from google.genai import types
        self.convo.append({"role": "user", "parts": [{"text": json.dumps(state)}]})
        # Tier-A #1: strict response_schema on the config so Gemini
        # constrains generation to the exact enum/shape we want. If
        # anything breaks (SDK types moved, model doesn't support it),
        # fall back to plain application/json mode so the match still
        # resolves through a real API call. Skips schema entirely in
        # joint mode because the reply shape there is different (raw
        # joint commands, not the action/footwork enum).
        try:
            cfg = types.GenerateContentConfig(
                system_instruction=self.sys, temperature=0.8,
                max_output_tokens=450 if self.mode == 'joint' else 200,
                response_mime_type="application/json",
                response_schema=(None if self.mode == 'joint'
                                 else _gemini_response_schema(self.actions)))
        except Exception:
            cfg = types.GenerateContentConfig(
                system_instruction=self.sys, temperature=0.8,
                max_output_tokens=450 if self.mode == 'joint' else 200,
                response_mime_type="application/json")
        r = self.client.models.generate_content(
            model=self.model, contents=self.convo[-7:], config=cfg)
        # Gemini reports usage as usageMetadata{promptTokenCount,
        # candidatesTokenCount} rather than OpenAI's `usage` block.
        try:
            um = getattr(r, "usage_metadata", None) or {}
            self._record_usage(um.get("prompt_token_count")
                               or um.get("promptTokenCount"),
                               um.get("candidates_token_count")
                               or um.get("candidatesTokenCount"))
        except Exception:
            pass
        txt = r.text
        self.convo.append({"role": "model", "parts": [{"text": txt}]})
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        from google.genai import types
        r = self.client.models.generate_content(
            model=self.model,
            contents=[{"role": "user", "parts": [{"text": user}]}],
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens))
        return r.text or ""


class OpenRouterBrain(Brain):
    """Any model on OpenRouter via the OpenAI-compatible chat endpoint.

    model: e.g. 'meta-llama/llama-3.3-70b-instruct:free' or 'openai/gpt-4o-mini'
    """

    def __init__(self, sharp_zones, model, label=None, mode="macro", weapon="sword",
                 api_key=None):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        self.label = label or model.split("/")[-1].replace(":free", "")[:24]
        # BYOK: if the caller passed a per-match api_key (from the user's
        # localStorage via /api/match), use it instead of the server-side
        # OPENROUTER_API_KEY. The user's traffic then draws from THEIR quota,
        # not ours — bypasses the 50-req/day free-tier ceiling.
        # api_key is intentionally NOT stored on self; only baked into
        # this httpx.Client's default headers so it never appears in logs,
        # replay JSON, error messages, or the recorder output.
        self._byok = bool(api_key)
        key = api_key or C.OPENROUTER_API_KEY
        import httpx
        self._client = httpx.Client(
            base_url=C.OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://stickblade.arena",
                "X-Title": "Stickblade Arena",
            },
            timeout=C.LLM_TIMEOUT,
        )

    def decide(self, state):
        user = json.dumps(state)
        msgs = [{"role": "system", "content": self.sys}]
        msgs += self.history[-6:]
        msgs.append({"role": "user", "content": user})
        payload = {
            "model": self.model, "messages": msgs,
            "temperature": 0.8,
            "max_tokens": _max_tokens_for(self.model, self.mode == "joint"),
        }
        # Per-model reasoning policy (see _reasoning_policy / catalog notes
        # above). Only attach the `reasoning` block when the policy returns
        # one — sending `enabled: false` to a mandatory-reasoning model
        # (gpt-oss-*) makes it 400 the request; sending it to a
        # no-reasoning model is a silent no-op but cleaner to just omit.
        rp = _reasoning_policy(self.model)
        if rp:
            payload["reasoning"] = rp
        r = self._client.post("/chat/completions", json=payload)
        # Surface OpenRouter's actual error text instead of httpx's generic
        # 'Client error N for url ...'. OR returns {"error": {"message":...}}
        # on 4xx/5xx; we want that message bubbling into [brain] log lines
        # so we know *why* a retry/buddy is firing.
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                # OR nests upstream Retry-After under error.metadata
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            # 429 = throttled. Mark this model in cooldown so subsequent
            # turns in this or any other match don't waste API calls on
            # a model we KNOW is throttled. Retry-After is usually 5-30s.
            if r.status_code == 429:
                _mark_cooldown(self.model,
                               retry_after or 15)  # default 15s if header absent
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        data = r.json()
        # OpenAI-compatible usage block: {"prompt_tokens", "completion_tokens"}.
        # Recorded before anything else can fail, so a billing-relevant call
        # is never lost to an exception downstream.
        try:
            self._record_usage((data.get("usage") or {}).get("prompt_tokens"),
                               (data.get("usage") or {}).get("completion_tokens"))
        except Exception:
            pass
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        txt = msg.get("content")
        finish = choice.get("finish_reason", "")
        # Reasoning-burnout signature: content is null/empty AND finish_reason
        # is 'length' (model hit the cap mid-think). Raise a distinct error
        # so decide_with_timeout's retry ladder skips to a buddy fast instead
        # of pointlessly re-querying the same model.
        if (not txt) and finish == "length":
            raise ValueError(f"reasoning_burnout: {self.model} spent entire "
                             f"budget on hidden CoT (finish=length, content=null)")
        if not txt:
            raise ValueError(f"empty response (finish={finish or 'unknown'})")
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        # Same per-model reasoning policy as decide(). Floor max_tokens at
        # 400 so any model that still does CoT (mandatory-reasoning) has
        # room for it + the short trash-talk line.
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": user}],
            "temperature": temperature,
            "max_tokens": max(max_tokens, 400),
        }
        rp = _reasoning_policy(self.model)
        if rp:
            payload["reasoning"] = rp
        r = self._client.post("/chat/completions", json=payload)
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            if r.status_code == 429:
                _mark_cooldown(self.model, retry_after or 15)
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        j = r.json()
        try:
            self._record_usage((j.get("usage") or {}).get("prompt_tokens"),
                               (j.get("usage") or {}).get("completion_tokens"))
        except Exception:
            pass
        return j["choices"][0]["message"]["content"] or ""


# ============================================================
# Trash talk + post-fight commentary
# ============================================================
QUIP_SYS = (
    "You are a stickman sword/flail/bow fighter about to enter a physics-based "
    "duel against another AI model. Reply with ONE line of in-character "
    "trash talk, maximum 18 words. No emojis. No quotation marks. No 'As an AI'. "
    "Be cocky, witty, specific to the matchup."
)


def pre_fight_quip(brain, opponent_label, weapon="sword"):
    """Ask the brain for a single trash-talk line. Falls back to a canned
    quip if the model is slow or errors out."""
    user = (f"You are fighting a model called '{opponent_label}'. "
            f"Your weapon: {weapon}. Give your one line of pre-fight trash "
            "talk. Just the line, nothing else.")
    # Draw from a COPY of the brain's own rng state, so a seeded match stays
    # reproducible even though the two fighters decide in parallel threads —
    # and so the quip does not advance the decision stream. It used to draw
    # from brain.rng directly, which meant the same seed produced a
    # different fight through the server (which asks for quips) than
    # through tools/simcore.py (which does not): the seeded-replay claim
    # held offline and silently failed in production.
    src = getattr(brain, "rng", random)
    peek = random.Random()
    try:
        peek.setstate(src.getstate())
    except (AttributeError, TypeError, ValueError):
        peek.seed()
    fallback = peek.choice(_MOCK_QUIPS["berserker"] + _MOCK_QUIPS["duelist"])
    return brain.chat_with_timeout(QUIP_SYS, user, max_tokens=60,
                                   temperature=1.0, fallback=fallback)


COMMENTATOR_SYS = (
    "You are a snarky e-sports commentator for an AI sword-fighting arena. "
    "Given the result of a duel between two LLMs, write a SHORT post-fight "
    "summary (2 sentences, max 45 words total). Sentence 1: what happened. "
    "Sentence 2: a playful roast of the LOSER. Stay in character, do not "
    "mention being an AI. No emojis. No quotation marks."
)


def commentator_roast(commentator_brain, winner_name, loser_name, method,
                      turns, weapon, sharp, final_hp,
                      fallback="A clean kill. Better luck next patch."):
    """Ask a third brain to write 2-sentence post-fight commentary."""
    user = (
        f"Weapon: {weapon}. Sharp zones: {', '.join(sharp)}.\n"
        f"Winner: {winner_name}. Loser: {loser_name}.\n"
        f"Method: {method}. Turns: {turns}.\n"
        f"Final HP — winner: {final_hp.get(winner_name, '?')}, "
        f"loser: {final_hp.get(loser_name, '?')}.\n"
        "Write your 2-sentence summary + roast now."
    )
    return commentator_brain.chat_with_timeout(
        COMMENTATOR_SYS, user, max_tokens=120, temperature=1.0,
        fallback=fallback)


# =========================================================================
# Groq — independent OpenAI-compatible provider.
# =========================================================================
# Only differs from OpenRouter in three ways:
#   1. Base URL (Groq's /openai/v1)
#   2. Auth key (GROQ_API_KEY env var; BYOK not supported for Groq yet —
#      users mostly want to unblock OR's tight quota, not Groq's generous one)
#   3. reasoning param — Groq honors {"reasoning_format": "hidden"} to
#      request no chain-of-thought in the response (their equivalent of
#      OR's reasoning.exclude). Non-reasoning models ignore this.
# Everything else — retry ladder, cooldowns, error surfacing, live ticker,
# BYOK header stripping — inherits unchanged from OpenRouterBrain.
# =========================================================================
class GroqBrain(OpenRouterBrain):
    """Groq API client. Same shape as OpenRouterBrain but points at
    Groq's endpoint and reads the GROQ_API_KEY env var instead. Models
    are stored with a 'groq:' prefix in ARENA_MODELS but sent to Groq
    with the prefix stripped (e.g. 'groq:llama-3.3-70b-versatile' ->
    'llama-3.3-70b-versatile').

    Overrides decide() and chat() because Groq REJECTS OpenRouter's
    `reasoning: {enabled, exclude}` object with a 400. Groq uses:
      * `include_reasoning: false`         (openai/gpt-oss-* models)
      * `reasoning_format: "hidden"`       (qwen, deepseek reasoning models)
      * (nothing)                          (vanilla llama, kimi, etc.)
    """

    def __init__(self, sharp_zones, model, label=None, mode="macro",
                 weapon="sword", api_key=None):
        # Strip the 'groq:' prefix used by our internal router. Groq's API
        # doesn't know about that prefix.
        wire_model = model[5:] if model.startswith("groq:") else model
        # Bypass OpenRouterBrain.__init__ so we can swap base_url + key
        # source cleanly. Still inherit its decide()/chat() methods via
        # class inheritance, which read self._client + self.model.
        Brain.__init__(self, sharp_zones, mode, weapon)
        self.model = wire_model
        self.label = label or wire_model.split("/")[-1][:24]
        self._byok = False   # BYOK not plumbed through Groq path
        key = api_key or C.GROQ_API_KEY
        import httpx
        self._client = httpx.Client(
            base_url=C.GROQ_BASE,
            headers={
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "https://stickblade.arena",
                "X-Title": "Stickblade Arena",
            },
            timeout=C.LLM_TIMEOUT,
        )

    def _groq_reasoning_params(self):
        """Return a dict of Groq-specific reasoning-disable params for
        this model (may be empty). Keeps the switch in one place.
        Vanilla llama/kimi/etc. → {} (nothing to disable).
        gpt-oss-*                → include_reasoning=False
        qwen3, deepseek-r1       → reasoning_format='hidden'
        """
        m = self.model.lower()
        if "gpt-oss" in m:
            # Groq's gpt-oss uses include_reasoning boolean, NOT reasoning_format.
            # Also accepts reasoning_effort='low' — combined they give us the
            # equivalent of OR's exclude+low_effort.
            return {"include_reasoning": False, "reasoning_effort": "low"}
        if any(t in m for t in ("qwen3", "qwen-3", "deepseek-r1")):
            # Both families accept reasoning_format=hidden.
            # qwen3 also accepts reasoning_effort=none for a stronger disable.
            out = {"reasoning_format": "hidden"}
            if "qwen" in m:
                out["reasoning_effort"] = "none"
            return out
        return {}

    def decide(self, state):
        user = json.dumps(state)
        msgs = [{"role": "system", "content": self.sys}]
        msgs += self.history[-6:]
        msgs.append({"role": "user", "content": user})
        payload = {
            "model": self.model, "messages": msgs,
            "temperature": 0.8,
            # Groq's gpt-oss can still burn tokens even with disable; give
            # them the same 3x headroom OR gets via _max_tokens_for.
            "max_tokens": _max_tokens_for(
                "openai/gpt-oss-120b:free" if "gpt-oss" in self.model.lower()
                else "", self.mode == "joint"),
        }
        payload.update(self._groq_reasoning_params())
        r = self._client.post("/chat/completions", json=payload)
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            if r.status_code == 429:
                # Cool down under the 'groq:'-prefixed key so _COOLDOWN
                # matches what _buddies_for filters against.
                _mark_cooldown("groq:" + self.model, retry_after or 15)
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        txt = msg.get("content")
        finish = choice.get("finish_reason", "")
        if (not txt) and finish == "length":
            raise ValueError(f"reasoning_burnout: {self.model} spent entire "
                             f"budget on hidden CoT (finish=length, content=null)")
        if not txt:
            raise ValueError(f"empty response (finish={finish or 'unknown'})")
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": user}],
            "temperature": temperature,
            "max_tokens": max(max_tokens, 400),
        }
        payload.update(self._groq_reasoning_params())
        r = self._client.post("/chat/completions", json=payload)
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            if r.status_code == 429:
                _mark_cooldown("groq:" + self.model, retry_after or 15)
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        return r.json()["choices"][0]["message"]["content"] or ""


def make_brain(kind, sharp_zones, mode="macro", weapon="sword", api_key=None,
               seed=None):
    """Build the right Brain subclass for a given kind.

    api_key: optional per-match BYOK OpenRouter key. If passed, OpenRouter
    calls draw from the caller's quota instead of the server's env var.
    Threaded via server.py -> Match -> make_brain -> OpenRouterBrain and
    is never stored anywhere persistent.

    seed: when set, scripted baselines (bot:*) get a per-fighter seeded RNG
    so a seeded match replays identically. LLM brains are unaffected —
    their outputs are not reproducible from a seed.
    """
    kind = kind.lower()
    # Scripted brains get their own Random seeded from the match seed so a
    # seeded match replays identically even though the two fighters decide
    # concurrently (see Brain.__init__). Without a seed we deliberately fall
    # back to the global RNG — unseeded matches are meant to vary.
    import random as _random
    rng = _random.Random(seed) if seed is not None else None

    def _mock(personality="duelist", label=None):
        if mode == "joint":
            from joint_mode import MockJointBrain
            jb = MockJointBrain(sharp_zones, label=label, weapon=weapon,
                                rng=rng)
            # Same provenance id as the macro mock ("mock:duelist"), so a
            # joint match lines up with the roster id the user picked
            # instead of reporting the internal "Mock-jointer" label.
            jb.p = personality
            return jb
        return MockBrain(sharp_zones, personality, label=label, weapon=weapon,
                         rng=rng)

    def _substitute(brain, reason):
        """Tag a mock that is STANDING IN for a model the user actually picked.

        Silent substitution is the one integrity failure the benchmark can't
        survive: the user chose gpt-oss-120b, got heuristics, and the match
        still reports `fully_llm_controlled: true`. Tagging the brain lets
        Match stamp every one of its turns `_fallback`, so the live wait
        screen, the reveal card's integrity row, and the leaderboard's
        fallback_rate all disclose it. Declared baselines (`bot:*`,
        `mock:*`) are NOT tagged — /api/models already labels them `no_api`.
        """
        brain.mock_substitute = True
        brain.substitute_reason = reason
        return brain

    # explicit mock personality: "mock:duelist" / "mock:berserker"
    if kind.startswith("mock:"):
        p = kind.split(":", 1)[1]
        return _mock(p if p in PERSONALITIES else "duelist")
    # Tier-A #2: non-LLM baseline bots. "bot:random" / "bot:greedy" /
    # "bot:distance" / "bot:pro". Zero network I/O, pure heuristics.
    # Powers the fixed y-axis reference for the leaderboard
    # ("GPT-OSS 120B beats scripted-pro 78%% of matches"). Kept in
    # its own module (bots.py) because they're a separate concern from
    # LLM adapters + schema handling + reasoning routing.
    if kind.startswith("bot:"):
        from bots import make_bot
        return make_bot(kind.split(":", 1)[1], sharp_zones,
                        mode=mode, weapon=weapon, seed=seed)
    # Groq model id: "groq:<groq-model-name>" — independent provider,
    # much larger free-tier ceiling. Routed through GroqBrain (subclass
    # of OpenRouterBrain) which just swaps base URL + auth key. If
    # GROQ_API_KEY isn't set, fall through to mock rather than pretending
    # to succeed — same shape as the OpenRouter branch below.
    if kind.startswith("groq:"):
        reason = "no GROQ_API_KEY configured"
        if C.GROQ_API_KEY:
            try:
                return GroqBrain(sharp_zones, kind, mode=mode, weapon=weapon)
            except Exception as e:
                reason = f"Groq init failed: {e}"
                print(f"[brains] Groq init failed ({e}); using mock.")
        else:
            print(f"[brains] No GROQ_API_KEY — '{kind}' slot uses mock.")
        label = kind.split(":", 1)[1].split("/")[-1][:20] + "(mock)"
        return _substitute(_mock("duelist", label=label), reason)
    # OpenRouter model id (contains "/"), e.g. meta-llama/llama-3.3-70b:free
    if "/" in kind:
        # BYOK wins over env var: if the caller passed api_key, use it
        # even when the server has no OPENROUTER_API_KEY of its own
        # (letting a locally-hosted instance run purely on user keys).
        effective_key = api_key or C.OPENROUTER_API_KEY
        reason = "no OpenRouter key (server env or BYOK)"
        if effective_key:
            try:
                return OpenRouterBrain(sharp_zones, kind, mode=mode,
                                       weapon=weapon, api_key=api_key)
            except Exception as e:
                reason = f"OpenRouter init failed: {e}"
                print(f"[brains] OpenRouter init failed ({e}); using mock.")
        else:
            print(f"[brains] No OpenRouter key (server env or BYOK) — "
                  f"'{kind}' slot uses mock.")
        label = kind.split("/")[-1].replace(":free", "")[:20] + "(mock)"
        return _substitute(_mock("duelist", label=label), reason)
    if kind == "gpt":
        reason = "no OPENAI_API_KEY configured"
        if C.OPENAI_API_KEY:
            try:
                return GPTBrain(sharp_zones, mode=mode, weapon=weapon)
            except Exception as e:
                reason = f"GPT init failed: {e}"
                print(f"[brains] GPT init failed ({e}); using mock.")
        else:
            reason = "no OPENAI_API_KEY configured"
            print("[brains] No OPENAI_API_KEY — GPT slot uses mock.")
        return _substitute(_mock("duelist", label="GPT(mock)"), reason)
    if kind == "gemini":
        reason = "no GEMINI_API_KEY configured"
        if C.GEMINI_API_KEY:
            try:
                return GeminiBrain(sharp_zones, mode=mode, weapon=weapon)
            except Exception as e:
                reason = f"Gemini init failed: {e}"
                print(f"[brains] Gemini init failed ({e}); using mock.")
        else:
            reason = "no GEMINI_API_KEY configured"
            print("[brains] No GEMINI_API_KEY — Gemini slot uses mock.")
        return _substitute(_mock("berserker", label="GEMINI(mock)"), reason)
    return _mock(kind if kind in PERSONALITIES else "duelist")
