"""Benchmark specification v1.0 — the ruleset must be complete, stable and
sensitive to change (action-plan §1).

If the physics constants drift and the fingerprint does NOT change, the
whole version-pinning story is a lie, so we test that explicitly.
"""
import importlib

import conftest
import pytest

conftest.init_pygame()
import config as C                                    # noqa: E402
import benchmark as B                                 # noqa: E402


def test_spec_has_every_section_the_action_plan_requires():
    s = B.spec()
    for key in ("physics", "rules", "model_interface", "rating", "voting"):
        assert key in s, f"spec missing section {key}"
    phys = s["physics"]
    for key in ("arena", "integration", "turn_structure", "combat", "weapons"):
        assert key in phys
    # The action plan lists these as must-document items.
    rules = s["rules"]
    for key in ("termination", "tie_rules", "invalid_action_handling",
                "timeout_handling", "fallback_ladder", "fallback_policies",
                "random_seed"):
        assert key in rules, f"rules missing {key}"


def test_versions_are_declared():
    assert B.BENCHMARK_VERSION == "1.0"
    assert B.PHYSICS_VERSION == "1.0"
    assert isinstance(B.SPEC_FINGERPRINT, str) and len(B.SPEC_FINGERPRINT) == 12


def test_fingerprint_is_stable_across_calls():
    assert B.fingerprint() == B.fingerprint() == B.SPEC_FINGERPRINT


def test_fingerprint_changes_when_physics_constants_change():
    """The core promise: a physics change invalidates comparability."""
    original = C.DMG_SCALE
    try:
        C.DMG_SCALE = original * 1.5
        changed = B.fingerprint()
    finally:
        C.DMG_SCALE = original
    assert changed != B.SPEC_FINGERPRINT
    assert B.fingerprint() == B.SPEC_FINGERPRINT      # restored


def test_fingerprint_changes_when_prompt_version_changes(monkeypatch):
    import brains
    monkeypatch.setattr(brains, "PROMPT_VERSION", 99, raising=True)
    assert B.fingerprint() != B.SPEC_FINGERPRINT


def test_match_lengths():
    assert B.MATCH_LENGTHS["sprint"] == 4
    assert B.MATCH_LENGTHS["standard"] == 12
    assert B.MATCH_LENGTHS["full"] == 24
    assert B.max_turns_for("nonsense") == B.MATCH_LENGTHS[B.DEFAULT_MATCH_LENGTH]
    assert B.LEGACY_MAX_TURNS == 24      # historic matches were 24-turn


def test_fallback_policy_drives_ranking_eligibility():
    op = B.provenance("a", "b", fallback_policy="operational",
                      fallback_used=True)
    assert op["ranking_eligible"] is True
    strict = B.provenance("a", "b", fallback_policy="strict",
                          fallback_used=True)
    assert strict["ranking_eligible"] is False
    strict_clean = B.provenance("a", "b", fallback_policy="strict",
                                fallback_used=False)
    assert strict_clean["ranking_eligible"] is True
    demo = B.provenance("a", "b", fallback_policy="demo")
    assert demo["ranking_eligible"] is False


def test_provenance_records_every_field_the_plan_asks_for():
    p = B.provenance("model/a", "model/b", model_used_a="model/a",
                     provider_used_a="openrouter", fallback_used=False,
                     latency_ms_a=4210.0, seed=123456)
    for key in ("benchmark_version", "physics_version", "prompt_version",
                "spec_fingerprint", "seed", "model_requested_a",
                "model_used_a", "provider_used_a", "fallback_used",
                "latency_ms_a"):
        assert key in p, f"provenance missing {key}"


def test_verify_replay_accepts_a_well_formed_replay():
    good = {"meta": {"provenance": {"benchmark_version": "1.0",
                                    "physics_version": "1.0",
                                    "prompt_version": 1,
                                    "seed": 7}, "total_turns": 3,
                     "action_log": [{"turn": 1, "a": {"action": "thrust"},
                                     "b": {"action": "ready"}},
                                    {"turn": 2, "a": {"action": "thrust"},
                                     "b": {"action": "guard_high"}},
                                    {"turn": 3, "a": {"action": "thrust"},
                                     "b": {"action": "advance"}}]},
            "frames": [[100, 100, 1, 0], [90, 100, 2, 0], [80, 95, 3, 1]],
            "events": []}
    rep = B.verify_replay(good)
    assert rep["ok"] is True
    assert rep["checks"]["hp_monotonic"] is True
    assert rep["checks"]["result_consistent"] is True


def test_verify_replay_flags_broken_replays():
    no_prov = {"meta": {}, "frames": [[1, 1, 1, 1]], "events": []}
    rep = B.verify_replay(no_prov)
    assert rep["ok"] is False
    assert rep["checks"]["provenance_present"] is False

    hp_heals = {"meta": {"provenance": {"benchmark_version": "1.0",
                                        "physics_version": "1.0",
                                        "prompt_version": 1, "seed": 1},
                         "total_turns": 2},
                "frames": [[100, 100, 1, 0], [110, 100, 2, 1]]}
    rep = B.verify_replay(hp_heals)
    assert rep["checks"]["hp_monotonic"] is False

    truncated = {"meta": {"provenance": {"benchmark_version": "1.0",
                                         "physics_version": "1.0",
                                         "prompt_version": 1, "seed": 1},
                          "total_turns": 6, "action_log": []},
                 "frames": [[100, 100, 1, 1]]}
    rep = B.verify_replay(truncated)
    assert rep["checks"]["action_log_complete"] is False


def test_verify_replay_never_raises_on_garbage():
    for bad in (None, {}, {"meta": "not-a-dict"}, {"frames": "nope"}):
        rep = B.verify_replay(bad)
        assert rep["ok"] is False


def test_spec_documents_the_damage_formula():
    combat = B.spec()["physics"]["combat"]
    assert "sharp_formula" in combat and "blunt_formula" in combat
    assert combat["damage_cap_sharp"] == C.DMG_CAP
    assert combat["part_multipliers"] == C.PART_MULT
    assert combat["start_hp"] == C.START_HP


def test_reimport_does_not_recompute_a_different_fingerprint():
    """Import order/state must not change the published fingerprint."""
    mod = importlib.reload(B)
    assert mod.SPEC_FINGERPRINT == B.SPEC_FINGERPRINT


@pytest.mark.parametrize("length,turns", [("sprint", 4), ("standard", 12),
                                          ("full", 24)])
def test_max_turns_for(length, turns):
    assert B.max_turns_for(length) == turns
