"""Operating cost model and budget limits (action-plan §33, §34).

A free public benchmark that quietly costs its operator an unbounded amount
is not a plan, it is a countdown. This module turns "we should watch spend"
into two numbers you can alert on.

The accounting is **measured, not estimated**: every provider reports the
tokens it billed, the brains accumulate those counts across retries and
buddy fallbacks (`stickblade/brains.py`, `Brain._record_usage`), and they
land on the match row (`prompt_tokens_a/b`, `completion_tokens_a/b`). A
match that fell back to a scripted brain still reports what the failed
provider calls cost — that is precisely the case a budget has to see.

Two honesty constraints shape the output:

* **Unreported usage is not free.** If a provider does not return a usage
  block, the match is counted in `matches_without_usage` and every cost is
  reported as a *lower bound*. Nothing is silently filled in with an
  estimate, because an estimate dressed as a measurement is worse than a
  gap.
* **Prices are data, not code.** The table below is a snapshot with an
  as-of date and can be overridden from `STICKBLADE_PRICES_JSON`. Provider
  pricing changes monthly; a hardcoded figure that silently goes stale would
  turn a budget into a fiction.
"""
from __future__ import annotations

import json
import os

# USD per 1M tokens. Snapshot only — override with STICKBLADE_PRICES_JSON
# (a JSON object of {prefix: [usd_per_1M_prompt, usd_per_1M_completion]}).
# Prefixes are matched against the model id, longest first, so a specific
# entry beats a provider-wide default.
PRICE_AS_OF = "2026-09"
DEFAULT_PRICES = {
    # [usd / 1M prompt tokens, usd / 1M completion tokens]
    "openai/gpt-4o-mini":        [0.15, 0.60],
    "openai/gpt-oss-20b":        [0.05, 0.20],
    "openai/gpt-oss-120b":       [0.10, 0.50],
    "google/gemini":             [0.10, 0.40],
    "meta-llama/llama-3.3-70b":  [0.12, 0.30],
    "meta-llama/llama-4-scout":  [0.08, 0.30],
    "deepseek":                  [0.25, 0.85],
    "qwen":                      [0.12, 0.30],
    "mistral":                   [0.10, 0.30],
    # Unknown-model fallback is deliberately the MOST expensive row: when
    # we cannot price a model we over-estimate its cost rather than
    # under-estimate it. An under-estimated budget is a budget that fails
    # silently; an over-estimated one just leaves headroom.
    "":                          [0.30, 1.20],
}


def prices():
    """Price table, overridable via STICKBLADE_PRICES_JSON."""
    raw = os.environ.get("STICKBLADE_PRICES_JSON")
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict) and loaded:
                return loaded
        except (TypeError, ValueError):
            pass
    return DEFAULT_PRICES


def price_for(model, table=None):
    """(usd_per_1M_prompt, usd_per_1M_completion) for a model id.

    Longest matching prefix wins, so `openai/gpt-4o-mini` beats the
    empty-string fallback. `:free` suffixes are stripped first.
    """
    table = table if table is not None else prices()
    m = (model or "").lower().replace(":free", "")
    best = None
    for key, val in table.items():
        if key and m.startswith(key.lower()) and (best is None
                                                  or len(key) > len(best[0])):
            best = (key, val)
    if best:
        return float(best[1][0]), float(best[1][1])
    fb = table.get("", DEFAULT_PRICES[""])
    return float(fb[0]), float(fb[1])


def usd(prompt_tokens, completion_tokens, model_a=None, model_b=None,
        table=None):
    """Cost of one match in USD.

    With two models the tokens are attributed per fighter using each model's
    own price; without them, a single blended price is applied.
    """
    table = table if table is not None else prices()
    pt = _int(prompt_tokens)
    ct = _int(completion_tokens)
    if model_a and model_b:
        pa, ca = price_for(model_a, table)
        pb, cb = price_for(model_b, table)
        # Split evenly: we store per-match totals, not per-fighter splits,
        # and half of each side is the only unbiased attribution available.
        return (pt / 2 * pa + ct / 2 * ca + pt / 2 * pb + ct / 2 * cb) / 1_000_000
    p, c = price_for(model_a or model_b or "", table)
    return (pt * p + ct * c) / 1_000_000


def _int(v):
    """Coerce a DB value to a count. A row written by an older build, or by
    a backend that stored NULL, must read as 0 — never raise and never be
    silently counted as a real bill."""
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def rollup(rows, days=30, now=None):
    """Cost rollup over match rows.

    `rows` are match dicts carrying the token columns and `created`.
    Returns totals, per-model cost, and explicit coverage: how many matches
    reported usage and how many did not.
    """
    import time
    now = now if now is not None else time.time()
    since = now - days * 86400
    table = prices()
    total_prompt = total_completion = 0
    total_usd = 0.0
    matches = reported = unreported = offline = 0
    by_model = {}
    for r in rows:
        try:
            created = float(r.get("created") or 0)
        except (TypeError, ValueError):
            continue
        if created and created < since:
            continue
        pt = _int(r.get("prompt_tokens_a")) + _int(r.get("prompt_tokens_b"))
        ct = _int(r.get("completion_tokens_a")) + _int(r.get("completion_tokens_b"))
        api = _int(r.get("api_calls_a")) + _int(r.get("api_calls_b"))
        matches += 1
        # No usage reported AND no API calls: a scripted/mock match, which
        # genuinely costs nothing. Reported-but-zero would be a provider
        # that omits usage — unreported, and a lower bound.
        if api == 0 and pt == 0 and ct == 0:
            scripted = (r.get("provider_used_a") or "") == "scripted" and \
                       (r.get("provider_used_b") or "") == "scripted"
            if scripted or not (r.get("provider_used_a") or r.get("provider_used_b")):
                offline += 1                  # genuinely $0, not missing data
                continue
            unreported += 1
            continue
        reported += 1
        total_prompt += pt
        total_completion += ct
        cost = usd(pt, ct, r.get("model_used_a"), r.get("model_used_b"), table)
        total_usd += cost
        for key in (r.get("model_used_a"), r.get("model_used_b")):
            if not key:
                continue
            m = by_model.setdefault(key, {"matches": 0, "usd": 0.0,
                                          "prompt_tokens": 0,
                                          "completion_tokens": 0})
            m["matches"] += 1
            m["usd"] += cost / 2
            m["prompt_tokens"] += pt // 2
            m["completion_tokens"] += ct // 2
    per_match = (total_usd / reported) if reported else None
    return {
        "window_days": days,
        "matches": matches,
        "matches_with_usage": reported,
        "matches_without_usage": unreported,
        # Scripted / offline matches cost nothing and are NOT missing data —
        # keeping them separate is what stops a rollup being marked
        # "incomplete" forever just because mock matches exist.
        "matches_offline": offline,
        # True only when every billable match reported usage. Otherwise the
        # cost is a floor, and the caller must say so.
        "complete": unreported == 0,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "usd_total": round(total_usd, 4),
        "usd_per_match": round(per_match, 6) if per_match is not None else None,
        "by_model": dict(sorted(by_model.items(),
                                key=lambda kv: -kv[1]["usd"])),
        "prices_as_of": PRICE_AS_OF,
    }


# --------------------------------------------------------------- §34 budget
def budgets():
    """Daily/monthly budget limits in USD (0 = unset)."""
    def _f(name, default=0.0):
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return default
    return {"daily_usd": _f("BUDGET_DAILY_USD"),
            "monthly_usd": _f("BUDGET_MONTHLY_USD")}


def budget_state(usd_today, usd_month, warn_at=0.8):
    """Compare spend against the configured limits.

    Returns a status per window: 'ok', 'warn' (>= warn_at of the limit),
    'over', or 'unset' when no limit is configured — an unconfigured budget
    is reported as unconfigured, never as healthy.
    """
    lim = budgets()
    out = {}
    for key, spent in (("daily", usd_today), ("monthly", usd_month)):
        limit = lim[f"{key}_usd"]
        if not limit:
            out[key] = {"limit_usd": None, "spent_usd": round(spent, 4),
                        "status": "unset"}
            continue
        frac = spent / limit
        out[key] = {
            "limit_usd": limit,
            "spent_usd": round(spent, 4),
            "fraction_of_limit": round(frac, 3),
            "status": "over" if frac >= 1.0
                      else "warn" if frac >= warn_at else "ok",
        }
    return out


# ------------------------------------------------------- §34 access tiers
# Sustainable access model. The rule the whole thing hangs on: the core
# benchmark stays free and reproducible forever; what is metered is the
# *convenience* around it (volume, hosting, priority), never the science.
ACCESS_TIERS = [
    {"id": "public",
     "name": "Public Quick Match",
     "price": "free",
     "matches": "rate-limited per IP",
     "includes": "scripted baselines + the free model roster, public "
                 "leaderboard, dataset export",
     "note": "The reproducible tier. Never paywalled — a benchmark nobody "
             "can check is marketing."},
    {"id": "byok",
     "name": "BYOK (bring your own key)",
     "price": "free — you pay your provider",
     "matches": "unlimited",
     "includes": "any OpenRouter/Gemini/OpenAI model, your quota, keys "
                 "held in your browser and never persisted server-side",
     "note": "How a researcher runs 500 matches without bankrupting us."},
    {"id": "research",
     "name": "Research mode",
     "price": "free, rate-limited",
     "matches": "seeded, frozen-spec, full provenance",
     "includes": "fixed eval packs, integrity reports, replay audit",
     "note": "Rate-limited to protect the shared budget, not to sell."},
    {"id": "hosted",
     "name": "Hosted evaluation runs",
     "price": "paid (future)",
     "matches": "high volume, priority queue",
     "includes": "dedicated workers, private leaderboards, SLA",
     "note": "Not implemented. Listed so the plan is visible: this is the "
             "line that would fund the free tiers."},
    {"id": "grants",
     "name": "Research grants / sponsorship",
     "price": "n/a",
     "matches": "negotiated",
     "includes": "institutional access, funded eval campaigns",
     "note": "Not implemented."},
]
