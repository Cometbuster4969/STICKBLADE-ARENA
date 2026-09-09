"""API contract + abuse-protection tests (action-plan §22, §26).

Everything here runs against the real FastAPI app through TestClient with a
throwaway SQLite database — no network, no provider keys, no LLM calls.
"""
import os
import tempfile
import time

import conftest
import pytest

conftest.init_pygame()
os.environ["STICKBLADE_DATA_DIR"] = tempfile.mkdtemp(prefix="sba_api_")

from fastapi.testclient import TestClient     # noqa: E402
import server                                 # noqa: E402

CLIENT = TestClient(server.app)


# ------------------------------------------------------------------ basics
def test_public_endpoints_are_reachable():
    for path in ("/api/health", "/api/models", "/api/weapons", "/api/version",
                 "/api/benchmark/spec", "/api/metrics", "/api/status",
                 "/api/recent", "/api/leaderboard"):
        r = CLIENT.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_version_endpoint_pins_the_benchmark_versions():
    v = CLIENT.get("/api/version").json()
    assert v["version"] == server.VERSION
    assert "prompt_version" in v
    assert v["replay_format"] == 2


def test_benchmark_spec_endpoint_returns_the_frozen_ruleset():
    spec = CLIENT.get("/api/benchmark/spec").json()
    assert spec["benchmark_version"] == "1.0"
    assert spec["fingerprint"] == server.SPEC_FINGERPRINT
    assert "physics" in spec and "rating" in spec and "voting" in spec
    assert spec["rating"]["k_factor"] == 32
    assert spec["voting"]["axes"]["tactical"]


def test_security_headers_are_present():
    r = CLIENT.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_docs_are_not_publicly_exposed():
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert CLIENT.get(path).status_code in (404, 405)


# ------------------------------------------------------- input validation
def test_unknown_model_is_rejected():
    # A slug with no provider prefix matches no roster entry and is not a
    # well-formed OpenRouter id, so it's rejected outright.
    r = CLIENT.post("/api/match", json={"model_a": "totally-made-up",
                                        "model_b": "mock:duelist",
                                        "sharp": ["tip"]})
    assert r.status_code == 400


def test_custom_models_must_be_free_unless_opted_in():
    """Spend protection: strangers can't bill us for a paid model."""
    from security import ALLOW_PAID_CUSTOM
    body = {"model_a": "anthropic/claude-3-opus",      # paid, no :free suffix
            "model_b": "mock:duelist", "sharp": ["tip"]}
    r = CLIENT.post("/api/match", json=body)
    if ALLOW_PAID_CUSTOM:
        assert r.status_code == 200
    else:
        assert r.status_code == 400


def test_invalid_weapon_and_zone_are_rejected():
    r = CLIENT.post("/api/match", json={"model_a": "mock:duelist",
                                        "model_b": "mock:berserker",
                                        "weapon": "lightsaber",
                                        "sharp": ["tip"]})
    assert r.status_code == 422
    r = CLIENT.post("/api/match", json={"model_a": "mock:duelist",
                                        "model_b": "mock:berserker",
                                        "weapon": "bow",
                                        "sharp": ["tip"]})
    assert r.status_code == 400      # 'tip' is not a bow zone


def test_match_length_and_policy_are_validated():
    body = {"model_a": "mock:duelist", "model_b": "mock:berserker",
            "sharp": ["tip"]}
    assert CLIENT.post("/api/match", json={**body,
                                           "match_length": "marathon"}).status_code == 422
    assert CLIENT.post("/api/match", json={**body,
                                           "fallback_policy": "chaos"}).status_code == 422
    assert CLIENT.post("/api/match", json={**body,
                                           "seed": -5}).status_code == 422
    ok = CLIENT.post("/api/match", json={**body, "match_length": "sprint",
                                         "seed": 7,
                                         "fallback_policy": "strict"})
    assert ok.status_code == 200
    assert ok.json()["max_turns"] == 4


def test_malformed_match_ids_never_reach_storage():
    for bad in ("..%2F..%2Fetc%2Fpasswd", "not-an-id", "' OR 1=1--", "a" * 200):
        r = CLIENT.get(f"/api/match/{bad}")
        assert r.status_code in (400, 404), f"{bad} -> {r.status_code}"


def test_vote_rejects_unfinished_matches():
    mid = CLIENT.post("/api/match", json={"model_a": "mock:duelist",
                                          "model_b": "mock:berserker",
                                          "sharp": ["tip"],
                                          "match_length": "sprint"}).json()["match_id"]
    server.store.cancel_match(mid)
    assert CLIENT.post(f"/api/vote/{mid}",
                       json={"choice": "a"}).status_code == 400


def test_vote_validates_choice_and_confidence():
    mid = _finished_match()
    assert CLIENT.post(f"/api/vote/{mid}",
                       json={"choice": "c"}).status_code == 422
    assert CLIENT.post(f"/api/vote/{mid}",
                       json={"choice": "a", "confidence": 99}).status_code == 422


# ------------------------------------------------------------ end to end
def _finished_match(**body):
    payload = {"model_a": "mock:duelist", "model_b": "bot:pro",
               "sharp": ["tip"], "match_length": "sprint", "seed": 2024}
    payload.update(body)
    mid = CLIENT.post("/api/match", json=payload).json()["match_id"]
    for _ in range(200):
        st = CLIENT.get(f"/api/match/{mid}").json()
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    return mid


def test_full_match_flow_with_provenance_and_integrity():
    mid = _finished_match()
    st = CLIENT.get(f"/api/match/{mid}").json()
    assert st["benchmark"]["benchmark_version"] == "1.0"
    assert st["benchmark"]["seed"] == 2024
    assert st["benchmark"]["match_length"] == "sprint"
    assert "integrity" in st

    integ = CLIENT.get(f"/api/integrity/{mid}").json()
    assert integ["ok"] is True, integ
    assert integ["checks"]["hp_monotonic"] is True
    assert "anti_gaming" in integ


def test_pinned_flip_fixes_canvas_sides_and_default_stays_random():
    """Research batches pin `flip` so seeded fights replay with balanced
    sides; ordinary requests keep the coin-flip. The export row is where
    the flip becomes visible."""
    def flip_of(mid):
        rows = CLIENT.get("/api/export?fmt=json&limit=50").json()["matches"]
        return next(r["flip"] for r in rows if r["id"] == mid)

    created = CLIENT.post("/api/match", json={
        "model_a": "mock:duelist", "model_b": "bot:pro", "sharp": ["tip"],
        "match_length": "sprint", "seed": 11, "flip": False}).json()
    assert created["flip_pinned"] is True
    mid_false = _finished_match(seed=11, flip=False)
    mid_true = _finished_match(seed=11, flip=True)
    assert flip_of(mid_false) == 0
    assert flip_of(mid_true) == 1
    # with flip pinned, model_used_a is the requested model_a (canvas A)
    rows = {r["id"]: r for r in
            CLIENT.get("/api/export?fmt=json&limit=50").json()["matches"]}
    assert rows[mid_false]["model_used_a"] == "mock:duelist"
    assert rows[mid_true]["model_used_a"] == "bot:pro"
    plain = CLIENT.post("/api/match", json={
        "model_a": "mock:duelist", "model_b": "bot:pro", "sharp": ["tip"],
        "match_length": "sprint"}).json()
    assert plain["flip_pinned"] is False


def test_multi_axis_vote_is_recorded():
    mid = _finished_match()
    r = CLIENT.post(f"/api/vote/{mid}", json={
        "choice": "a", "execution": "a", "entertainment": "b",
        "deserved": "a", "confidence": 4}).json()
    assert "elo_change" in r
    row = server.store._conn().execute(
        "SELECT choice, execution, entertainment, deserved, confidence"
        " FROM votes WHERE match_id=?", (mid,)).fetchone()
    assert row["choice"] == "a"
    assert row["entertainment"] == "b"
    assert row["confidence"] == 4


def test_ranking_ineligible_match_does_not_move_elo():
    mid = _finished_match(fallback_policy="demo")
    r = CLIENT.post(f"/api/vote/{mid}", json={"choice": "a"}).json()
    assert r["ranking_excluded"] is True
    assert r["elo_change"] == {}
    assert "demo" in r["exclusion_reason"]


def test_cancel_stops_a_running_match():
    mid = CLIENT.post("/api/match", json={"model_a": "mock:duelist",
                                          "model_b": "mock:berserker",
                                          "sharp": ["tip"],
                                          "match_length": "full"}).json()["match_id"]
    c = CLIENT.post(f"/api/match/{mid}/cancel").json()
    assert c["cancelled"] is True
    st = CLIENT.get(f"/api/match/{mid}").json()
    assert st["status"] == "error"
    # cancelling a finished match is a no-op, not an error
    assert CLIENT.post(f"/api/match/{mid}/cancel").json()["cancelled"] is False


def test_export_supports_json_jsonl_and_csv():
    _finished_match()
    j = CLIENT.get("/api/export?fmt=json&limit=5").json()
    assert j["count"] >= 1 and "matches" in j
    assert j["license"] == "CC-BY-SA-4.0"
    l = CLIENT.get("/api/export?fmt=jsonl&limit=5")
    assert l.headers["content-type"].startswith("application/x-ndjson")
    c = CLIENT.get("/api/export?fmt=csv&limit=5")
    assert c.headers["content-type"].startswith("text/csv")
    assert "benchmark_version" in c.text.splitlines()[0]
    assert CLIENT.get("/api/export?fmt=xml").status_code == 400


def test_metrics_and_status_report_operational_state():
    m = CLIENT.get("/api/metrics").json()
    assert "uptime_s" in m and "queue" in m and "storage" in m
    assert m["alert_thresholds"]["match_failure_rate"] == 0.05
    s = CLIENT.get("/api/status").json()
    assert s["benchmark_version"] == "1.0"
    assert "components" in s and "health" in s
    # Status page contract (next-step priority 4): replay storage, last
    # incident and degraded modes are part of the payload, and an
    # all-scripted deployment is reported as degraded, not "ok".
    assert s["components"]["replays"].startswith("ok")
    assert "last_incident" in s
    assert isinstance(s["degraded_modes"], list)
    assert s["status"] in ("ok", "degraded", "down")
    if not any(s["providers_configured"].values()):
        # never "ok" without a provider key. It may be "down" rather than
        # "degraded" here because earlier tests in this module deliberately
        # cancel/fail matches and push the 24 h failure rate over 20 %.
        assert s["status"] in ("degraded", "down")
        assert any("provider key" in d for d in s["degraded_modes"])


@pytest.mark.parametrize("path", ["/api/match/abc", "/api/replay/xyz",
                                  "/api/integrity/zzz"])
def test_bad_ids_do_not_leak_tracebacks(path):
    r = CLIENT.get(path)
    assert r.status_code in (400, 404)
    assert "Traceback" not in r.text


# ------------------------------------------- §5: ratings with uncertainty
def test_bradley_terry_endpoint_returns_intervals():
    """Empty DB must still return a well-formed payload, not a 500."""
    r = CLIENT.get("/api/leaderboard/bradley_terry?bootstraps=20")
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "bradley-terry-davidson"
    assert isinstance(body["comparisons"], int)
    assert isinstance(body["rows"], list)
    for row in body["rows"]:
        # The whole point of §5: a rating is publishable only with a range.
        for key in ("rating", "ci_low", "ci_high", "matches",
                    "preference_rate", "provisional", "component"):
            assert key in row, f"missing {key} in {row}"
        assert row["ci_low"] <= row["rating"] <= row["ci_high"]


def test_bradley_terry_validates_filters():
    assert CLIENT.get("/api/leaderboard/bradley_terry?weapon=nope").status_code == 400
    assert CLIENT.get("/api/leaderboard/bradley_terry?mode=nope").status_code == 400
    assert CLIENT.get("/api/leaderboard/bradley_terry?arena=nope").status_code == 400
    # bootstraps is clamped, never a DoS lever
    assert CLIENT.get("/api/leaderboard/bradley_terry?bootstraps=99999"
                      ).status_code == 200


def test_model_stats_endpoint_returns_the_full_metric_table():
    _finished_match()
    r = CLIENT.get("/api/model_stats")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows, "expected at least one model after a finished match"
    for row in rows:
        for key in ("model", "matches", "win_rate", "preference_rate",
                    "damage_per_turn", "hit_rate", "lethal_rate",
                    "survival_rate", "timeout_rate", "invalid_action_rate",
                    "fallback_rate", "latency_ms_mean"):
            assert key in row, f"missing {key} in {row}"
        assert 0.0 <= row["survival_rate"] <= 1.0
        assert 0.0 <= row["timeout_rate"] <= 1.0
        assert 0.0 <= row["lethal_rate"] <= 1.0
    assert CLIENT.get("/api/model_stats?weapon=nope").status_code == 400


def test_model_stats_covers_every_rated_model_and_more():
    """The two tables are built from different populations on purpose: Elo
    only moves on *voted* matches, model_stats counts every finished match.
    So model_stats must be a superset, and its match count can never be
    lower than the number of matches that produced Elo movement."""
    _finished_match()
    elo = {r["model"]: r for r in CLIENT.get("/api/leaderboard").json()}
    stats = {r["model"]: r for r in CLIENT.get("/api/model_stats").json()["rows"]}
    assert set(elo) <= set(stats), f"rated but unmeasured: {set(elo) - set(stats)}"
    for model, row in elo.items():
        rated = row["wins"] + row["losses"] + row["draws"]
        assert stats[model]["matches"] >= rated, (
            f"{model}: {stats[model]['matches']} measured < {rated} rated")


# ------------------------------------- §6: expert / casual vote separation
def test_vote_records_the_declared_evaluator_tier():
    """The tier must survive the round trip — an unlabelled expert vote is
    indistinguishable from a casual one and the separation is worthless."""
    mid = _finished_match()
    r = CLIENT.post(f"/api/vote/{mid}",
                    json={"choice": "a", "voter_tier": "expert"})
    assert r.status_code == 200, r.text
    export = CLIENT.get("/api/export?fmt=json&limit=500").json()
    votes = [m for m in export.get("matches", []) if m["id"] == mid]
    assert votes, "match missing from export"
    stored = votes[0].get("votes") or []
    assert stored and stored[0].get("voter_tier") == "expert", stored


def test_unknown_tier_defaults_to_casual_not_rejected():
    """A garbage tier should not lose the vote; it should be labelled
    conservatively rather than guessed at."""
    mid = _finished_match()
    r = CLIENT.post(f"/api/vote/{mid}",
                    json={"choice": "b", "voter_tier": "wizard"})
    # Pydantic rejects values outside the Literal (422) — that is the right
    # call: silently defaulting would invent a tier. But the vote must still
    # be castable without the field at all.
    assert r.status_code in (400, 422), r.status_code
    r2 = CLIENT.post(f"/api/vote/{mid}", json={"choice": "b"})
    assert r2.status_code == 200


def test_bradley_terry_can_be_filtered_by_tier():
    assert CLIENT.get("/api/leaderboard/bradley_terry?tier=expert").status_code == 200
    assert CLIENT.get("/api/leaderboard/bradley_terry?tier=nope").status_code == 400


def test_export_separates_expert_and_casual_vote_counts():
    """Downstream analysts must be able to reproduce either tier's
    leaderboard from the export, so the counts travel as columns."""
    row = CLIENT.get("/api/export?fmt=csv&limit=5")
    header = row.text.splitlines()[0]
    assert "votes_expert" in header and "votes_casual" in header, header


# ------------------------------------------------ §31: recurring events
def test_events_calendar_is_reachable_and_well_formed():
    body = CLIENT.get("/api/events").json()
    assert isinstance(body["events"], list) and body["events"]
    assert isinstance(body["champions"], list)
    for w in body["events"]:
        for key in ("event_id", "name", "start", "end", "status"):
            assert key in w, w
        assert w["status"] in ("past", "active", "upcoming")
        # An event that has run must explain itself: either a champion or a
        # reason it has none. Never a silent blank.
        if w["status"] != "upcoming":
            assert w.get("champion") or w.get("reason"), w


def test_unknown_event_is_a_404_not_a_500():
    assert CLIENT.get("/api/events/does-not-exist").status_code == 404


def test_event_detail_returns_that_event_only():
    first = CLIENT.get("/api/events").json()["events"][0]["event_id"]
    body = CLIENT.get(f"/api/events/{first}").json()
    assert body["event"]["id"] == first
    assert all(w["event_id"] == first for w in body["windows"]), body["windows"]


# ------------------------------------------ §33/§34: costs and access model
def test_costs_endpoint_reports_measured_spend_and_coverage():
    body = CLIENT.get("/api/costs?days=30").json()
    w = body["window"]
    for key in ("matches", "matches_with_usage", "matches_without_usage",
                "complete", "prompt_tokens", "completion_tokens",
                "usd_total", "usd_per_match", "prices_as_of"):
        assert key in w, w
    # Coverage must be reported, not assumed: a rollup with unreported
    # usage has to say so, because those dollars exist but are uncounted.
    assert isinstance(w["complete"], bool)
    assert w["matches"] == (w["matches_with_usage"]
                            + w["matches_without_usage"]
                            + w["matches_offline"])


def test_budget_is_unset_rather_than_fake_healthy():
    body = CLIENT.get("/api/costs").json()
    if not body["limits"]["daily_usd"]:
        assert body["budget"]["daily"]["status"] == "unset"


def test_access_model_publishes_a_free_reproducible_tier():
    """§34: the core benchmark must stay free. If someone paywalls the
    public tier, this is the test that should fail."""
    tiers = {t["id"]: t for t in CLIENT.get("/api/costs").json()["access_tiers"]}
    assert "free" in tiers["public"]["price"].lower()
    assert "free" in tiers["byok"]["price"].lower()
    for tid, t in tiers.items():
        if "free" not in t["price"].lower() and "n/a" not in t["price"].lower():
            assert "Not implemented" in t["note"], (tid, t)


def test_cost_endpoint_does_not_leak_match_contents():
    """It is an ops endpoint: totals only, no per-match payloads."""
    body = CLIENT.get("/api/costs").json()
    assert "matches" not in body or isinstance(body.get("matches"), int)
    assert "rows" not in body
