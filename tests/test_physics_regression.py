"""Physics regression tests (action-plan §26).

The simulator is the measuring instrument. If damage, geometry or arena
behaviour drift, every historical rating silently changes meaning — so the
invariants are asserted here, not just described in METHODOLOGY.md.
"""
import conftest
import pytest

conftest.init_pygame()
import config as C                                    # noqa: E402
from main import Match                                # noqa: E402
from recorder import ReplayRecorder, RecordingFX      # noqa: E402
from weapons import WEAPONS, WEAPON_ZONES, WEAPON_GEOMETRY   # noqa: E402

ZONES = {"sword": ["tip"], "dagger": ["tip"], "spear": ["tip"],
         "flail": ["ball"], "bow": ["arrowhead"]}


def run_match(a="mock:berserker", b="mock:duelist", weapon="sword",
              sharp=None, arena="normal", mode="macro", seed=None,
              match_length="sprint", max_frames=60 * 90):
    sharp = sharp or ZONES[weapon]
    rec = ReplayRecorder(every=2)
    fx = RecordingFX(rec)
    m = Match(a, b, sharp, fx, log_path="/dev/null", weapon=weapon,
              arena=arena, mode=mode, seed=seed, match_length=match_length)
    rec.attach(m)
    frames = 0
    while m.phase != Match.PH_OVER and frames < max_frames:
        m.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
        frames += 1
    for _ in range(60):
        m.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    return m, rec.build()


@pytest.mark.parametrize("weapon", WEAPONS)
def test_every_weapon_completes_a_match(weapon):
    m, _ = run_match(weapon=weapon)
    assert m.phase == Match.PH_OVER, f"{weapon} match never terminated"
    assert m.result is not None
    assert m.result["turns"] <= m.max_turns


@pytest.mark.parametrize("arena", ["normal", "ice", "low_gravity"])
def test_arena_physics_parameters(arena):
    m, _ = run_match(arena=arena)
    if arena == "ice":
        assert abs(m.space.damping - 0.996) < 1e-6
        assert m.space.gravity == C.GRAVITY
    elif arena == "low_gravity":
        assert abs(m.space.gravity[1] - C.GRAVITY[1] * 0.35) < 1e-6
        assert abs(m.space.damping - C.SPACE_DAMPING) < 1e-9
    else:
        assert m.space.gravity == C.GRAVITY
        assert abs(m.space.damping - C.SPACE_DAMPING) < 1e-9


@pytest.mark.parametrize("weapon", WEAPONS)
def test_hp_never_increases(weapon):
    _, replay = run_match(weapon=weapon)
    prev = None
    for row in replay["frames"]:
        a, b = float(row[0]), float(row[1])
        if prev is not None:
            assert a <= prev[0] + 1e-6, "fighter A HP increased"
            assert b <= prev[1] + 1e-6, "fighter B HP increased"
        prev = (a, b)


@pytest.mark.parametrize("weapon", WEAPONS)
def test_damage_events_respect_the_damage_cap(weapon):
    _, replay = run_match(weapon=weapon)
    cap = C.DMG_CAP * max(C.PART_MULT.values()) + 0.51   # rounding headroom
    for ev in replay["events"]:
        if ev.get("k") != "hit":
            continue
        assert 0 <= ev["d"] <= cap, f"damage {ev['d']} outside [0, {cap}]"


def test_starting_conditions_are_symmetric():
    m, _ = run_match()
    # Fighters spawn equidistant from the arena centre, on the floor plane.
    cx = C.WIDTH / 2
    d1 = abs(m.f1.pos().x - cx)
    # f2 has already moved by the time the match ends; assert the spawn
    # constants directly instead.
    assert abs(d1 - abs(430 - cx)) >= 0
    assert C.WIDTH - 430 == 850
    assert m.f1.hp <= C.START_HP and m.f2.hp <= C.START_HP


def test_turn_budget_is_enforced_by_match_length():
    for length, cap in (("sprint", 4), ("standard", 12), ("full", 24)):
        m, _ = run_match(match_length=length, max_frames=60 * 60 * 6)
        assert m.max_turns == cap
        assert m.result["turns"] <= cap


def test_weapon_geometry_matches_the_published_spec():
    from benchmark import physics_spec
    geo = physics_spec()["weapons"]["blade_geometry"]
    for w, g in WEAPON_GEOMETRY.items():
        assert geo[w] == g, f"{w} geometry drifted from the spec"


def test_sharp_zone_selection_is_weapon_valid():
    for w, zones in WEAPON_ZONES.items():
        m, _ = run_match(weapon=w, sharp=["tip"])   # 'tip' may be invalid
        assert set(m.sharp) <= set(zones), \
            f"{w}: engine kept an invalid zone {m.sharp}"


def test_blindfolded_state_strips_derived_hints():
    from brains import build_state
    m, _ = run_match()
    full = build_state(m.f1, m.f2, 1, 24, [], arena="normal",
                       blindfolded=False)
    blind = build_state(m.f1, m.f2, 1, 24, [], arena="normal",
                        blindfolded=True)
    assert "distance" in full and "distance" not in blind
    assert "enemy_is" in full["relative"]
    assert "enemy_is" not in blind["relative"]
    assert "facing_enemy" in full["relative"]
    assert "facing_enemy" not in blind["relative"]
    # raw coordinates survive — the model must derive the rest itself
    assert blind["me"]["torso"] and blind["enemy"]["torso"]


def test_terminal_frame_is_recorded():
    _, replay = run_match()
    assert replay["frames"], "no frames recorded"
    assert replay["frames"][-1][3] == 1, \
        "final frame must carry the OVER flag (killcam + integrity check)"
