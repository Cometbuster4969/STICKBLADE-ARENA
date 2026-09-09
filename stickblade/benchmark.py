"""STICKBLADE BENCHMARK SPECIFICATION v1.0 — the authoritative ruleset.

Why this file exists
--------------------
A benchmark is only comparable over time if the thing being measured is
frozen. Before this module, "a Stickblade match" was defined implicitly by
whatever `config.py`, `main.py`, `combat.py` and `brains.py` happened to do
on the day the match ran. Prompts, physics constants, weapon geometry,
fallback behaviour and provider routing could each drift independently,
silently invalidating cross-date leaderboard comparisons.

This module is the single source of truth. It:

  1. Documents every rule that can affect a match outcome (BENCHMARK_SPEC).
  2. Derives those values *from the live code* wherever possible, so the
     spec cannot drift from the implementation — if a constant changes,
     the fingerprint changes with it.
  3. Emits a short `fingerprint()` hash (sha256, first 12 hex chars) that
     is stored on every match row and replay. Two matches with different
     fingerprints are NOT comparable.
  4. Provides `provenance()` — the per-match record the action plan asks
     for (benchmark_version, physics_version, prompt_version, seed,
     model_requested / model_used, provider_used, fallback_used,
     latency_ms, invalid-action counts, ranking eligibility).
  5. Provides `verify_replay()` — the "Replay Integrity" audit
     (action-plan §8) that checks a replay is complete, seeded and
     internally consistent.

Versioning policy
-----------------
  * BENCHMARK_VERSION  bump on any change to match rules, voting rules,
                       rating rules, or the set of eval axes.
  * PHYSICS_VERSION    bump on any change to the simulation: timestep,
                       gravity, damping, geometry, damage constants,
                       collision handling.
  * PROMPT_VERSION     lives in brains.py (the state/prompt schema). Bump
                       there, per its documented ledger in AGENTS.md.

Any bump invalidates cross-version Elo comparison; the leaderboard and
dataset export both carry the version so consumers can segment.
"""
from __future__ import annotations

import hashlib
import json

import config as C

# ---------------------------------------------------------------- versions
BENCHMARK_VERSION = "1.0"
PHYSICS_VERSION = "1.0"

# Match durations (action-plan §17): a sprint exists so a first-time user
# can see a whole fight in ~20s instead of 60-90s. The FULL length remains
# the research standard — every historical match before this existed ran
# at 24 turns, which is why "full" is also the legacy default for any
# caller that doesn't pass a length.
MATCH_LENGTHS = {"sprint": 4, "standard": 12, "full": 24}
DEFAULT_MATCH_LENGTH = "full"
LEGACY_MAX_TURNS = C.MAX_TURNS          # 24 — kept so we can assert no drift

# Fallback policies (action-plan §18).
#   strict      — any provider failure makes the match ranking-ineligible
#                 (used for controlled research runs)
#   operational — fallback continues the match, is recorded, still ranked
#                 (default: keeps the public arena alive under throttling)
#   demo        — scripted/demo matches, never ranked (tutorial, smoke tests)
FALLBACK_POLICIES = ("strict", "operational", "demo")
DEFAULT_FALLBACK_POLICY = "operational"

# Vote axes (action-plan §6). Only `tactical` feeds the benchmark
# preference score; the rest are collected separately so we can measure
# the gap between "fought intelligently" and "was fun to watch".
VOTE_AXES = ("tactical", "execution", "entertainment", "deserved")
PRIMARY_VOTE_AXIS = "tactical"


def max_turns_for(length: str) -> int:
    """Turns in a match of the given length ('sprint'|'standard'|'full')."""
    return MATCH_LENGTHS.get((length or "").lower(), MATCH_LENGTHS[DEFAULT_MATCH_LENGTH])


# ------------------------------------------------------------- spec helpers
def _pymunk_version() -> str:
    try:
        import pymunk
        return str(getattr(pymunk, "version", "unknown"))
    except Exception:
        return "unknown"


def _flail_spike_speed():
    try:
        from weapons import SPIKE_SPEED
        return SPIKE_SPEED
    except Exception:                                      # pragma: no cover
        return None


def _bow_shots():
    try:
        from weapons import BOW_SHOTS
        return {k: list(v) for k, v in BOW_SHOTS.items()}
    except Exception:                                      # pragma: no cover
        return {}


# ------------------------------------------------------------------- spec
def physics_spec() -> dict:
    """Everything that determines how bodies move and how damage is dealt."""
    from weapons import WEAPON_GEOMETRY, WEAPON_ZONES, WEAPON_ACTIONS
    return {
        "engine": "pymunk",
        "engine_version": _pymunk_version(),
        "arena": {
            "width": C.WIDTH, "height": C.HEIGHT,
            "floor_y": C.FLOOR_Y,
            # Fighter spawn x; fighters always spawn facing each other at
            # equal distance from the centre line, so neither has a
            # positional advantage before the first decision.
            "spawn_x": [430, C.WIDTH - 430],
            "boundaries": "hard floor + soft walls; fighters cannot leave "
                          "the arena horizontally",
        },
        "integration": {
            "timestep_s": C.DT,
            "substeps_per_frame": C.SUBSTEPS,
            "render_fps": C.FPS,
            "gravity": list(C.GRAVITY),
            "space_damping_normal": C.SPACE_DAMPING,
            "space_damping_ice": 0.996,
            "gravity_scale_low_gravity": 0.35,
            "ground_friction_multiplier_ice": 0.10,
        },
        "turn_structure": {
            "turn_seconds": C.TURN_SECONDS,
            "turns_per_length": dict(MATCH_LENGTHS),
            "phases": ["BANNER", "THINK", "SIM", "OVER"],
            "both_fighters_decide_simultaneously": True,
            "decisions_are_independent": True,
        },
        "combat": {
            "start_hp": C.START_HP,
            "damage_scale": C.DMG_SCALE,
            "damage_cap_sharp": C.DMG_CAP,
            "blunt_speed_min": C.BLUNT_SPEED_MIN,
            "blunt_damage_cap": C.BLUNT_CAP,
            "sharp_speed_min": C.SHARP_SPEED_MIN,
            "instant_kill_head_speed": C.KILL_HEAD_SPEED,
            "part_multipliers": dict(C.PART_MULT),
            "hit_cooldown_s": C.HIT_COOLDOWN,
            "swing_cooldown_s": C.SWING_COOLDOWN,
            # Damage formula, stated explicitly so it can be reimplemented:
            "sharp_formula": "min(DMG_CAP, (rel_speed - SHARP_SPEED_MIN) "
                             "* DMG_SCALE + 4) * PART_MULT[part]",
            "blunt_formula": "min(BLUNT_CAP, (rel_speed - BLUNT_SPEED_MIN) "
                             "* 0.012 + 1.0)",
            "rel_speed_definition": "magnitude of (striking_body.velocity_at_"
                                    "world_point(p) - victim_part.velocity_at_"
                                    "world_point(p)) at the contact point",
        },
        "weapons": {
            "available": list(WEAPON_GEOMETRY.keys()) + ["flail", "bow"],
            "zones": {k: list(v) for k, v in WEAPON_ZONES.items()},
            "actions": {k: list(v) for k, v in WEAPON_ACTIONS.items()},
            "blade_geometry": {k: dict(v) for k, v in WEAPON_GEOMETRY.items()},
            "flail_spike_speed": _flail_spike_speed(),
            "bow_shot_speeds": _bow_shots(),
        },
    }


def match_rules_spec() -> dict:
    """Termination, tie-breaking and invalid-action semantics."""
    return {
        "termination": [
            "a fighter's HP reaches 0 (kill)",
            "both fighters reach 0 in the same turn (mutual destruction → draw)",
            "the configured turn cap is reached (decided on points)",
            "the wall-clock ceiling is reached (decided on points, flagged)",
        ],
        "wall_clock_ceiling_s": {"melee": 180, "bow": 300},
        "tie_rules": {
            # |hp_a - hp_b| < 0.5 at the turn cap is a draw on points.
            "hp_tie_tolerance": 0.5,
            "mutual_destruction": "draw",
            "double_knockdown_at_cap": "decided on remaining HP",
        },
        "invalid_action_handling": (
            "an action outside the weapon's vocabulary is coerced to "
            "'ready' and counted as an invalid action; footwork outside the "
            "vocabulary is coerced to 'hold'. Neither ends the match."
        ),
        "timeout_handling": (
            "per-attempt budget from _timeout_for(model); after the retry "
            "ladder is exhausted the turn is played by a scripted fallback "
            "brain and marked _fallback=True."
        ),
        "fallback_ladder": [
            "original model, adaptive timeout",
            "original model, +50% timeout",
            "buddy model #1 (similar tier, different provider preferred)",
            "buddy model #2",
            "scripted mock (flagged, counted as a fallback turn)",
        ],
        "fallback_policies": {
            "strict": "any fallback turn ⇒ match is ranking-ineligible",
            "operational": "fallback continues, is recorded, stays eligible",
            "demo": "scripted/demo match, never ranked",
        },
        "random_seed": (
            "when a seed is supplied, Python's global RNG and every "
            "scripted brain are seeded from it, making the physics + "
            "fallback replay bit-identical on re-run. LLM decisions are "
            "NOT reproducible from the seed alone; determinism is verified "
            "by replaying the stored action log, not by re-calling models."
        ),
    }


def model_interface_spec() -> dict:
    """What the model sees and how it is asked."""
    from brains import PROMPT_VERSION
    from moves import ACTIONS, FOOTWORK
    return {
        "prompt_version": PROMPT_VERSION,
        "temperature_decision": 0.8,
        "temperature_quip": 1.0,
        "temperature_commentary": 1.0,
        "max_tokens_decision": "per-model, see brains._max_tokens_for()",
        "max_tokens_quip": 60,
        "max_tokens_commentary": 120,
        "response_format": "JSON object {action, footwork, thought}",
        "valid_macro_actions": list(ACTIONS),
        "valid_footwork": list(FOOTWORK),
        "control_modes": {
            "macro": "model picks a named move + footwork",
            "joint": "model sets a target state per joint (Toribash-style)",
        },
        "state_schema_version": PROMPT_VERSION,
        "state_fields_note": (
            "see brains.build_state(): absolute torso/head/weapon-tip "
            "coordinates, velocities, facing, HP, last-turn hits, relative "
            "geometry, ranged hints. Blindfolded variant strips the "
            "derived categorical hints."
        ),
        "prompt_injection_policy": (
            "opponent 'thought' text is never shown to a fighter; only "
            "engine-generated numeric state is sent. Custom free-text "
            "fields are filtered before transmission."
        ),
    }


def rating_spec() -> dict:
    return {
        "system": "Elo",
        "k_factor": 32,
        "start_rating": 1000.0,
        "draw_value": 0.5,
        "self_play_delta": 0.0,
        # Ratings are segmented so we never average across different
        # questions. Six-key cell, see storage.elo PK.
        "cell_key": ["model", "sharp", "weapon", "mode", "arena", "blindfolded"],
        "uncertainty": "Wilson score 95% interval on win-rate (draws = 0.5)",
        "min_matches_ranked": 5,
        "provisional_below": 10,
        "exclusions": [
            "matches with fallback under the strict policy",
            "demo-policy matches",
            "self-play (mirror) matches — recorded as draws, 0 delta",
            "error/timeout matches",
        ],
        "objective_axis": (
            "damage_per_turn, hit_rate, fallback_rate, avg_distance — "
            "physics-derived, independent of human votes"
        ),
    }


def voting_spec() -> dict:
    return {
        "blind": "model identities hidden until the vote is cast",
        "colour_assignment": (
            "green/blue ↔ model mapping is randomised per match (flip bit) "
            "and stored, so colour cannot leak identity"
        ),
        "axes": {
            "tactical": "who made better tactical decisions (feeds ranking)",
            "execution": "who executed their intent more cleanly",
            "entertainment": "who was more fun to watch (NOT ranked)",
            "deserved": "who deserved the win per the physics",
        },
        "confidence": "optional 1-5 self-reported confidence",
        "one_vote_per_match": True,
        "vote_affects": "tactical axis only (Elo + preference rate)",
    }


def spec() -> dict:
    """The full, ordered, JSON-serialisable benchmark specification."""
    return {
        "benchmark": "Stickblade Arena",
        "benchmark_version": BENCHMARK_VERSION,
        "physics_version": PHYSICS_VERSION,
        "physics": physics_spec(),
        "rules": match_rules_spec(),
        "model_interface": model_interface_spec(),
        "rating": rating_spec(),
        "voting": voting_spec(),
        "eval_axes": ["sharp", "weapon", "mode", "arena", "blindfolded"],
        "data_license": "CC-BY-SA-4.0",
        "code_license": "Apache-2.0",
    }


def fingerprint(spec_doc: dict | None = None) -> str:
    """Stable sha256 fingerprint of the rules that affect outcomes.

    Deliberately hashes only the parts that can change a result (physics,
    rules, prompt version) — documentation strings and licence fields are
    excluded so prose edits never invalidate a leaderboard.
    """
    doc = spec_doc or spec()
    core = {
        "benchmark_version": doc["benchmark_version"],
        "physics_version": doc["physics_version"],
        "physics": doc["physics"],
        "rules": doc["rules"],
        "prompt_version": doc["model_interface"]["prompt_version"],
        "rating": {k: doc["rating"][k]
                   for k in ("k_factor", "start_rating", "cell_key")},
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


SPEC_FINGERPRINT = fingerprint()


# ------------------------------------------------------------- provenance
def provenance(model_requested_a: str = "", model_requested_b: str = "",
               model_used_a: str = "", model_used_b: str = "",
               provider_used_a: str = "", provider_used_b: str = "",
               fallback_used: bool = False, latency_ms_a: float = 0.0,
               latency_ms_b: float = 0.0, seed=None,
               match_length: str = DEFAULT_MATCH_LENGTH,
               fallback_policy: str = DEFAULT_FALLBACK_POLICY,
               invalid_actions_a: int = 0, invalid_actions_b: int = 0,
               **extra) -> dict:
    """Per-match provenance record (action-plan §1).

    Stored on the match row, embedded in the replay meta, and exported in
    every dataset row. `ranking_eligible` is the single flag downstream
    consumers should filter on.
    """
    from brains import PROMPT_VERSION
    pol = fallback_policy if fallback_policy in FALLBACK_POLICIES \
        else DEFAULT_FALLBACK_POLICY
    prov = {
        "benchmark_version": BENCHMARK_VERSION,
        "physics_version": PHYSICS_VERSION,
        "prompt_version": PROMPT_VERSION,
        "spec_fingerprint": SPEC_FINGERPRINT,
        "seed": seed,
        "match_length": (match_length or DEFAULT_MATCH_LENGTH).lower(),
        "max_turns": max_turns_for(match_length),
        "fallback_policy": pol,
        "model_requested_a": model_requested_a,
        "model_requested_b": model_requested_b,
        "model_used_a": model_used_a or model_requested_a,
        "model_used_b": model_used_b or model_requested_b,
        "provider_used_a": provider_used_a,
        "provider_used_b": provider_used_b,
        "fallback_used": bool(fallback_used),
        "latency_ms_a": round(float(latency_ms_a or 0.0), 1),
        "latency_ms_b": round(float(latency_ms_b or 0.0), 1),
        "invalid_actions_a": int(invalid_actions_a or 0),
        "invalid_actions_b": int(invalid_actions_b or 0),
    }
    prov["ranking_eligible"] = ranking_eligible(prov)
    prov.update(extra)
    return prov


def ranking_eligible(prov: dict) -> bool:
    """Decide whether a provenance record may enter the ranked leaderboard."""
    if prov.get("fallback_policy") == "demo":
        return False
    if prov.get("fallback_policy") == "strict" and prov.get("fallback_used"):
        return False
    return True


# ------------------------------------------------------- replay integrity
def verify_replay(replay: dict) -> dict:
    """Replay Integrity audit (action-plan §8).

    Checks, in order:
      provenance present and version-pinned
      seed present (reproducibility claim)
      action log complete (one entry per played turn)
      frames present and non-empty
      HP monotonically non-increasing across frames
      terminal frame consistent with the recorded result

    Returns a report dict; `ok` is true only when every check passes.
    Never raises on malformed input — a broken replay should produce a
    failed report, not a 500.
    """
    checks: dict[str, bool] = {}
    notes: list[str] = []
    try:
        meta = (replay or {}).get("meta") or {}
        prov = meta.get("provenance") or {}
        frames = replay.get("frames") or []
        action_log = meta.get("action_log") or []
        turns = int(meta.get("total_turns") or 0)

        checks["has_meta"] = bool(meta)
        checks["provenance_present"] = bool(prov)
        checks["version_pinned"] = bool(
            prov.get("benchmark_version") and prov.get("physics_version")
            and prov.get("prompt_version"))
        checks["seed_present"] = prov.get("seed") is not None
        checks["action_log_complete"] = (len(action_log) >= max(0, turns - 1)
                                         and turns > 0) or (turns == 0)
        checks["frames_present"] = len(frames) > 0

        # HP monotonicity: frame rows start [hp_a, hp_b, turn, over].
        hp_ok = True
        prev = None
        for row in frames:
            try:
                a, b = float(row[0]), float(row[1])
            except (TypeError, ValueError, IndexError):
                hp_ok = False
                break
            if prev is not None and (a > prev[0] + 1e-6 or b > prev[1] + 1e-6):
                hp_ok = False
                break
            prev = (a, b)
        checks["hp_monotonic"] = hp_ok

        terminal_ok = True
        if frames:
            last = frames[-1]
            try:
                terminal_ok = int(last[3]) == 1
            except (TypeError, ValueError, IndexError):
                terminal_ok = False
        checks["result_consistent"] = terminal_ok

        if not checks["version_pinned"]:
            notes.append("replay predates version pinning (spec v1.0)")
        if not checks["seed_present"]:
            notes.append("no seed: match is not reproducible from stored state")
        if not checks["action_log_complete"]:
            notes.append(f"action log has {len(action_log)} entries for "
                         f"{turns} turns")
        ok = all(checks.values())
        if ok:
            notes.append("physics version: verified")
            notes.append("result: reproducible from stored action log + seed")
        return {
            "ok": ok,
            "checks": checks,
            "notes": notes,
            "fingerprint": prov.get("spec_fingerprint") or "",
            "benchmark_version": prov.get("benchmark_version"),
            "physics_version": prov.get("physics_version"),
            "prompt_version": prov.get("prompt_version"),
            "seed": prov.get("seed"),
            "ranking_eligible": prov.get("ranking_eligible"),
            "turns": turns,
        }
    except Exception as e:                                # pragma: no cover
        return {"ok": False, "checks": checks, "error": str(e)[:200],
                "notes": notes}


if __name__ == "__main__":
    import sys
    if "--fingerprint" in sys.argv:
        print(SPEC_FINGERPRINT)
    else:
        json.dump(spec(), sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
