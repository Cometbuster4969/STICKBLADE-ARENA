"""State ablations (action-plan §11).

The state we hand a model is a hypothesis about what a fighter needs.
Ablations test it. These tests pin the properties that make an ablation
result trustworthy rather than an artefact: every ablation must produce a
structurally valid state, must not mutate the caller's state, and an
unknown ablation name must fail loudly instead of silently running the
baseline.
"""
import copy
import json

import conftest                                            # noqa: F401
import pytest

import ablations


def _state():
    """A realistic mid-match state shaped like build_state()'s output."""
    return {
        "turn": 4, "turns_left": 8, "arena": "normal",
        "my_hp": 78.4, "enemy_hp": 61.2,
        "distance": 180, "my_height": "standing", "enemy_height": "standing",
        "enemy_last_action": "advance", "my_last_action": "guard",
        "enemy_sword_tip_distance_to_me": 55,
        "last_turn_hits": [{"by": "enemy", "zone": "tip", "hit_part": "torso",
                            "damage": 6.4, "was_sharp": True}],
        "me": {"torso": [520, 150], "head": [520, 190],
               "weapon_tip": [575, 160], "off_hand": [505, 130],
               "facing": 1, "velocity": [40, 0]},
        "enemy": {"torso": [700, 152], "head": [700, 192],
                  "facing": -1, "velocity": [-20, 5]},
        "relative": {"dx": 180, "dy": 2, "head_dx": 180, "head_dy": 2,
                     "head_to_head_distance": 180, "enemy_is": "right",
                     "enemy_height_relative": "level", "facing_enemy": True},
        "ranged_hint": {"arrow_flight_time_s": 0.18,
                        "vertical_drop_to_compensate": 12,
                        "per_shot": {"draw_shot": {"flight_time_s": 0.18,
                                                   "vertical_drop_to_compensate": 12},
                                     "quick_shot": {"flight_time_s": 0.28,
                                                    "vertical_drop_to_compensate": 29},
                                     "high_arc_shot": {"flight_time_s": 0.24,
                                                       "vertical_drop_to_compensate": 21}},
                        "gravity_scale": 1.0,
                        "aim_at_enemy_head": [700, 192]},
    }


def test_every_ablation_is_registered_and_named():
    names = ablations.names()
    assert names[0] == "baseline"
    assert len(names) == len(set(names))
    assert set(names) == set(ablations.BY_NAME)


def test_unknown_ablation_raises_instead_of_silently_running_baseline():
    with pytest.raises(KeyError):
        ablations.apply("no_velocity_but_spelled_wrong", _state())


def test_ablations_produce_structurally_valid_states():
    assert ablations.validate(_state()) == [], ablations.validate(_state())


def test_no_ablation_mutates_the_input_state():
    """A sweep applies every ablation to the SAME state; if one mutated it
    the later ablations would be measured on a doctored payload."""
    original = _state()
    snapshot = copy.deepcopy(original)
    for name in ablations.names():
        ablations.apply(name, original)
        assert original == snapshot, f"{name} mutated the input state"


def test_each_ablation_removes_what_it_says_it_removes():
    s = _state()
    assert "velocity" not in ablations.apply("no_velocity", s)["me"]
    assert "enemy_last_action" not in ablations.apply(
        "no_opponent_last_action", s)
    assert "weapon_tip" not in ablations.apply("no_weapon_geometry", s)["me"]
    assert "arena" not in ablations.apply("no_arena_modifier", s)
    assert "last_turn_hits" not in ablations.apply("no_history", s)
    assert "head" not in ablations.apply("no_head_positions", s)["me"]
    bf = ablations.apply("blindfolded", s)
    assert "enemy_is" not in bf["relative"] and "distance" not in bf
    # raw coordinates must survive the blindfold — that is the whole point
    assert bf["me"]["torso"] == [520, 150]


def test_normalized_coords_stay_in_unit_range():
    s = ablations.apply("normalized_coords", _state())
    for key in ("torso", "head", "weapon_tip", "off_hand"):
        for v in s["me"][key]:
            assert 0.0 <= v <= 1.0, (key, s["me"][key])


def test_raw_coords_control_is_identical_to_baseline():
    """If someone makes normalized the default, raw must remain a distinct,
    tested representation rather than silently becoming the same thing."""
    s = _state()
    assert json.dumps(ablations.apply("raw_coords", s), sort_keys=True) == \
        json.dumps(ablations.apply("baseline", s), sort_keys=True)


def test_field_cost_reports_a_delta_per_ablation():
    res = ablations.field_cost(_state())
    assert res["baseline_tokens"] > 0
    assert len(res["rows"]) == len(ablations.names())
    by = {r["ablation"]: r for r in res["rows"]}
    assert by["baseline"]["delta_vs_baseline"] == 0.0
    # Every ablation that removes something must cost less than baseline.
    for name in ("no_velocity", "no_history", "no_weapon_geometry",
                 "no_arena_modifier", "no_head_positions", "blindfolded"):
        assert by[name]["delta_vs_baseline"] < 0, (name, by[name])


def test_validate_catches_a_state_with_no_position_information():
    broken = {"turn": 1, "my_hp": 100.0, "enemy_hp": 100.0}
    problems = ablations.validate(broken)
    assert problems, "a state with no position data must be flagged"
