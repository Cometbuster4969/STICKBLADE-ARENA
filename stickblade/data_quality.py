"""Data-quality labels for ratings and reports (next-step priority 2).

The infrastructure can now measure model behaviour carefully — but almost
every match recorded so far was fought by scripted baselines, because the
provider keys were not configured. A leaderboard that shows "1084 Elo" for
a model without saying *who actually made the decisions* is easy to
misread as a model result when it is only an infrastructure result.

This module draws the line explicitly. Every match is classified by **who
decided**, not by who was requested:

    real_provider      both fighters were served by a real inference
                       provider (openrouter / groq / openai / google, …)
    mixed_provider     one side was a real provider, the other a scripted
                       brain (a declared bot/mock, or a substitute)
    scripted_baseline  neither side was a real provider

A requested model whose slot was served by a scripted stand-in (no API key,
provider outage with fallback) counts as *scripted* here even though the
roster id says otherwise — the evidence class describes the decisions the
data actually contains. That is the whole point.

Per model, the rollup reports how many matches fall in each class, how many
were ranking-eligible, how many involved a fallback, how many are missing
provider-reported token usage, when the model last played and under which
benchmark version. Two labels summarise it:

    evidence   scripted_baseline | mixed_provider | real_provider
    status     ranking_eligible  | exploratory_only | reference_baseline

`status` is deliberately conservative: a model is `ranking_eligible` only
when at least MIN_REAL_RANKED of its matches were real-provider *and*
ranking-eligible. Declared bots (bot:*/mock:*) are `reference_baseline` —
they are anchors in the comparison graph, never claims about a model.

Everything here is a pure function over match rows so both storage backends
(SQLite, Supabase) and the offline tools share one definition, and the tests
can pin it to hand-built rows.
"""
from __future__ import annotations

import time

# Provider strings that mean "no real model decided this side".
NON_REAL_PROVIDERS = frozenset({"", "scripted", "error", "none", "mock"})

# Roster prefixes that declare a scripted baseline up front.
BASELINE_PREFIXES = ("bot:", "mock:", "scripted:")

# How many real-provider, ranking-eligible matches a model needs before its
# rating is labelled ranking-eligible. Matches the leaderboard's existing
# provisional threshold so the two labels agree.
MIN_REAL_RANKED = 10

# Below this many real-provider ranked matches *in total*, the whole board is
# labelled as scripted / insufficient and the UI shows a banner.
MIN_REAL_FOR_BOARD = 30

EVIDENCE_LABELS = {
    "real_provider": "Real-provider result",
    "mixed_provider": "Mixed-provider result",
    "scripted_baseline": "Scripted baseline",
}
STATUS_LABELS = {
    "ranking_eligible": "Ranking eligible",
    "exploratory_only": "Exploratory only",
    "reference_baseline": "Reference baseline",
}


# --------------------------------------------------------------- per match
def is_real_provider(provider) -> bool:
    """True when a side's decisions came from a real inference provider."""
    return (provider or "").strip().lower() not in NON_REAL_PROVIDERS


def is_declared_baseline(model_id) -> bool:
    return (model_id or "").lower().startswith(BASELINE_PREFIXES)


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def side_view(row: dict, side: str) -> dict:
    """Canvas-side (`a`/`b`) view of a stored match row.

    Storage keeps `model_a`/`model_b` in the user's pick order and every
    `*_a`/`*_b` provenance column in *canvas* order; `flip` links them.
    Getting this mapping wrong would attribute one model's provider and
    tokens to its opponent, so it lives in exactly one place.
    """
    flip = bool(row.get("flip"))
    if side == "a":
        model = row.get("model_b") if flip else row.get("model_a")
    else:
        model = row.get("model_a") if flip else row.get("model_b")
    provider = row.get(f"provider_used_{side}") or ""
    pt = _int(row.get(f"prompt_tokens_{side}"))
    ct = _int(row.get(f"completion_tokens_{side}"))
    calls = _int(row.get(f"api_calls_{side}"))
    real = is_real_provider(provider)
    return {
        "model": model,
        "model_used": row.get(f"model_used_{side}") or model,
        "provider": provider,
        "real": real,
        "declared_baseline": is_declared_baseline(model),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "api_calls": calls,
        # Token metadata is only *expected* from a real provider. A real
        # side with zero reported tokens is a gap in the record, not $0.
        "tokens_reported": (pt + ct) > 0,
        "tokens_missing": real and (pt + ct) == 0,
    }


def evidence_class(row: dict) -> str:
    a = is_real_provider(row.get("provider_used_a"))
    b = is_real_provider(row.get("provider_used_b"))
    if a and b:
        return "real_provider"
    if a or b:
        return "mixed_provider"
    return "scripted_baseline"


def classify_match(row: dict) -> dict:
    """Per-match data-quality record (also embedded in exports)."""
    a, b = side_view(row, "a"), side_view(row, "b")
    ev = evidence_class(row)
    eligible = row.get("ranking_eligible")
    eligible = True if eligible is None else bool(eligible)
    fallback = bool(row.get("fallback_used"))
    return {
        "evidence": ev,
        "evidence_label": EVIDENCE_LABELS[ev],
        "ranking_eligible": eligible,
        "fallback_used": fallback,
        "tokens_missing": a["tokens_missing"] or b["tokens_missing"],
        "provider_identified": all(
            (s["provider"] or "").strip() != "" for s in (a, b)),
        "model_identified": all(
            (s["model_used"] or "").strip() != "" for s in (a, b)),
        # Strict mode must never rank a match that fell back. If a stored
        # row violates that, downstream consumers should see it.
        "silent_fallback": (fallback and eligible
                            and (row.get("fallback_policy") == "strict")),
    }


# --------------------------------------------------------------- per model
def _new_model_bucket(model):
    return {
        "model": model,
        "declared_baseline": is_declared_baseline(model),
        "matches": 0,
        "real_provider_matches": 0,
        "mixed_provider_matches": 0,
        "scripted_matches": 0,
        # this model's own side was served by a real provider
        "own_side_real_matches": 0,
        "ranking_eligible_matches": 0,
        "real_ranked_matches": 0,
        "fallback_matches": 0,
        "token_reported_matches": 0,
        "token_missing_matches": 0,
        "first_match_at": None,
        "last_match_at": None,
        "benchmark_versions": set(),
        "providers": {},
    }


def rollup_models(rows) -> dict:
    """Per-model data-quality rollup over finished match rows.

    Returns {model_id: record}. Only rows with status 'done' (or no status
    column at all, for offline tools) are counted.
    """
    out = {}
    for r in rows:
        if r.get("status") not in (None, "done"):
            continue
        ev = evidence_class(r)
        try:
            created = float(r.get("created") or 0) or None
        except (TypeError, ValueError):
            created = None
        eligible = r.get("ranking_eligible")
        eligible = True if eligible is None else bool(eligible)
        fallback = bool(r.get("fallback_used"))
        for side in ("a", "b"):
            s = side_view(r, side)
            if not s["model"]:
                continue
            m = out.setdefault(s["model"], _new_model_bucket(s["model"]))
            m["matches"] += 1
            if ev == "real_provider":
                m["real_provider_matches"] += 1
            elif ev == "mixed_provider":
                m["mixed_provider_matches"] += 1
            else:
                m["scripted_matches"] += 1
            if s["real"]:
                m["own_side_real_matches"] += 1
                if eligible:
                    m["real_ranked_matches"] += 1
                if s["tokens_reported"]:
                    m["token_reported_matches"] += 1
                else:
                    m["token_missing_matches"] += 1
            if eligible:
                m["ranking_eligible_matches"] += 1
            if fallback:
                m["fallback_matches"] += 1
            if created:
                m["first_match_at"] = (created if m["first_match_at"] is None
                                       else min(m["first_match_at"], created))
                m["last_match_at"] = (created if m["last_match_at"] is None
                                      else max(m["last_match_at"], created))
            bv = r.get("benchmark_version")
            if bv:
                m["benchmark_versions"].add(str(bv))
            if s["provider"]:
                m["providers"][s["provider"]] = \
                    m["providers"].get(s["provider"], 0) + 1
    for m in out.values():
        _finalise_model(m)
    return out


def _finalise_model(m: dict) -> dict:
    if m["declared_baseline"]:
        evidence = "scripted_baseline"
        status = "reference_baseline"
    else:
        if m["own_side_real_matches"] == 0:
            evidence = "scripted_baseline"
        elif m["own_side_real_matches"] == m["matches"] and \
                m["scripted_matches"] == 0 and m["mixed_provider_matches"] == 0:
            evidence = "real_provider"
        else:
            evidence = "mixed_provider"
        status = ("ranking_eligible"
                  if m["real_ranked_matches"] >= MIN_REAL_RANKED
                  else "exploratory_only")
    m["evidence"] = evidence
    m["evidence_label"] = EVIDENCE_LABELS[evidence]
    m["status"] = status
    m["status_label"] = STATUS_LABELS[status]
    m["benchmark_versions"] = sorted(m["benchmark_versions"])
    m["min_real_ranked"] = MIN_REAL_RANKED
    return m


def model_record(rollup: dict, model: str) -> dict:
    """Record for a model, or an explicit 'no matches' record — never None,
    so a UI can always render the label column."""
    rec = rollup.get(model)
    if rec:
        return rec
    return _finalise_model(_new_model_bucket(model))


# ----------------------------------------------------------------- summary
def summary(rows, now=None) -> dict:
    """Board-level data-quality summary — what the banner reads.

    `evidence_level`:
        scripted_only      no real-provider match at all
        insufficient_real  some real-provider matches, fewer than
                           MIN_REAL_FOR_BOARD are ranking-eligible
        real               enough real-provider ranked matches to talk
                           about model behaviour (still subject to the
                           per-pair separability test)
    """
    now = time.time() if now is None else now
    done = [r for r in rows if r.get("status") in (None, "done")]
    counts = {"real_provider": 0, "mixed_provider": 0, "scripted_baseline": 0}
    real_ranked = fallback = silent = 0
    tok_reported = tok_missing = 0
    unidentified = 0
    last = None
    versions = set()
    for r in done:
        c = classify_match(r)
        counts[c["evidence"]] += 1
        if c["evidence"] == "real_provider" and c["ranking_eligible"]:
            real_ranked += 1
        if c["fallback_used"]:
            fallback += 1
        if c["silent_fallback"]:
            silent += 1
        if c["evidence"] != "scripted_baseline":
            if c["tokens_missing"]:
                tok_missing += 1
            else:
                tok_reported += 1
        if not (c["provider_identified"] and c["model_identified"]):
            unidentified += 1
        try:
            created = float(r.get("created") or 0)
        except (TypeError, ValueError):
            created = 0
        if created:
            last = created if last is None else max(last, created)
        if r.get("benchmark_version"):
            versions.add(str(r["benchmark_version"]))
    n = len(done)
    if counts["real_provider"] == 0:
        level = "scripted_only"
    elif real_ranked < MIN_REAL_FOR_BOARD:
        level = "insufficient_real"
    else:
        level = "real"
    billable = tok_reported + tok_missing
    return {
        "matches": n,
        "real_provider_matches": counts["real_provider"],
        "mixed_provider_matches": counts["mixed_provider"],
        "scripted_matches": counts["scripted_baseline"],
        "real_ranked_matches": real_ranked,
        "fallback_matches": fallback,
        "silent_fallback_matches": silent,
        "unidentified_matches": unidentified,
        "token_reported_matches": tok_reported,
        "token_missing_matches": tok_missing,
        "token_coverage": (round(tok_reported / billable, 4)
                           if billable else None),
        "last_match_at": last,
        "benchmark_versions": sorted(versions),
        "evidence_level": level,
        "min_real_for_board": MIN_REAL_FOR_BOARD,
        "min_real_ranked_per_model": MIN_REAL_RANKED,
        "infrastructure_validated": n > 0,
        "model_conclusions_validated": level == "real",
        "note": {
            "scripted_only": ("Every recorded match was fought by scripted "
                              "baselines. The infrastructure is validated; "
                              "no conclusion about any model is."),
            "insufficient_real": (f"Fewer than {MIN_REAL_FOR_BOARD} "
                                  "real-provider ranked matches exist. "
                                  "Treat every ranking as exploratory."),
            "real": ("Real-provider data present. Rankings remain subject "
                     "to the per-pair separability test."),
        }[level],
    }
