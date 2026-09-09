"""Data-quality labels (next-step priority 2).

The label must describe *who actually decided*, not who was requested. These
tests pin that rule to hand-built rows so a later refactor cannot quietly
turn a scripted stand-in into a "real-provider result".
"""
import os
import tempfile
import time

import conftest  # noqa: F401  (sys.path + SDL setup)
import pytest

import data_quality as DQ


def _row(pa="scripted", pb="scripted", ma="model/x", mb="model/y", flip=0,
         eligible=1, fallback=0, tok_a=0, tok_b=0, policy="operational",
         created=None, status="done", **extra):
    r = {"id": "m", "created": created or time.time(), "status": status,
         "model_a": ma, "model_b": mb, "flip": flip,
         "model_used_a": mb if flip else ma,
         "model_used_b": ma if flip else mb,
         "provider_used_a": pa, "provider_used_b": pb,
         "fallback_used": fallback, "ranking_eligible": eligible,
         "fallback_policy": policy, "benchmark_version": "1.0",
         "prompt_tokens_a": tok_a, "completion_tokens_a": 0,
         "prompt_tokens_b": tok_b, "completion_tokens_b": 0,
         "api_calls_a": 1 if tok_a else 0, "api_calls_b": 1 if tok_b else 0}
    r.update(extra)
    return r


# ------------------------------------------------------------ per match
def test_evidence_class_is_decided_by_provider_not_by_roster_id():
    # A requested LLM whose slot was served by a scripted stand-in is
    # scripted evidence — the roster id says "model/x", the decisions say
    # otherwise.
    assert DQ.evidence_class(_row("scripted", "scripted")) == "scripted_baseline"
    assert DQ.evidence_class(_row("openrouter", "scripted")) == "mixed_provider"
    assert DQ.evidence_class(_row("openrouter", "groq")) == "real_provider"


@pytest.mark.parametrize("p", ["", None, "scripted", "error", "none", "mock"])
def test_non_real_provider_strings(p):
    assert DQ.is_real_provider(p) is False


@pytest.mark.parametrize("p", ["openrouter", "groq", "openai", "google",
                               "Groq", " openrouter "])
def test_real_provider_strings(p):
    assert DQ.is_real_provider(p) is True


def test_side_view_respects_flip_bit():
    # flip=1 means model_a was rendered as canvas side B, so canvas-side-A
    # provenance belongs to model_b. Getting this wrong would attribute one
    # model's provider and tokens to its opponent.
    r = _row(pa="groq", pb="scripted", ma="llm/a", mb="bot:pro", flip=1,
             tok_a=120)
    a, b = DQ.side_view(r, "a"), DQ.side_view(r, "b")
    assert a["model"] == "bot:pro" and a["provider"] == "groq"
    assert b["model"] == "llm/a" and b["provider"] == "scripted"
    assert a["prompt_tokens"] == 120 and b["prompt_tokens"] == 0


def test_missing_tokens_only_counts_for_real_sides():
    real_no_tok = DQ.classify_match(_row("openrouter", "scripted"))
    assert real_no_tok["tokens_missing"] is True
    scripted = DQ.classify_match(_row("scripted", "scripted"))
    assert scripted["tokens_missing"] is False          # $0, not a gap
    real_tok = DQ.classify_match(_row("openrouter", "groq", tok_a=10, tok_b=9))
    assert real_tok["tokens_missing"] is False


def test_silent_fallback_flags_strict_ranked_fallback():
    ok = DQ.classify_match(_row("openrouter", "groq", fallback=1, eligible=0,
                                policy="strict"))
    assert ok["silent_fallback"] is False
    bad = DQ.classify_match(_row("openrouter", "groq", fallback=1, eligible=1,
                                 policy="strict"))
    assert bad["silent_fallback"] is True


# ------------------------------------------------------------ per model
def test_declared_baselines_are_reference_never_ranking_eligible():
    rows = [_row("scripted", "scripted", ma="bot:pro", mb="mock:duelist")
            for _ in range(50)]
    roll = DQ.rollup_models(rows)
    for m in ("bot:pro", "mock:duelist"):
        assert roll[m]["status"] == "reference_baseline"
        assert roll[m]["evidence"] == "scripted_baseline"
        assert roll[m]["matches"] == 50


def test_requested_llm_served_by_stand_in_is_scripted_evidence():
    rows = [_row("scripted", "scripted", ma="meta/llama", mb="bot:pro")
            for _ in range(20)]
    rec = DQ.rollup_models(rows)["meta/llama"]
    assert rec["evidence"] == "scripted_baseline"
    assert rec["status"] == "exploratory_only"
    assert rec["real_provider_matches"] == 0
    assert rec["scripted_matches"] == 20


def test_model_becomes_ranking_eligible_only_with_enough_real_ranked():
    rows = [_row("openrouter", "groq", ma="a/x", mb="b/y", tok_a=5, tok_b=5)
            for _ in range(DQ.MIN_REAL_RANKED - 1)]
    roll = DQ.rollup_models(rows)
    assert roll["a/x"]["status"] == "exploratory_only"
    assert roll["a/x"]["evidence"] == "real_provider"
    rows.append(_row("openrouter", "groq", ma="a/x", mb="b/y", tok_a=5, tok_b=5))
    roll = DQ.rollup_models(rows)
    assert roll["a/x"]["status"] == "ranking_eligible"
    assert roll["a/x"]["real_ranked_matches"] == DQ.MIN_REAL_RANKED


def test_ineligible_real_matches_do_not_count_toward_ranking():
    rows = [_row("openrouter", "groq", ma="a/x", mb="b/y", eligible=0,
                 policy="strict", fallback=1) for _ in range(30)]
    rec = DQ.rollup_models(rows)["a/x"]
    assert rec["real_provider_matches"] == 30
    assert rec["real_ranked_matches"] == 0
    assert rec["fallback_matches"] == 30
    assert rec["status"] == "exploratory_only"


def test_mixed_history_is_labelled_mixed():
    rows = ([_row("openrouter", "scripted", ma="a/x", mb="bot:pro")] * 5
            + [_row("scripted", "scripted", ma="a/x", mb="bot:pro")] * 5)
    rec = DQ.rollup_models(rows)["a/x"]
    assert rec["evidence"] == "mixed_provider"
    assert rec["own_side_real_matches"] == 5
    assert rec["token_missing_matches"] == 5   # real turns, no usage reported


def test_rollup_tracks_last_match_and_benchmark_versions():
    rows = [_row("scripted", "scripted", ma="bot:pro", mb="mock:duelist",
                 created=1000.0),
            _row("scripted", "scripted", ma="bot:pro", mb="mock:duelist",
                 created=2000.0, benchmark_version="1.1")]
    rec = DQ.rollup_models(rows)["bot:pro"]
    assert rec["first_match_at"] == 1000.0
    assert rec["last_match_at"] == 2000.0
    assert rec["benchmark_versions"] == ["1.0", "1.1"]


def test_unfinished_matches_are_ignored():
    rows = [_row("openrouter", "groq", status="error") for _ in range(5)]
    assert DQ.rollup_models(rows) == {}
    assert DQ.summary(rows)["matches"] == 0


def test_model_record_never_returns_none():
    rec = DQ.model_record({}, "never/played")
    assert rec["matches"] == 0
    assert rec["status"] == "exploratory_only"
    assert rec["evidence"] == "scripted_baseline"


# --------------------------------------------------------------- summary
def test_summary_levels():
    scripted = [_row("scripted", "scripted") for _ in range(100)]
    s = DQ.summary(scripted)
    assert s["evidence_level"] == "scripted_only"
    assert s["infrastructure_validated"] is True
    assert s["model_conclusions_validated"] is False
    assert s["token_coverage"] is None                 # nothing billable

    few_real = scripted + [_row("openrouter", "groq", tok_a=1, tok_b=1)
                           for _ in range(DQ.MIN_REAL_FOR_BOARD - 1)]
    s = DQ.summary(few_real)
    assert s["evidence_level"] == "insufficient_real"
    assert s["real_provider_matches"] == DQ.MIN_REAL_FOR_BOARD - 1
    assert s["token_coverage"] == 1.0

    enough = few_real + [_row("openrouter", "groq", tok_a=1, tok_b=1)]
    s = DQ.summary(enough)
    assert s["evidence_level"] == "real"
    assert s["model_conclusions_validated"] is True


def test_summary_token_coverage_excludes_scripted_and_reports_gaps():
    rows = ([_row("scripted", "scripted")] * 10
            + [_row("openrouter", "groq", tok_a=1, tok_b=1)] * 3
            + [_row("openrouter", "groq")] * 1)          # real, no usage
    s = DQ.summary(rows)
    assert s["token_reported_matches"] == 3
    assert s["token_missing_matches"] == 1
    assert s["token_coverage"] == 0.75


# --------------------------------------------------------------- endpoint
@pytest.fixture(scope="module")
def client():
    # Same pattern as test_api_schema.py: one server module per pytest
    # process. If another test module imported it first the env var is
    # ignored and the throwaway database is shared — which is fine, every
    # assertion below is about the offline match this fixture creates.
    conftest.init_pygame()
    os.environ.setdefault("STICKBLADE_DATA_DIR",
                          tempfile.mkdtemp(prefix="sba_dq_"))
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    mid = c.post("/api/match", json={
        "model_a": "mock:duelist", "model_b": "bot:pro", "sharp": ["tip"],
        "match_length": "sprint", "seed": 11}).json()["match_id"]
    for _ in range(200):
        st = c.get(f"/api/match/{mid}").json()
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    c.post(f"/api/vote/{mid}", json={"choice": "a"})
    return c


def test_endpoint_reports_scripted_only_for_offline_matches(client):
    d = client.get("/api/data_quality").json()
    assert d["summary"]["evidence_level"] == "scripted_only"
    assert d["summary"]["matches"] >= 1
    assert d["summary"]["silent_fallback_matches"] == 0
    assert d["summary"]["unidentified_matches"] == 0
    models = {m["model"]: m for m in d["models"]}
    assert models["mock:duelist"]["status"] == "reference_baseline"
    assert models["bot:pro"]["evidence"] == "scripted_baseline"
    assert "evidence" in d["labels"] and "status" in d["labels"]


def test_endpoint_validates_filters(client):
    assert client.get("/api/data_quality?weapon=banana").status_code == 400
    assert client.get("/api/data_quality?arena=moon").status_code == 400
    assert client.get("/api/data_quality?weapon=sword&arena=normal").status_code == 200


def test_every_ranking_row_carries_a_data_quality_label(client):
    lb = client.get("/api/leaderboard").json()
    assert lb, "expected at least one voted row"
    for r in lb:
        dq = r["data_quality"]
        assert dq["evidence"] in DQ.EVIDENCE_LABELS
        assert dq["status"] in DQ.STATUS_LABELS
        assert dq["last_match_at"] is not None
        assert dq["benchmark_versions"] == ["1.0"]
    for r in client.get("/api/leaderboard/objective").json():
        assert r["data_quality"]["evidence"] == "scripted_baseline"
    bt = client.get("/api/leaderboard/bradley_terry?bootstraps=5").json()
    assert bt["data_quality"]["evidence_level"] == "scripted_only"
    for r in bt["rows"]:
        assert r["data_quality"]["status"] == "reference_baseline"
    ms = client.get("/api/model_stats").json()
    assert ms["data_quality"]["evidence_level"] == "scripted_only"
    assert all("data_quality" in r for r in ms["rows"])


def test_export_carries_evidence_per_row_and_summary(client):
    j = client.get("/api/export?fmt=json&limit=10").json()
    assert j["data_quality"]["evidence_level"] == "scripted_only"
    assert all(m["evidence"] == "scripted_baseline" for m in j["matches"])
    csv_head = client.get("/api/export?fmt=csv&limit=10").text.splitlines()[0]
    assert csv_head.split(",")[-1] == "evidence"
    line = client.get("/api/export?fmt=jsonl&limit=1").text.splitlines()[0]
    assert '"evidence":"scripted_baseline"' in line


def test_status_exposes_dataset_evidence_level(client):
    s = client.get("/api/status").json()
    assert s["data_quality"]["evidence_level"] == "scripted_only"
    assert "note" in s["data_quality"]
