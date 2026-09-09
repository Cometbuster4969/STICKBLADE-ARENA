"""tools/run_calibration_batch.py — plan design + acceptance audit.

The audit is what turns a batch of matches into a claim ("100 % of research
matches identify provider and model", "no silent fallback in strict mode"),
so its logic is pinned here on hand-built rows. The plan tests pin the
experimental design: every unordered pair, every cell, seeds unique, sides
balanced per model. One slow-ish test runs a 2-match local batch end to end
and checks the files the runner promises.
"""
import json
import os
import pathlib

import pytest

import run_calibration_batch as RCB


MODELS4 = ["bot:pro", "mock:duelist", "bot:greedy", "bot:distance"]


# ------------------------------------------------------------------ plan
def test_plan_covers_every_pair_and_cell_with_unique_seeds():
    plan = RCB.build_plan(MODELS4, n_per_pair=16)
    ms = plan["matches"]
    pairs = {m["pair_id"] for m in ms}
    assert len(pairs) == 6                       # C(4,2)
    cells = {m["cell_id"] for m in ms}
    assert len(cells) == 8                       # 2 weapons × 2 arenas × 2 modes
    assert len(ms) == 6 * 16
    seeds = [m["seed"] for m in ms]
    assert len(set(seeds)) == len(seeds)
    # every (pair, cell) combination gets the same number of matches
    from collections import Counter
    per = Counter((m["pair_id"], m["cell_id"]) for m in ms)
    assert set(per.values()) == {2}


def test_plan_balances_sides_per_model_when_n_is_a_multiple_of_cells():
    plan = RCB.build_plan(MODELS4, n_per_pair=16)
    left = {m: 0 for m in MODELS4}
    right = {m: 0 for m in MODELS4}
    for m in plan["matches"]:
        left[m["left"]] += 1
        right[m["right"]] += 1
    for m in MODELS4:
        assert left[m] == right[m], (m, left[m], right[m])
    # and within a single (pair, cell) the two matches alternate sides
    seen = {}
    for m in plan["matches"]:
        seen.setdefault((m["pair_id"], m["cell_id"]), set()).add(m["flip"])
    assert all(v == {False, True} for v in seen.values())


def test_plan_is_deterministic_for_a_fixed_run_id_and_seed():
    a = RCB.build_plan(MODELS4, n_per_pair=16, run_id="fixed")
    b = RCB.build_plan(MODELS4, n_per_pair=16, run_id="fixed")
    assert a["matches"] == b["matches"]
    ha = {k: v for k, v in a["header"].items() if k != "created"}
    hb = {k: v for k, v in b["header"].items() if k != "created"}
    assert ha == hb


def test_plan_header_records_the_design_knobs():
    plan = RCB.build_plan(MODELS4, n_per_pair=4, match_length="sprint",
                          fallback_policy="strict", base_seed=123)
    h = plan["header"]
    assert h["match_length"] == "sprint"
    assert h["fallback_policy"] == "strict"
    assert h["base_seed"] == 123
    assert h["n_per_pair"] == 4
    assert h["models"] == MODELS4
    assert h["sharps"] == {"sword": "tip", "bow": "arrowhead"}


def test_plan_rejects_fewer_than_two_models():
    with pytest.raises(ValueError):
        RCB.build_plan(["bot:pro"], n_per_pair=2)


def test_provider_of_maps_roster_ids():
    assert RCB.provider_of("bot:pro") == "scripted"
    assert RCB.provider_of("mock:duelist") == "scripted"
    assert RCB.provider_of("groq:llama-3.1-8b-instant") == "groq"
    assert RCB.provider_of("meta-llama/llama-3.3-70b-instruct:free") == "openrouter"


# ----------------------------------------------------------------- rows
def _row(**kw):
    base = {
        "idx": kw.pop("idx", 0), "pair_id": "m1|m2", "cell_id": "sword/normal/macro",
        "status": "done", "fallback_policy": "strict",
        "model_requested_a": "m1", "model_requested_b": "m2",
        "model_used_a": "m1", "model_used_b": "m2",
        "provider_a": "openrouter", "provider_b": "groq",
        "prompt_tokens_a": 100, "completion_tokens_a": 10,
        "prompt_tokens_b": 100, "completion_tokens_b": 10,
        "latency_ms_a": 800.0, "latency_ms_b": 900.0,
        "fallback_status": "none", "eligibility_status": "ranking_eligible",
        "evidence": "real_provider", "winner_model": "m1",
    }
    base.update(kw)
    return base


def test_unflip_swaps_sided_columns_and_winner_only_when_flipped():
    row = {"flip": 1, "model_used_a": "X", "model_used_b": "Y",
           "provider_used_a": "groq", "provider_used_b": "scripted",
           "prompt_tokens_a": 5, "prompt_tokens_b": 0,
           "winner_side": "a", "model_a": "req1", "model_b": "req2"}
    out = RCB._unflip(row)
    assert out["model_used_a"] == "Y" and out["model_used_b"] == "X"
    assert out["provider_used_a"] == "scripted"
    assert out["prompt_tokens_a"] == 0 and out["prompt_tokens_b"] == 5
    assert out["winner_side"] == "b"
    # request-order columns untouched
    assert out["model_a"] == "req1" and out["model_b"] == "req2"
    row["flip"] = 0
    assert RCB._unflip(row)["model_used_a"] == "X"
    row["winner_side"] = "draw"
    row["flip"] = 1
    assert RCB._unflip(row)["winner_side"] == "draw"


def test_fallback_and_eligibility_status_helpers():
    assert RCB._fallback_status(0, 0, "strict") == "none"
    assert RCB._fallback_status(1, 0, "strict") == "excluded"
    assert RCB._fallback_status(0, 2, "operational") == "used"
    assert RCB._eligibility_status(True, "done") == "ranking_eligible"
    assert RCB._eligibility_status(False, "done") == "excluded"
    assert RCB._eligibility_status(True, "error") == "failed"


def test_finish_row_on_a_failed_match_keeps_it_but_marks_it_failed():
    plan = RCB.build_plan(["m1", "m2"], n_per_pair=2)
    row = RCB._base_row(plan, plan["matches"][0], "test")
    out = RCB._finish_row(row, {}, {}, "error", None, None, None, None,
                          None, 1.0, error="boom")
    assert out["status"] == "error"
    assert out["eligibility_status"] == "failed"
    assert out["evidence"] is None            # unknown, NOT "scripted"
    assert out["winner_model"] is None
    assert out["voter_tier"] is None
    assert set(out) == set(RCB.RESULT_FIELDS)


def test_finish_row_strict_fallback_is_excluded_not_ranked():
    plan = RCB.build_plan(["m1", "m2"], n_per_pair=2)
    row = RCB._base_row(plan, plan["matches"][0], "test")
    prov = {"provider_used_a": "openrouter", "provider_used_b": "scripted",
            "model_used_a": "m1", "model_used_b": "mock:duelist",
            "ranking_eligible": False}
    out = RCB._finish_row(row, prov, {"fallback_turns_b": 3}, "done",
                          "a", "kill", 5, 100.0, 20.0, 30.0)
    assert out["fallback_status"] == "excluded"
    assert out["eligibility_status"] == "excluded"
    assert out["evidence"] == "mixed_provider"
    assert out["winner_model"] == row["model_requested_a"]


# ---------------------------------------------------------------- audit
def test_audit_accepts_a_clean_real_provider_batch():
    rows = [_row(idx=i) for i in range(6)]
    a = RCB.audit(rows)
    assert a["accepted"] is True
    assert all(c["pass"] for c in a["checks"].values())
    assert a["token_coverage"] == 1.0
    assert a["latency_ms"]["p50"] is not None
    assert a["by_pair"]["m1|m2"]["n"] == 6
    assert a["by_pair"]["m1|m2"]["a_wins"] == 6


def test_audit_rejects_scripted_only_batches_on_exactly_one_check():
    rows = [_row(idx=i, provider_a="scripted", provider_b="scripted",
                 prompt_tokens_a=0, completion_tokens_a=0,
                 prompt_tokens_b=0, completion_tokens_b=0,
                 evidence="scripted_baseline") for i in range(4)]
    a = RCB.audit(rows)
    assert a["accepted"] is False
    failed = [k for k, c in a["checks"].items() if not c["pass"]]
    assert failed == ["real_provider_evidence_present"]
    assert a["token_coverage"] is None          # reported as n/a, not 0 %


def test_audit_flags_silent_fallback_in_strict_mode():
    rows = [_row(idx=0),
            _row(idx=1, fallback_status="excluded",
                 eligibility_status="ranking_eligible")]   # the bug
    a = RCB.audit(rows)
    assert a["checks"]["no_silent_fallback_in_strict_mode"]["pass"] is False
    assert "idx [1]" in a["checks"]["no_silent_fallback_in_strict_mode"]["detail"]
    # properly excluded fallback is fine
    rows[1]["eligibility_status"] = "excluded"
    assert RCB.audit(rows)["checks"]["no_silent_fallback_in_strict_mode"]["pass"]


def test_audit_flags_missing_provider_identity_and_token_gaps():
    rows = [_row(idx=0), _row(idx=1, provider_b=""),
            _row(idx=2, prompt_tokens_a=0, completion_tokens_a=0)]
    a = RCB.audit(rows)
    c = a["checks"]
    assert c["all_matches_identify_provider_and_model"]["pass"] is False
    assert c["all_matches_identify_provider_and_model"]["detail"] == "2/3"
    # 5 real sides (idx1 has only one), 4 with tokens → 80 % < 95 %
    assert c["token_coverage_at_least_95pct_or_reported"]["pass"] is False
    assert a["token_coverage"] == 0.8
    assert a["token_missing_sides"] == 1


def test_audit_keeps_failed_matches_out_of_the_ranked_count():
    rows = [_row(idx=0), _row(idx=1, status="error", eligibility_status="failed",
                              evidence=None, winner_model=None)]
    a = RCB.audit(rows)
    assert a["matches"] == 2 and a["completed"] == 1 and a["failed"] == 1
    assert a["checks"]["failed_matches_retained_not_ranked"]["pass"]
    assert a["by_pair"]["m1|m2"]["n"] == 1
    # a failed row mislabelled as ranked is caught
    rows[1]["eligibility_status"] = "ranking_eligible"
    assert not RCB.audit(rows)["checks"]["failed_matches_retained_not_ranked"]["pass"]


def test_render_audit_is_markdown_with_the_pipeline_caveat():
    a = RCB.audit([_row(idx=0)])
    md = RCB.render_audit(a, header={"run_id": "t", "models": ["m1", "m2"],
                                     "n_per_pair": 1, "cells": ["c"],
                                     "match_length": "sprint",
                                     "fallback_policy": "strict",
                                     "base_seed": 1})
    assert md.startswith("# Calibration batch")
    assert "**Overall: ACCEPTED**" in md
    assert "says nothing about which model is better" in md
    assert "Token coverage:** 100.0%" in md


# ------------------------------------------------------- end-to-end (local)
def test_local_run_writes_plan_results_csv_and_audit(tmp_path):
    plan = RCB.build_plan(["bot:pro", "mock:duelist"], n_per_pair=2,
                          weapons=("sword",), arenas=("normal",),
                          modes=("macro",), match_length="sprint",
                          run_id="t-local")
    out = tmp_path / "batch"
    RCB.run_local(plan, out, verbose=False)
    rows = RCB._load_jsonl(out / "results.jsonl")
    assert len(rows) == 2
    assert {r["flip"] for r in rows} == {False, True}
    for r in rows:
        assert r["status"] == "done"
        assert r["provider_a"] == "scripted" and r["provider_b"] == "scripted"
        assert r["model_used_a"] in ("bot:pro", "mock:duelist")
        assert r["evidence"] == "scripted_baseline"
        assert r["eligibility_status"] in ("ranking_eligible", "excluded")
        assert r["benchmark_version"] == "1.0"
        assert r["prompt_version"] == 2
        assert r["spec_fingerprint"]
        assert r["seed"] is not None
    # rerunning resumes: nothing re-executed, file unchanged
    before = (out / "results.jsonl").read_text()
    RCB.run_local(plan, out, verbose=False)
    assert (out / "results.jsonl").read_text() == before
    audit_json = json.loads((out / "audit.json").read_text())
    assert audit_json["accepted"] is False
    assert (out / "audit.md").exists()
    assert (out / "plan.json").exists()
    csv_head = (out / "results.csv").read_text().splitlines()[0].split(",")
    assert csv_head == RCB.RESULT_FIELDS
