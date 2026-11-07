"""Pseudo-replication guard for the balance sweep (action-plan §9).

Scripted bots are deterministic, so re-running the same configuration under a
new seed replays the *same fight* bit-for-bit. The v1.0 balance report
counted those repeats as independent trials: 24 flail rows were 15 distinct
fights, and the "81% side-B" flag was a Wilson interval over a sample that
did not exist. These tests pin the correction.
"""
import csv
import pathlib

import pytest

import weapon_balance as WB

ROOT = pathlib.Path(__file__).resolve().parent.parent
BALANCE_CSV = ROOT / "research" / "balance_matches.csv"


def row(**kw):
    """One balance row with just the fields the signature reads."""
    base = dict(weapon="sword", arena="normal", sharp="tip", flipped=False,
                winner_side="a", method="kill", turns=9, damage_a=40.0,
                damage_b=10.0, hits_a=3, hits_b=1, hp_a=70.0, hp_b=10.0)
    base.update(kw)
    return base


# ------------------------------------------------------------------ signatures
def test_identical_fights_share_a_signature():
    assert WB.fight_signature(row()) == WB.fight_signature(row())


@pytest.mark.parametrize("field,value", [
    ("weapon", "dagger"), ("arena", "ice"), ("sharp", "edge"),
    ("flipped", True), ("winner_side", "b"), ("method", "points"),
    ("turns", 10), ("damage_a", 41.0), ("damage_b", 11.0),
    ("hits_a", 4), ("hits_b", 2), ("hp_a", 71.0), ("hp_b", 11.0),
])
def test_any_outcome_difference_changes_the_signature(field, value):
    """The signature must be sensitive to everything that makes it a
    different fight — a too-loose key would merge genuinely distinct rows
    and throw away real samples."""
    assert WB.fight_signature(row()) != WB.fight_signature(row(**{field: value}))


def test_unique_rows_keeps_first_occurrence_order():
    rows = [row(flipped=False), row(flipped=True), row(flipped=False)]
    kept = WB.unique_rows(rows)
    assert len(kept) == 2 and kept[0]["flipped"] is False


# ------------------------------------------------------------------ aggregation
def test_summarize_counts_rows_and_distinct_fights_separately():
    rows = [row(flipped=f, arena=a) for a in ("normal", "ice") for f in (False, True)]
    duplicated = rows * 6                      # 4 fights, every one replayed 6x
    r = WB.summarize_by(duplicated, "weapon")[0]
    assert r["matches"] == 24
    assert r["unique_fights"] == 4
    assert r["duplicate_rows"] == 20


def test_win_rate_is_computed_on_distinct_fights_not_rows():
    """The whole point: duplicating a fight must not move the estimate or
    tighten the interval.

    Rows: one A win duplicated 9x, one B win once. Counting rows gives
    90% side-A; counting fights gives 50%, which is the truth for a
    two-fight sample.
    """
    a_win = row(flipped=False, winner_side="a")
    b_win = row(flipped=True, winner_side="b", damage_a=10.0, damage_b=40.0)
    rows = [a_win] * 9 + [b_win]

    r = WB.summarize_by(rows, "weapon")[0]
    assert r["side_a_win_rate_naive"] == pytest.approx(0.9)
    assert r["side_a_win_rate"] == pytest.approx(0.5)
    # Two observations cannot produce a tight interval, whatever the row count.
    assert r["ci_lo"] < 0.2 and r["ci_hi"] > 0.8


def test_interval_is_never_tighter_than_the_distinct_fight_count_allows():
    rows = [row(flipped=f) for f in (False, True)] * 6
    r = WB.summarize_by(rows, "weapon")[0]
    # 12 rows, 2 fights, both won by A -> Wilson on 2/2 is very wide.
    assert r["unique_fights"] == 2
    assert r["ci_lo"] < 0.35


# ---------------------------------------------------------------------- verdict
def test_verdict_flags_pseudo_replication():
    rows = [row(flipped=f) for f in (False, True)] * 8
    flags = WB.verdict(WB.summarize_by(rows, "weapon"))
    joined = " ".join(flags)
    assert "distinct fights" in joined
    assert "deterministic" in joined


def test_verdict_does_not_claim_a_bias_when_the_interval_contains_even():
    rows = ([row(flipped=False)] * 6 + [row(flipped=True)] * 6)
    flags = WB.verdict(WB.summarize_by(rows, "weapon"))
    assert not any(f.startswith("⚠") and "side bias" in f for f in flags), flags


# ------------------------------------------------- committed-data regression
@pytest.mark.skipif(not BALANCE_CSV.exists(), reason="balance CSV not present")
def test_committed_v1_sweep_is_pseudo_replicated_as_documented():
    """Pins the finding, so the number in the docs cannot drift silently."""
    rows = list(csv.DictReader(BALANCE_CSV.open()))
    assert len(rows) == 120

    by_weapon = {r["weapon"]: r for r in WB.summarize_by(rows, "weapon")}
    assert set(by_weapon) == {"sword", "dagger", "spear", "flail", "bow"}

    # Measured 2026-11-07: 15-23 of 24 rows per weapon are distinct fights.
    for weapon, r in by_weapon.items():
        assert r["matches"] == 24
        assert 14 <= r["unique_fights"] <= 24, (weapon, r["unique_fights"])

    flail = by_weapon["flail"]
    assert flail["unique_fights"] == 15
    assert flail["duplicate_rows"] == 9
    # And the reported rate is now a 15-fight estimate, not a 24-row one.
    assert flail["side_a_win_rate"] != pytest.approx(flail["side_a_win_rate_naive"])
