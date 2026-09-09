"""Bradley-Terry rating model: correctness, not just "it runs".

A rating model that is wrong is worse than no rating model, because it
manufactures an ordering that looks authoritative. These tests pin the
analytic properties we actually rely on:

  * a known win rate recovers the known log-odds
  * symmetric records give symmetric ratings
  * draws pull ratings toward each other rather than being discarded
  * a sparse undefeated record does NOT produce an infinite rating
  * more data means a tighter interval (the whole point of publishing CIs)
  * cycle (rock-paper-scissors) does not manufacture a spurious ordering
  * disconnected components are reported, not silently merged
  * the canvas-vote -> model-pair mapping respects the flip bit (getting
    this wrong would rank the wrong model, and nothing else would look off)
"""
import math

import conftest                                            # noqa: F401
import pytest

from ratings import (SCALE, bradley_terry, fit_with_ci,
                     preference_pairs_from_votes)


def _diff(pairs, a="A", b="B"):
    t = bradley_terry(pairs)
    return t[a] - t[b]


def test_known_win_rate_recovers_known_log_odds():
    """90 wins / 10 losses => log(9) logits, within the ridge's shrinkage."""
    pairs = [("A", "B", 1.0)] * 90 + [("B", "A", 1.0)] * 10
    got, want = _diff(pairs), math.log(9)
    # ridge shrinks slightly toward 0; anything beyond 5% means the update
    # is not solving the score equation any more.
    assert abs(got - want) / want < 0.05, f"got {got:.4f}, want ~{want:.4f}"


def test_symmetric_records_are_symmetric():
    pairs = [("A", "B", 1.0)] * 50 + [("B", "A", 1.0)] * 50
    assert abs(_diff(pairs)) < 1e-6


def test_all_draws_are_symmetric_and_nu_is_large():
    pairs = [("A", "B", 0.5), ("B", "A", 0.5)] * 20
    t = bradley_terry(pairs)
    assert abs(t["A"] - t["B"]) < 1e-6
    # Davidson's tie parameter must grow when everything is a draw; a fixed
    # small nu would flatten genuine differences instead.
    assert t["_nu"] > 1.0, t["_nu"]


def test_no_ties_collapses_to_plain_bradley_terry():
    """nu must be estimated, not assumed: no draws => nu == 0."""
    pairs = [("A", "B", 1.0)] * 30 + [("B", "A", 1.0)] * 10
    assert bradley_terry(pairs)["_nu"] == 0.0


def test_draws_shrink_the_gap_relative_to_wins_only():
    wins_only = [("A", "B", 1.0)] * 60 + [("B", "A", 1.0)] * 20
    with_draws = wins_only + [("A", "B", 0.5), ("B", "A", 0.5)] * 20
    assert _diff(with_draws) < _diff(wins_only)


def test_undefeated_newcomer_stays_finite():
    """3-0 must not produce an infinite rating — the sparse-data trap."""
    pairs = ([("A", "B", 1.0)] * 40 + [("B", "A", 1.0)] * 40
             + [("C", "B", 1.0)] * 3)
    t = bradley_terry(pairs)
    for k, v in t.items():
        if k == "_nu":
            continue
        assert math.isfinite(v), f"{k} is not finite: {v}"
        assert abs(v) < 10, f"{k} ran away to {v}"


def test_more_data_gives_a_tighter_interval():
    small = [("A", "B", 1.0)] * 7 + [("B", "A", 1.0)] * 3
    big = [("A", "B", 1.0)] * 70 + [("B", "A", 1.0)] * 30
    rows_s = {r["model"]: r for r in fit_with_ci(small, bootstraps=200)}
    rows_b = {r["model"]: r for r in fit_with_ci(big, bootstraps=200)}
    w_s = rows_s["A"]["ci_high"] - rows_s["A"]["ci_low"]
    w_b = rows_b["A"]["ci_high"] - rows_b["A"]["ci_low"]
    assert w_b < w_s, f"n=100 width {w_b} should be < n=10 width {w_s}"


def test_interval_contains_the_point_estimate():
    pairs = [("A", "B", 1.0)] * 20 + [("B", "A", 1.0)] * 8
    for r in fit_with_ci(pairs, bootstraps=200):
        assert r["ci_low"] <= r["rating"] <= r["ci_high"], r


def test_cycle_does_not_manufacture_an_ordering():
    """A beats B beats C beats A: no model is better, so none may rank above."""
    pairs = ([("A", "B", 1.0)] * 20 + [("B", "C", 1.0)] * 20
             + [("C", "A", 1.0)] * 20)
    rows = fit_with_ci(pairs, bootstraps=50)
    ratings = [r["rating"] for r in rows]
    assert max(ratings) - min(ratings) < 1.0, ratings


def test_disconnected_components_are_reported_separately():
    pairs = [("A", "B", 1.0)] * 5 + [("X", "Y", 1.0)] * 5
    rows = {r["model"]: r for r in fit_with_ci(pairs, bootstraps=50)}
    assert rows["A"]["component"] != rows["X"]["component"]
    # Both losers happen to be rated the same; the point is that A and X are
    # NOT comparable, and the payload says so.
    assert all(r["provisional"] for r in rows.values())


def test_preference_rate_and_counts_are_present():
    pairs = [("A", "B", 1.0)] * 6 + [("B", "A", 1.0)] * 2 + [
        ("A", "B", 0.5), ("B", "A", 0.5)] * 2
    rows = {r["model"]: r for r in fit_with_ci(pairs, bootstraps=50)}
    a, b = rows["A"], rows["B"]
    assert a["matches"] == 10 and b["matches"] == 10
    assert a["wins"] == 6 and a["losses"] == 2 and a["draws"] == 2
    # 6 wins + half of 2 draws = 7 points / 10
    assert abs(a["preference_rate"] - 0.7) < 1e-9
    assert a["rating"] > b["rating"]


def test_rating_scale_is_elo_readable():
    """One logit should be ~173.7 points, so the column is legible."""
    assert abs(SCALE - 400 / math.log(10)) < 1e-9


def test_vote_pairs_map_canvas_sides_to_models_through_flip():
    rows = [
        # no flip: canvas 'a' is model_a
        {"model_a": "m1", "model_b": "m2", "flip": False, "choice": "a"},
        # flipped: canvas 'a' is model_b
        {"model_a": "m1", "model_b": "m2", "flip": True, "choice": "a"},
        {"model_a": "m1", "model_b": "m2", "flip": False, "choice": "draw"},
        # self-play: not estimable, must be dropped
        {"model_a": "m1", "model_b": "m1", "flip": False, "choice": "a"},
        # ranking-ineligible (strict fallback policy): excluded
        {"model_a": "m3", "model_b": "m4", "flip": False, "choice": "a",
         "ranking_eligible": False},
    ]
    pairs = preference_pairs_from_votes(rows)
    assert pairs == [("m1", "m2", 1.0), ("m2", "m1", 1.0),
                     ("m1", "m2", 0.5), ("m2", "m1", 0.5)]


def test_empty_input_is_handled():
    assert fit_with_ci([]) == []
    assert bradley_terry([]) == {}


@pytest.mark.parametrize("garbage", [
    [("A", "B", 0.0)],          # zero weight
    [("", "B", 1.0)],           # empty id
    [("A", "A", 1.0)],          # self-play only
    [("A", "B", -1.0)],         # negative weight
    [("A", "B", float("nan"))],  # NaN
])
def test_degenerate_input_does_not_raise(garbage):
    """The fitter is fed user-generated data; it must never raise."""
    try:
        out = fit_with_ci(garbage, bootstraps=10)
        assert isinstance(out, list)
    except Exception as e:                                  # pragma: no cover
        pytest.fail(f"raised {type(e).__name__}: {e}")


def test_bootstrap_resamples_matches_not_pair_rows():
    """A draw is stored as two pair rows but is ONE match.

    Resampling rows would give every draw twice the sampling weight of a
    decided match, and would report a tighter interval than the data
    supports — precisely when draws are common. `_match_units` must pair
    the two directed draw rows back up.
    """
    from ratings import _match_units
    pairs = ([("A", "B", 1.0)] * 4                       # 4 decided matches
             + [("A", "B", 0.5), ("B", "A", 0.5)] * 3)   # 3 draws = 6 rows
    units = _match_units(pairs)
    assert len(units) == 7, f"expected 7 matches, grouped as {units}"
    assert sorted(len(u) for u in units) == [1, 1, 1, 1, 2, 2, 2]


def test_draw_weighting_matches_the_documented_preference_rate():
    """End-to-end: 6W/2L/2D must report n=10 and preference_rate 0.7."""
    pairs = ([("A", "B", 1.0)] * 6 + [("B", "A", 1.0)] * 2
             + [("A", "B", 0.5), ("B", "A", 0.5)] * 2)
    row = next(r for r in fit_with_ci(pairs, bootstraps=100) if r["model"] == "A")
    assert row["matches"] == 10, row
    assert row["draws"] == 2, row
    assert row["preference_rate"] == 0.7, row
