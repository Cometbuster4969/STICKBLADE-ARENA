"""Cost accounting and budgets (action-plan §33, §34).

The failure mode here is a budget that lies: unreported usage counted as
free, stale prices baked into code, or an unset limit reported as healthy.
These tests pin all three.
"""
import os
import time

import conftest                                            # noqa: F401
import pytest

import costs


def test_price_lookup_is_specific_before_generic():
    specific = costs.price_for("openai/gpt-4o-mini")
    fallback = costs.price_for("some/unknown-model-xyz")
    assert specific == (0.15, 0.60)
    # The unknown-model fallback is deliberately the most expensive row:
    # when we cannot price a model we over-estimate, not under-estimate.
    assert fallback[0] > specific[0] and fallback[1] > specific[1]
    # Longest prefix wins: gpt-oss-20b is cheaper than the openai/ default
    assert costs.price_for("openai/gpt-oss-20b") == (0.05, 0.20)


def test_free_suffix_does_not_change_the_price():
    """`:free` is an OpenRouter billing marker, not a different model."""
    plain = costs.price_for("meta-llama/llama-3.3-70b-instruct")
    assert costs.price_for("meta-llama/llama-3.3-70b-instruct:free") == plain


def test_prices_are_overridable(monkeypatch):
    monkeypatch.setenv("STICKBLADE_PRICES_JSON",
                       '{"test/model": [1.0, 2.0], "": [9.0, 9.0]}')
    assert costs.price_for("test/model") == (1.0, 2.0)
    assert costs.price_for("anything/else") == (9.0, 9.0)


def test_malformed_override_falls_back_to_the_builtin_table(monkeypatch):
    monkeypatch.setenv("STICKBLADE_PRICES_JSON", "{not json")
    assert costs.price_for("openai/gpt-4o-mini")[0] == 0.15


def test_two_models_split_the_cost():
    # 1M prompt + 1M completion, one side gpt-4o-mini (0.15/0.60), other
    # deepseek (0.25/0.85) -> average of the two halves.
    got = costs.usd(1_000_000, 1_000_000, "openai/gpt-4o-mini", "deepseek/x")
    want = (0.15 + 0.60 + 0.25 + 0.85) / 2
    assert abs(got - want) < 1e-9, (got, want)


def test_zero_tokens_cost_nothing():
    assert costs.usd(0, 0, "openai/gpt-4o-mini") == 0.0


def test_rollup_counts_unreported_usage_as_incomplete_not_free():
    """A billable match whose provider reported nothing must mark the
    rollup incomplete, so the endpoint can say 'this is a lower bound'."""
    now = time.time()
    rows = [
        {"created": now - 60, "prompt_tokens_a": 1000,
         "completion_tokens_a": 100, "prompt_tokens_b": 1000,
         "completion_tokens_b": 100, "api_calls_a": 1, "api_calls_b": 1,
         "model_used_a": "openai/gpt-4o-mini",
         "model_used_b": "openai/gpt-4o-mini"},
        # provider reported nothing but the match was NOT scripted
        {"created": now - 60, "provider_used_a": "openrouter",
         "provider_used_b": "openrouter"},
    ]
    out = costs.rollup(rows, days=30, now=now)
    assert out["matches_with_usage"] == 1
    assert out["matches_without_usage"] == 1
    assert out["complete"] is False


def test_scripted_matches_cost_nothing_and_are_not_unreported():
    """Mock-vs-mock matches genuinely cost $0. Counting them as 'unreported'
    would permanently mark the rollup incomplete for no reason."""
    now = time.time()
    rows = [{"created": now - 60, "provider_used_a": "scripted",
             "provider_used_b": "scripted"}]
    out = costs.rollup(rows, days=30, now=now)
    assert out["matches_without_usage"] == 0
    assert out["matches_offline"] == 1
    assert out["complete"] is True
    assert out["usd_total"] == 0.0


def test_rollup_respects_the_window():
    now = time.time()
    rows = [
        {"created": now - 3600, "prompt_tokens_a": 1_000_000,
         "api_calls_a": 1, "model_used_a": "openai/gpt-4o-mini"},
        {"created": now - 90 * 86400, "prompt_tokens_a": 1_000_000,
         "api_calls_a": 1, "model_used_a": "openai/gpt-4o-mini"},
    ]
    assert costs.rollup(rows, days=30, now=now)["matches"] == 1
    assert costs.rollup(rows, days=365, now=now)["matches"] == 2


def test_per_match_cost_is_none_when_nothing_was_billed():
    assert costs.rollup([], days=30)["usd_per_match"] is None


def test_unset_budget_is_reported_as_unset_not_ok(monkeypatch):
    monkeypatch.delenv("BUDGET_DAILY_USD", raising=False)
    monkeypatch.delenv("BUDGET_MONTHLY_USD", raising=False)
    st = costs.budget_state(5.0, 50.0)
    assert st["daily"]["status"] == "unset"
    assert st["monthly"]["status"] == "unset"


@pytest.mark.parametrize("spent,expected", [
    (0.5, "ok"), (8.5, "warn"), (15.0, "over"),
])
def test_budget_status_thresholds(monkeypatch, spent, expected):
    monkeypatch.setenv("BUDGET_DAILY_USD", "10")
    monkeypatch.setenv("BUDGET_MONTHLY_USD", "100")
    st = costs.budget_state(spent, spent)
    assert st["daily"]["status"] == expected, st


def test_access_model_keeps_the_benchmark_free():
    """§34: the reproducible tier must never be paywalled. If someone adds
    a paid 'public' tier, this is the test that should fail."""
    public = next(t for t in costs.ACCESS_TIERS if t["id"] == "public")
    assert "free" in public["price"].lower()
    assert "free" in next(t for t in costs.ACCESS_TIERS
                          if t["id"] == "byok")["price"].lower()
    assert "free" in next(t for t in costs.ACCESS_TIERS
                          if t["id"] == "research")["price"].lower()
    paid = [t["id"] for t in costs.ACCESS_TIERS if "free" not in t["price"].lower()]
    # Paid tiers exist only for volume/hosting, and are marked unimplemented.
    for t in costs.ACCESS_TIERS:
        if t["id"] in paid:
            assert "Not implemented" in t["note"], t


def test_garbage_rows_do_not_raise():
    rows = [{"created": "not-a-number"},
            {"created": None},
            {"created": time.time(), "prompt_tokens_a": "lots"},
            {}]
    out = costs.rollup(rows, days=7)
    assert out["usd_total"] >= 0
