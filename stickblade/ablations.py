"""State-representation ablations (action-plan §11).

The state we hand a model is a hypothesis: "these fields are what a fighter
needs". Ablations are how that hypothesis gets tested — knock one field out,
run the same matchups, and measure what changed.

What this module is, and what it is not:

* It **defines** the ablations and guarantees each one produces a valid,
  self-consistent state (no dangling references, no leaked field), so the
  thing being tested is the field and not a broken payload.
* It **measures the prompt cost** of every field, which needs no API key
  and is a real, publishable number: what each field costs per match, and
  therefore how much a field has to be worth to justify itself.
* It does **not** measure model performance. That needs provider traffic
  (keys + spend), and `tools/run_ablation.py` is the harness that will run
  it when those exist. Anything claiming "field X improves win rate" from
  this file alone would be fabricated.

The ablations mirror the plan's list, plus the coordinate-representation
pair, because "normalized vs raw coordinates" is a real question about
whether models do arithmetic on absolute pixel values.
"""
from __future__ import annotations

import copy
import json

# Reference: the arena is 1280 x 720 with the floor at y = 64. Normalizing
# against the real bounds is what makes the normalized variant meaningful
# (a model seeing 0.42 instead of 540 can still reason about "a bit right
# of centre").
ARENA_W = 1280
ARENA_H = 720


def _drop(d, *paths):
    """Remove nested keys by dotted path, tolerating absent keys."""
    for p in paths:
        cur = d
        parts = p.split(".")
        for key in parts[:-1]:
            cur = cur.get(key) if isinstance(cur, dict) else None
            if not isinstance(cur, dict):
                break
        else:
            if isinstance(cur, dict):
                cur.pop(parts[-1], None)
    return d


def _norm_xy(v):
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return v
    return [round(float(v[0]) / ARENA_W, 4), round(float(v[1]) / ARENA_H, 4)]


# --------------------------------------------------------------- ablations
def baseline(state):
    """The shipped representation — every ablation is compared against
    this, never against another ablation, so all deltas share one
    reference point.

    Returns a copy rather than the input object so every ablation has
    identical semantics; a caller that runs a sweep in place must not find
    its state mutated by whichever ablation happened to run first.
    """
    return copy.deepcopy(state)


def no_velocity(state):
    """Drop every velocity vector (mine and the enemy's)."""
    s = copy.deepcopy(state)
    _drop(s, "me.velocity", "enemy.velocity")
    return s


def no_opponent_last_action(state):
    """Drop `enemy_last_action` (and mine, so the model cannot infer the
    opponent's from its own in a mirror-symmetric way)."""
    s = copy.deepcopy(state)
    _drop(s, "enemy_last_action", "my_last_action")
    return s


def no_weapon_geometry(state):
    """Drop weapon-tip / off-hand positions and the tip-distance scalar."""
    s = copy.deepcopy(state)
    _drop(s, "me.weapon_tip", "me.off_hand",
          "enemy_sword_tip_distance_to_me")
    return s


def no_arena_modifier(state):
    """Drop the arena label and the gravity-scaled ranged hints, so the
    model cannot special-case ice / low gravity."""
    s = copy.deepcopy(state)
    _drop(s, "arena", "ranged_hint.per_shot", "ranged_hint.gravity_scale")
    return s


def no_history(state):
    """Drop the previous turn's hit events."""
    s = copy.deepcopy(state)
    _drop(s, "last_turn_hits")
    return s


def no_head_positions(state):
    """Drop head coordinates (keep torsos) — head shots are a real
    damage zone, so this tests whether models actually aim."""
    s = copy.deepcopy(state)
    _drop(s, "me.head", "enemy.head",
          "relative.head_dx", "relative.head_dy",
          "relative.head_to_head_distance", "ranged_hint.aim_at_enemy_head")
    return s


def blindfolded(state):
    """The shipped blindfolded variant: strip derived categorical hints,
    keep raw coordinates. Included because it is the one ablation we
    already ship as a first-class eval axis."""
    s = copy.deepcopy(state)
    _drop(s, "distance", "my_height", "enemy_height",
          "relative.enemy_is", "relative.enemy_height_relative",
          "relative.facing_enemy")
    return s


def normalized_coords(state):
    """All coordinates rescaled to [0, 1]. Same information, different
    units — tests whether models read absolute pixel magnitudes or only
    relative structure."""
    s = copy.deepcopy(state)
    for side in ("me", "enemy"):
        grp = s.get(side)
        if isinstance(grp, dict):
            for key in ("torso", "head", "weapon_tip", "off_hand"):
                if key in grp:
                    grp[key] = _norm_xy(grp[key])
    rh = s.get("ranged_hint")
    if isinstance(rh, dict) and "aim_at_enemy_head" in rh:
        rh["aim_at_enemy_head"] = _norm_xy(rh["aim_at_enemy_head"])
    return s


def raw_coords(state):
    """Explicit raw-coordinate control (identical to baseline today).

    Kept as a named ablation so the comparison survives a future change
    that makes normalized the default — otherwise 'raw' would silently
    stop being tested.
    """
    return copy.deepcopy(state)


ABLATIONS = [
    ("baseline",              baseline,              "shipped representation"),
    ("no_velocity",           no_velocity,           "drop all velocity vectors"),
    ("no_opponent_last_action", no_opponent_last_action,
     "drop both fighters' last actions"),
    ("no_weapon_geometry",    no_weapon_geometry,    "drop weapon tip / off-hand"),
    ("no_arena_modifier",     no_arena_modifier,     "drop arena + gravity hints"),
    ("no_history",            no_history,            "drop last-turn hit events"),
    ("no_head_positions",     no_head_positions,     "drop head coordinates"),
    ("blindfolded",           blindfolded,           "strip derived spatial hints"),
    ("normalized_coords",     normalized_coords,     "coords rescaled to [0,1]"),
    ("raw_coords",            raw_coords,            "absolute pixel coords (control)"),
]

BY_NAME = {n: fn for n, fn, _ in ABLATIONS}


def apply(name, state):
    """Apply one ablation by name. Unknown names raise — a typo must not
    silently run the baseline and publish it as an ablation result."""
    if name not in BY_NAME:
        raise KeyError(f"unknown ablation: {name!r} (have {sorted(BY_NAME)})")
    return BY_NAME[name](state)


def names():
    return [n for n, _, _ in ABLATIONS]


# ------------------------------------------------------------ measurement
def _tok(text):
    """Token-count estimate, no external dependency.

    GPT-style BPE averages ~4 characters per token for English text and
    ~3 for JSON-heavy numeric payloads. We use 3.4 and say so: this is a
    cost metric, not a billing figure. Providers report the real number
    (see `costs.py`), which is why this estimate is only ever used to
    compare representations against each other.
    """
    return len(text) / 3.4


def field_cost(state, ablation_names=None):
    """Prompt-token cost of each ablation's state, vs the baseline.

    Returns rows with the ablated state's token estimate and the delta
    against baseline. A negative delta means the field costs tokens; if a
    field costs a lot and buys no measurable performance, that is the
    finding §11 is looking for.
    """
    base = json.dumps(baseline(state), separators=(",", ":"))
    base_tok = _tok(base)
    rows = []
    for name in (ablation_names or names()):
        txt = json.dumps(apply(name, state), separators=(",", ":"))
        tok = _tok(txt)
        rows.append({
            "ablation": name,
            "state_tokens": round(tok, 1),
            "delta_vs_baseline": round(tok - base_tok, 1),
            "pct_of_baseline": round(100 * tok / base_tok, 1) if base_tok else None,
        })
    return {"baseline_tokens": round(base_tok, 1), "rows": rows}


def validate(state, ablation_names=None):
    """Structural check: does each ablated state still hold together?

    A state that lost a field a model needed, or kept a field that
    references a dropped one, would measure the bug rather than the
    ablation. Returns a list of problems (empty = clean).
    """
    problems = []
    for name in (ablation_names or names()):
        try:
            s = apply(name, state)
        except Exception as e:                                # pragma: no cover
            problems.append(f"{name}: raised {type(e).__name__}: {e}")
            continue
        if not isinstance(s, dict):
            problems.append(f"{name}: returned {type(s).__name__}, not a dict")
            continue
        # Every ablation must keep the fields a fighter cannot do without:
        # its own HP, the turn clock, and some way to locate the enemy.
        for required in ("turn", "my_hp", "enemy_hp"):
            if required not in s:
                problems.append(f"{name}: lost required field '{required}'")
        if not (s.get("relative") or s.get("me")):
            problems.append(f"{name}: no positional information left at all")
        # The ablations must not mutate the caller's state (they run
        # side-by-side against the same match state in a sweep).
        if s is state:
            problems.append(f"{name}: returned the input object (must copy)")
    return problems
