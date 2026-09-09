#!/usr/bin/env python3
"""
Cross-benchmark correlation study — STICKBLADE ARENA
====================================================

Question:
    Does the human-perceived Elo (crowd-vote rating) rank models the same
    way as the objective win-rate leaderboard (mechanical damage/win/loss)?

    Answer decides whether METHODOLOGY.md § 4's core claim — "the gap
    between perceived-Elo and objective win-rate is the benchmark's most
    interesting signal" — is defensible. If ρ is very high, the two
    leaderboards are redundant and we should collapse them. If ρ is low,
    the gap really is meaningful and we should report both.

Method:
    Pulls fresh JSON dumps from the live prod endpoints:
        /api/leaderboard           (perceived Elo, blind human votes)
        /api/leaderboard/objective (mechanical win/loss/damage)
        /api/export?fmt=json       (raw per-match data)

    Then computes:
        * Spearman rho + Kendall tau on all shared models
        * Slice by weapon (sword / spear / flail / bow / dagger)
        * Slice by mode  (macro / joint)
        * Compares LLM-only, bot-only, and combined populations

Reproducibility:
    Snapshots of all three endpoints captured 2026-08-04 are checked in
    beside this script:
        research/export_snapshot_2026-08-04.json
        research/lb_perceived_snapshot_2026-08-04.json
        research/lb_objective_snapshot_2026-08-04.json

    Running this script offline against those snapshots reproduces the
    numbers in METHODOLOGY.md § 4 Table 1.

Author: Ayush (Cometbuster4969)
Date:   2026-08-04
"""

from __future__ import annotations
import json
import pathlib
import sys
from collections import defaultdict

import pandas as pd
from scipy import stats

# Windows-safe stdout: force UTF-8 so print() can emit ρ, τ, —, ≥, ± etc.
# Python on Windows defaults stdout to cp1252 which crashes on these chars.
# `errors="replace"` is a belt-and-braces fallback so a stray character
# still degrades to '?' instead of aborting the whole run.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # Very old Python or a non-standard stream — fall through; the
        # script will still run, may just show '?' for Greek letters.
        pass

HERE = pathlib.Path(__file__).parent
SNAP_DATE = "2026-08-04"

EXPORT_PATH = HERE / f"export_snapshot_{SNAP_DATE}.json"
PERCEIVED_PATH = HERE / f"lb_perceived_snapshot_{SNAP_DATE}.json"
OBJECTIVE_PATH = HERE / f"lb_objective_snapshot_{SNAP_DATE}.json"

# Frozen-pack v1 results (Tier-A #4). Loaded IF present — the original
# 2026-08-04 study runs even without it. When present, matches from the
# frozen pack are added to the export DataFrame so per-model objective
# sample sizes cross the joint filter (perceived_n >= 5 AND matches >= 5)
# and the study can produce a publishable Spearman rho.
#
# Pack spec + runner: research/frozen_pack_v1.yaml + tools/run_frozen_pack.py
FROZEN_PACK_CSV = HERE / "frozen_pack_v1_results.csv"


def load_leaderboards():
    """Return (perceived_df, objective_df, export_df).

    perceived_df — one row per (model, weapon, mode, arena, blindfolded)
    objective_df — one row per model (marginalized)
    export_df    — one row per match. INCLUDES frozen-pack matches when
                   research/frozen_pack_v1_results.csv exists (the whole
                   point of the frozen pack is to fatten this DataFrame's
                   per-model row count so the joint filter has real n).
    """
    # encoding="utf-8" required — Python on Windows defaults to cp1252 which
    # can't decode em-dashes, curly quotes, Greek letters (ρ), etc. that
    # appear in commentary text and model descriptions inside the snapshots.
    perceived = pd.DataFrame(json.loads(PERCEIVED_PATH.read_text(encoding="utf-8")))
    objective = pd.DataFrame(json.loads(OBJECTIVE_PATH.read_text(encoding="utf-8")))
    export = pd.DataFrame(json.loads(EXPORT_PATH.read_text(encoding="utf-8"))["matches"])

    # Splice in frozen-pack results if the CSV exists. The CSV schema is
    # a strict subset of /api/export's match schema — just the fields we
    # need for the correlation study. Missing fields default to NaN.
    if FROZEN_PACK_CSV.exists():
        pack = pd.read_csv(FROZEN_PACK_CSV)
        pack = pack[pack["status"] == "done"].copy()
        # Rename/coerce so pack rows can be concat'd with export rows
        pack["id"] = pack["match_id"]
        pack["voted"] = False   # frozen-pack matches are NOT public-voted
        pack["blind"] = True
        pack["blindfolded"] = False
        pack["mode"] = "macro"
        pack["arena"] = "normal"
        # Columns that align exactly with /api/export schema
        keep = [c for c in export.columns if c in pack.columns]
        pack_slim = pack[keep].copy()
        n_before = len(export)
        export = pd.concat([export, pack_slim], ignore_index=True)
        print(f"[frozen-pack] Loaded {len(pack)} pack matches; "
              f"export DataFrame grew {n_before} -> {len(export)}")
    else:
        print(f"[frozen-pack] No {FROZEN_PACK_CSV.name} — study runs on "
              f"organic 2026-08-04 snapshot only (expect underpowered result)")

    return perceived, objective, export


def build_shared_frame(perceived: pd.DataFrame, objective: pd.DataFrame,
                       export: pd.DataFrame | None = None):
    """Join perceived-Elo (marginalized over all axes) with objective stats
    on model id. Returns a DataFrame with one row per shared model.

    IMPORTANT: if `export` is provided, objective stats are RECOMPUTED from
    the raw match rows instead of using the pre-aggregated `objective`
    snapshot. This is required after the frozen-pack merge, because the
    objective-leaderboard snapshot was captured BEFORE the frozen pack ran
    and doesn't know about those matches. Without this recompute, the
    joint sample-size filter (matches >= 5) never crosses threshold even
    though 100 pack matches were added — the pack rows land in `export`
    but the stale `matches` count from the objective JSON hides them.
    """
    # Take the perceived aggregate row (sharp/weapon/mode/arena all == 'ALL')
    p_agg = perceived[
        (perceived["sharp"] == "ALL")
        & (perceived["weapon"] == "ALL")
        & (perceived["mode"] == "ALL")
        & (perceived["arena"] == "ALL")
        & (perceived["blindfolded"] == False)  # noqa: E712
    ][["model", "rating", "n", "win_rate"]].rename(
        columns={"rating": "perceived_elo",
                 "n": "perceived_n",
                 "win_rate": "perceived_win_rate"}
    )

    if export is not None:
        # Recompute objective stats from the (post-merge) export DataFrame.
        # For each model, tally matches where it appeared as model_a OR
        # model_b, count wins per side, sum damage dealt, etc.
        done = export[export["status"] == "done"].copy() \
            if "status" in export.columns else export.copy()
        stats_rows = []
        all_models = set(done.get("model_a", [])) | set(done.get("model_b", []))
        for model in all_models:
            as_a = done[done["model_a"] == model]
            as_b = done[done["model_b"] == model]
            n = len(as_a) + len(as_b)
            if n == 0:
                continue
            wins = ((as_a["winner_side"] == "a").sum()
                    + (as_b["winner_side"] == "b").sum())
            losses = ((as_a["winner_side"] == "b").sum()
                      + (as_b["winner_side"] == "a").sum())
            draws = n - wins - losses
            damage_dealt = (
                pd.to_numeric(as_a.get("damage_dealt_a"), errors="coerce").fillna(0).sum()
                + pd.to_numeric(as_b.get("damage_dealt_b"), errors="coerce").fillna(0).sum()
            )
            turns = pd.to_numeric(as_a.get("turns"), errors="coerce").fillna(0).sum() \
                    + pd.to_numeric(as_b.get("turns"), errors="coerce").fillna(0).sum()
            hits_landed = (
                pd.to_numeric(as_a.get("hits_landed_a"), errors="coerce").fillna(0).sum()
                + pd.to_numeric(as_b.get("hits_landed_b"), errors="coerce").fillna(0).sum()
            )
            hits_attempted = (
                pd.to_numeric(as_a.get("hits_attempted_a"), errors="coerce").fillna(0).sum()
                + pd.to_numeric(as_b.get("hits_attempted_b"), errors="coerce").fillna(0).sum()
            )
            stats_rows.append({
                "model": model,
                "matches": n,
                "wins": int(wins), "losses": int(losses), "draws": int(draws),
                "objective_win_rate": (wins + 0.5 * draws) / n,
                "damage_per_turn": (damage_dealt / turns) if turns > 0 else 0.0,
                "hit_rate": (hits_landed / hits_attempted) if hits_attempted > 0 else 0.0,
                "fallback_rate": 0.0,  # not derivable from export slice; placeholder
            })
        o = pd.DataFrame(stats_rows)
        print(f"[build_shared_frame] Recomputed objective stats from "
              f"{len(done)} export rows -> {len(o)} models with matches")
    else:
        # Legacy path: trust the pre-aggregated objective snapshot.
        o = objective[["model", "matches", "damage_per_turn", "hit_rate",
                       "fallback_rate", "wins", "losses", "draws"]].copy()
        o["objective_win_rate"] = (o["wins"] + 0.5 * o["draws"]) / o["matches"]

    return p_agg.merge(o, on="model", how="inner")


def _bootstrap_ci_rho(x, y, n_boot=2000, seed=42):
    """Return (lo, hi) 95% bootstrap CI on Spearman rho.

    Non-parametric CIs are the honest way to report ρ at small n.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    x = np.asarray(x); y = np.asarray(y)
    n = len(x)
    if n < 3:
        return (float("nan"), float("nan"))
    rhos = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        if len(set(idx)) < 3:
            continue
        try:
            r, _ = stats.spearmanr(x[idx], y[idx])
            if not (r != r):  # not NaN
                rhos.append(r)
        except Exception:
            continue
    if not rhos:
        return (float("nan"), float("nan"))
    rhos.sort()
    return (rhos[int(0.025 * len(rhos))], rhos[int(0.975 * len(rhos))])


def correlate(df: pd.DataFrame, label: str):
    """Print Spearman + Kendall between perceived_elo and objective metrics.

    Returns a dict of results for programmatic use.
    """
    if len(df) < 3:
        print(f"[{label}] n={len(df)} — too few models for a meaningful "
              f"correlation. Skipping.")
        return None

    out = {"label": label, "n_models": len(df)}
    print(f"\n[{label}] n = {len(df)} models")
    print(f"  Median perceived_n:  {df['perceived_n'].median():.0f} matches/model")
    print(f"  Median objective_n:  {df['matches'].median():.0f} matches/model")

    for obj_metric in ["objective_win_rate", "damage_per_turn", "hit_rate"]:
        try:
            rho, p_rho = stats.spearmanr(df["perceived_elo"], df[obj_metric])
            tau, p_tau = stats.kendalltau(df["perceived_elo"], df[obj_metric])
            lo, hi = _bootstrap_ci_rho(df["perceived_elo"].values,
                                       df[obj_metric].values)
        except (ValueError, KeyError):
            continue
        out[f"{obj_metric}_spearman_rho"] = rho
        out[f"{obj_metric}_spearman_p"] = p_rho
        out[f"{obj_metric}_kendall_tau"] = tau
        out[f"{obj_metric}_kendall_p"] = p_tau
        out[f"{obj_metric}_spearman_ci95"] = (lo, hi)
        star_rho = "  ***" if p_rho < 0.001 else "  **" if p_rho < 0.01 else "  *" if p_rho < 0.05 else ""
        print(f"  perceived_elo vs {obj_metric:22s} — "
              f"ρ = {rho:+.3f} [95%% CI {lo:+.3f}, {hi:+.3f}] "
              f"(p = {p_rho:.3f}){star_rho}  "
              f"τ = {tau:+.3f} (p = {p_tau:.3f})")
    return out


def slice_by_weapon(export: pd.DataFrame, perceived: pd.DataFrame,
                    objective: pd.DataFrame):
    """Compute per-weapon perceived/objective correlations.

    For each weapon:
      * grab the perceived-Elo row for (weapon=W, sharp=ALL, mode=ALL, arena=ALL)
      * compute per-model objective win_rate on JUST matches of that weapon
      * correlate.
    """
    results = []
    for weapon in sorted(export["weapon"].dropna().unique()):
        p_w = perceived[
            (perceived["weapon"] == weapon)
            & (perceived["mode"] == "ALL")
            & (perceived["arena"] == "ALL")
            & (perceived["blindfolded"] == False)  # noqa: E712
        ][["model", "rating", "n"]].rename(
            columns={"rating": "perceived_elo", "n": "perceived_n"}
        )

        # Recompute objective win_rate on only this-weapon matches
        matches_w = export[export["weapon"] == weapon].copy()
        obj_rows = []
        for model in p_w["model"].unique():
            m_as_a = matches_w[matches_w["model_a"] == model]
            m_as_b = matches_w[matches_w["model_b"] == model]
            n = len(m_as_a) + len(m_as_b)
            if n == 0:
                continue
            wins = ((m_as_a["winner_side"] == "a").sum()
                    + (m_as_b["winner_side"] == "b").sum())
            draws = ((m_as_a["winner_side"].isin(["draw", None])
                      | m_as_a["winner_side"].isna()).sum()
                     + (m_as_b["winner_side"].isin(["draw", None])
                        | m_as_b["winner_side"].isna()).sum())
            obj_rows.append({"model": model, "objective_win_rate":
                             (wins + 0.5 * draws) / n, "matches": n})
        obj_w = pd.DataFrame(obj_rows)
        if obj_w.empty:
            continue
        df_w = p_w.merge(obj_w, on="model", how="inner")
        r = correlate(df_w, f"weapon={weapon}")
        if r:
            r["weapon"] = weapon
            results.append(r)
    return results


def population_slices(shared: pd.DataFrame):
    """Slice by LLM vs bot and correlate separately.

    Rationale: bots are deterministic policies that should show tight
    correlation between perceived and objective. LLMs, if the human vote
    captures anything different from raw win-rate, should show lower
    correlation. The gap between the two ρ values is direct evidence
    for/against the 'humans reward smart-looking play differently from
    mechanical wins' hypothesis in METHODOLOGY.md § 4.
    """
    bots = shared[shared["model"].str.startswith("bot:") |
                  shared["model"].str.startswith("mock:")]
    llms = shared[~(shared["model"].str.startswith("bot:") |
                    shared["model"].str.startswith("mock:"))]
    correlate(bots, "bots+mocks only")
    correlate(llms, "LLMs only")


def main():
    if not (EXPORT_PATH.exists() and PERCEIVED_PATH.exists()
            and OBJECTIVE_PATH.exists()):
        print(f"Missing snapshot files in {HERE}. Expected:")
        for p in (EXPORT_PATH, PERCEIVED_PATH, OBJECTIVE_PATH):
            print(f"  {p.name}  {'OK' if p.exists() else 'MISSING'}")
        sys.exit(1)

    perceived, objective, export = load_leaderboards()

    print("=" * 72)
    print(f"STICKBLADE cross-benchmark correlation study — snapshot {SNAP_DATE}")
    print("=" * 72)
    print(f"perceived leaderboard rows: {len(perceived)}")
    print(f"objective leaderboard rows: {len(objective)}")
    print(f"exported matches:           {len(export)}")

    # Pass `export` in so objective stats get recomputed from the merged
    # DataFrame — this is what makes frozen-pack matches actually count
    # in the joint sample-size filter.
    shared = build_shared_frame(perceived, objective, export)
    print(f"\nModels present on BOTH leaderboards: {len(shared)}")
    print("  Merged frame preview:")
    print(shared[["model", "perceived_elo", "perceived_n",
                  "objective_win_rate", "matches",
                  "damage_per_turn"]].to_string(index=False))

    print("\n" + "#" * 72)
    print("# UNFILTERED — every model regardless of sample size.")
    print("# WARNING: Elo has not converged for models with n < 10 matches.")
    print("# Use the MIN_N filtered results below as the headline number.")
    print("#" * 72)
    correlate(shared, "ALL models UNFILTERED (LLMs + bots + mocks)")
    population_slices(shared)

    # Filtered by minimum sample size — this is the honest headline.
    # Must filter BOTH sides: a model with perceived_n=44 but matches=3
    # has an objective_win_rate that's dominated by physics-simulation noise
    # even though its perceived Elo has converged.
    print("\n" + "#" * 72)
    print("# FILTERED — models with at least MIN_N_PERCEIVED voted matches")
    print("# AND at least MIN_N_OBJECTIVE completed matches.")
    print("#")
    print("# This is the honest headline number. Below these thresholds")
    print("# either the perceived Elo hasn't converged (dominated by the")
    print("# 1000-baseline prior) OR the objective win-rate is dominated by")
    print("# small-sample noise (100% win rate at n=1 is meaningless).")
    print("#" * 72)
    MIN_N_PERCEIVED = 5
    MIN_N_OBJECTIVE = 5
    shared_conv = shared[
        (shared["perceived_n"] >= MIN_N_PERCEIVED)
        & (shared["matches"] >= MIN_N_OBJECTIVE)
    ].copy()
    print(f"\nModels with perceived_n >= {MIN_N_PERCEIVED} AND "
          f"matches >= {MIN_N_OBJECTIVE}: {len(shared_conv)}")
    if len(shared_conv) >= 3:
        print(shared_conv[["model", "perceived_elo", "perceived_n",
                           "objective_win_rate", "matches",
                           "damage_per_turn"]].to_string(index=False))
        correlate(shared_conv,
                  f"BOTH-CONVERGED (perceived_n >= {MIN_N_PERCEIVED}, "
                  f"matches >= {MIN_N_OBJECTIVE})")
        # LLM-only within converged set
        llms_conv = shared_conv[~(
            shared_conv["model"].str.startswith("bot:") |
            shared_conv["model"].str.startswith("mock:"))]
        if len(llms_conv) >= 3:
            correlate(llms_conv,
                      f"BOTH-CONVERGED LLMs only")
        else:
            print(f"\n[BOTH-CONVERGED LLMs only] n={len(llms_conv)} — "
                  f"too few LLMs meet both thresholds. This is the honest "
                  f"read: at current traffic (n={len(export)} matches), "
                  f"the cross-benchmark study is UNDERPOWERED. The Wilson")
            print(f"CIs on individual Elo/win-rate values are trustworthy;")
            print(f"the CROSS-metric correlation needs more matches.")

    print("\n" + "-" * 72)
    print("Per-weapon slices (all sample sizes — sparse data):")
    print("-" * 72)
    slice_by_weapon(export, perceived, objective)

    print("\n" + "=" * 72)
    print("Interpretation guide (per METHODOLOGY.md § 4):")
    print("  |ρ| ≥ 0.85 → leaderboards mostly redundant, consider collapsing")
    print("  0.5 ≤ |ρ| < 0.85 → both signals valid, gap is meaningful")
    print("  |ρ| < 0.5 with p > 0.05 → underpowered; publish CI, run more matches")
    print("  Negative ρ → humans and objective disagree systematically; the")
    print("               gap IS the headline finding (if statistically valid)")
    print("=" * 72)


if __name__ == "__main__":
    main()
