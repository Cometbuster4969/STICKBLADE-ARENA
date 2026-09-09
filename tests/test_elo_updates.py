"""Rating + uncertainty tests (action-plan §5, §6, §26).

Raw Elo alone is not a defensible headline number, so the rating path is
tested together with the things that make it honest: cell segmentation,
self-play safety, exclusion of ineligible matches, and the Wilson interval
shown next to every win rate.
"""
import tempfile

import conftest
import pytest

conftest.init_pygame()
from storage import LocalStorage, K_FACTOR, START_ELO    # noqa: E402


@pytest.fixture()
def store():
    return LocalStorage(root=tempfile.mkdtemp(prefix="sba_elo_"))


def _finish(store, a, b, winner_side="a", method="kill", turns=8, **kw):
    mid = store.create_match(a, b, ["tip"], blind=True, **kw)
    store.set_flip(mid, False)
    store.finish_match(mid, winner_side, method, turns,
                       {"meta": {"metrics": {}}, "frames": [],
                        "events": [], "thoughts": []})
    return mid


def test_k_factor_and_start_rating_are_the_published_values():
    assert K_FACTOR == 32
    assert START_ELO == 1000.0


def test_normal_vote_splits_the_k_factor(store):
    mid = _finish(store, "model/a", "model/b")
    r = store.record_vote(mid, "a")
    assert r["elo_change"]["model/a"] == 16.0
    assert r["elo_change"]["model/b"] == -16.0


def test_self_play_is_a_no_op(store):
    mid = _finish(store, "model/a", "model/a")
    r = store.record_vote(mid, "a")
    assert r["elo_change"]["model/a"] == 0.0
    row = store.leaderboard()[0]
    assert row["draws"] == 1


def test_draw_is_worth_half(store):
    mid = _finish(store, "model/a", "model/b")
    store.record_vote(mid, "draw")
    rows = {r["model"]: r for r in store.leaderboard()}
    # Equal ratings → expected 0.5 → draw produces zero movement.
    assert rows["model/a"]["rating"] == START_ELO
    assert rows["model/b"]["rating"] == START_ELO


def test_ratings_are_segmented_per_eval_cell(store):
    """A JOINT-mode win must not move the MACRO rating."""
    mid = _finish(store, "model/a", "model/b", mode="joint")
    store.record_vote(mid, "a")
    macro = {r["model"]: r for r in store.leaderboard(mode="macro")}
    joint = {r["model"]: r for r in store.leaderboard(mode="joint")}
    assert macro.get("model/a", {"rating": START_ELO})["rating"] == START_ELO
    assert joint["model/a"]["rating"] > START_ELO


def test_blindfolded_matches_have_their_own_cell(store):
    mid = _finish(store, "model/a", "model/b", blindfolded=True)
    store.record_vote(mid, "a")
    normal = {r["model"]: r for r in store.leaderboard(blindfolded=False)}
    blind = {r["model"]: r for r in store.leaderboard(blindfolded=True)}
    assert normal.get("model/a", {"rating": START_ELO})["rating"] == START_ELO
    assert blind["model/a"]["rating"] > START_ELO


def test_second_vote_on_a_match_is_idempotent(store):
    mid = _finish(store, "model/a", "model/b")
    first = store.record_vote(mid, "a")
    second = store.record_vote(mid, "b")
    assert second.get("already_voted") is True
    # A second vote must not double-count: the rating stays where the
    # first vote put it (the payload is a reveal, not a re-rating).
    rows = {r["model"]: r for r in store.leaderboard()}
    assert rows["model/a"]["rating"] == START_ELO + first["elo_change"]["model/a"]
    assert rows["model/a"]["wins"] == 1


def test_ranking_ineligible_matches_do_not_move_elo(store):
    mid = _finish(store, "model/a", "model/b", fallback_policy="demo")
    r = store.record_vote(mid, "a")
    assert r["ranking_excluded"] is True
    assert r["elo_change"] == {}
    rows = {x["model"]: x for x in store.leaderboard(weapon="sword")}
    assert rows.get("model/a", {"rating": START_ELO})["rating"] == START_ELO
    # the vote is still recorded — we don't throw away the human signal
    assert store.metrics_snapshot()["matches"]["voted"] == 1


def test_multi_axis_vote_persists_every_axis(store):
    mid = _finish(store, "model/a", "model/b")
    store.record_vote(mid, "b", axes={"execution": "b",
                                      "entertainment": "a",
                                      "deserved": "b"}, confidence=5)
    row = store._conn().execute(
        "SELECT * FROM votes WHERE match_id=?", (mid,)).fetchone()
    assert row["choice"] == "b"
    assert row["execution"] == "b"
    assert row["entertainment"] == "a"       # fan favourite ≠ best tactician
    assert row["deserved"] == "b"
    assert row["confidence"] == 5


def test_wilson_interval_is_a_real_interval():
    from server import _wilson_ci
    rate, lo, hi = _wilson_ci(10, 10, 0)
    assert lo <= rate <= hi
    assert 0.0 <= lo and hi <= 1.0
    assert rate == 0.5
    # More data ⇒ tighter interval
    _, lo2, hi2 = _wilson_ci(100, 100, 0)
    assert (hi2 - lo2) < (hi - lo)
    # No data ⇒ no claim
    assert _wilson_ci(0, 0, 0) == (None, None, None)
    # Draws count as half-wins
    rate_d, _, _ = _wilson_ci(0, 0, 10)
    assert rate_d == 0.5


def test_leaderboard_rows_carry_sample_size_and_uncertainty():
    from server import _wilson_ci
    store = LocalStorage(root=tempfile.mkdtemp(prefix="sba_lb_"))
    for _ in range(3):
        mid = _finish(store, "model/a", "model/b")
        store.record_vote(mid, "a")
    rows = {r["model"]: r for r in store.leaderboard()}
    row = rows["model/a"]
    assert row["wins"] == 3 and row["losses"] == 0
    rate, lo, hi = _wilson_ci(row["wins"], row["losses"], row["draws"])
    assert rate == 1.0 and lo > 0.0 and hi <= 1.0


def test_objective_leaderboard_is_vote_independent(store):
    """Physics-derived metrics exist for unvoted matches too."""
    mid = store.create_match("model/a", "model/b", ["tip"], blind=True)
    store.set_flip(mid, False)
    store.finish_match(mid, "a", "kill", 10, {
        "meta": {"metrics": {"damage_dealt_a": 80.0, "damage_dealt_b": 20.0,
                             "hits_landed_a": 4, "hits_landed_b": 1,
                             "hits_attempted_a": 8, "hits_attempted_b": 5,
                             "fallback_turns_a": 0, "fallback_turns_b": 0,
                             "avg_distance": 120.0}},
        "frames": [], "events": [], "thoughts": []})
    rows = {r["model"]: r for r in store.objective_leaderboard()}
    assert rows["model/a"]["damage_per_turn"] == 8.0
    assert rows["model/b"]["damage_per_turn"] == 2.0
    assert rows["model/b"]["matches"] == 1


def test_metrics_snapshot_counts_ineligible_and_fallbacks(store):
    mid = _finish(store, "model/a", "model/b", fallback_policy="strict")
    store.set_provenance(mid, {"fallback_used": True, "ranking_eligible": False,
                               "latency_ms_a": 100.0, "latency_ms_b": 200.0,
                               "invalid_actions_a": 1})
    store.record_vote(mid, "a")
    snap = store.metrics_snapshot()
    assert snap["matches"]["ranking_ineligible"] == 1
    assert snap["rates"]["completion"] == 1.0
    assert snap["latency_ms_24h"]["n"] == 2


def test_leaderboard_rows_publish_uncertainty_and_eligibility():
    """Ratings must travel with an error bar and a sample size."""
    import server
    uid_a, uid_b = "unit-test/leaderboard-a", "unit-test/leaderboard-b"
    for _ in range(6):
        mid = server.store.create_match(uid_a, uid_b, ["tip"], blind=True)
        server.store.set_flip(mid, False)
        server.store.finish_match(mid, "a", "kill", 6,
                                  {"meta": {"metrics": {}}, "frames": [],
                                   "events": [], "thoughts": []})
        server.store.record_vote(mid, "a")
    rows = {r["model"]: r for r in server.leaderboard()}
    row = rows[uid_a]
    assert row["n"] == 6
    assert row["win_rate"] == 1.0
    assert 0.0 < row["win_rate_lo"] <= row["win_rate_hi"] <= 1.0
    assert row["benchmark_version"] == "1.0"
    assert row["provisional"] is True          # <10 matches
    assert row["eligible"] is True             # >=5 matches
