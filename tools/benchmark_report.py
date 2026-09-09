#!/usr/bin/env python3
"""Monthly benchmark report generator (action-plan §29).

Turns raw operational exports into the report a research artifact is
expected to publish on a cadence: how many matches ran, which models were
active, how ratings moved, how reliable the harness was, what exploits
showed up, what changed methodologically, and what the known limitations
are.

Everything is computed from files you already have — nothing is invented.
Any section whose input is missing is explicitly marked "not supplied"
rather than silently skipped, because a report with a hidden gap is worse
than a report with a visible one.

Inputs (all optional):
  --export        matches JSON from `GET /api/export?fmt=json`
                  (or tools/export_dataset.py)
  --leaderboard   leaderboard JSON from `GET /api/leaderboard`
  --objective     JSON from `GET /api/leaderboard/objective`
  --metrics       JSON from `GET /api/metrics`
  --ratings       JSON from `GET /api/leaderboard/bradley_terry`
  --stats         JSON from `GET /api/model_stats`
  --balance       JSON from `tools/weapon_balance.py --md-out x.md`
  --prev-export   last month's export, for deltas
  --notes         free-text methodology-change note (repeatable)

Usage:
    python3 tools/benchmark_report.py \\
        --export research/exports/2026-09.json \\
        --leaderboard research/lb_2026-09.json \\
        --metrics research/metrics_2026-09.json \\
        --out research/reports/2026-09.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from datetime import datetime, timezone


def load(path):
    if not path:
        return None
    p = pathlib.Path(path)
    if not p.exists():
        print(f"  ! missing input: {path}")
        return None
    text = p.read_text()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # JSON Lines (dataset releases ship matches/matches.jsonl): one object
    # per line, wrapped so the rest of the report sees an export payload.
    try:
        rows = [json.loads(l) for l in text.splitlines() if l.strip()]
        if rows and all(isinstance(r, dict) for r in rows):
            return {"matches": rows, "count": len(rows), "source": str(p)}
    except ValueError as e:
        print(f"  ! could not parse {path}: {e}")
    return None


def _iso(ts):
    """Epoch → ISO-8601 UTC; passes ISO strings and None through."""
    if ts is None:
        return "?"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OSError):
        return str(ts)


def pct(values, p):
    if not values:
        return None
    vs = sorted(values)
    return round(vs[min(len(vs) - 1, int(p * len(vs)))], 2)


def match_rows(export):
    if not export:
        return []
    if isinstance(export, dict):
        return export.get("matches", [])
    return export if isinstance(export, list) else []


def section_volume(rows):
    if not rows:
        return None
    done = [r for r in rows if r.get("status") == "done"]
    by_model = {}
    for r in done:
        for m in (r.get("model_a"), r.get("model_b")):
            if m:
                by_model[m] = by_model.get(m, 0) + 1
    by_weapon, by_arena, by_mode = {}, {}, {}
    for r in done:
        by_weapon[r.get("weapon")] = by_weapon.get(r.get("weapon"), 0) + 1
        by_arena[r.get("arena")] = by_arena.get(r.get("arena"), 0) + 1
        by_mode[r.get("mode")] = by_mode.get(r.get("mode"), 0) + 1
    return {"matches_exported": len(rows), "completed": len(done),
            "active_models": len(by_model),
            "top_models": sorted(by_model.items(), key=lambda kv: -kv[1])[:10],
            "by_weapon": by_weapon, "by_arena": by_arena, "by_mode": by_mode}


def section_reliability(rows, metrics):
    if not rows and not metrics:
        return None
    done = [r for r in rows if r.get("status") == "done"] or rows
    fb = [r for r in done if r.get("fallback_used")]
    lat = [float(r["latency_ms_a"]) for r in done
           if r.get("latency_ms_a") is not None]
    lat += [float(r["latency_ms_b"]) for r in done
            if r.get("latency_ms_b") is not None]
    invalid = sum(int(r.get("invalid_actions_a") or 0) +
                  int(r.get("invalid_actions_b") or 0) for r in done)
    ineligible = [r for r in done if r.get("ranking_eligible") is False]
    turns = [int(r["turns"]) for r in done if r.get("turns")]
    return {
        "matches": len(done),
        "fallback_matches": len(fb),
        "fallback_rate": round(len(fb) / len(done), 4) if done else None,
        "invalid_actions": invalid,
        "ranking_ineligible": len(ineligible),
        "latency_ms_p50": pct(lat, 0.50),
        "latency_ms_p95": pct(lat, 0.95),
        "latency_ms_max": max(lat) if lat else None,
        "avg_turns": round(statistics.mean(turns), 1) if turns else None,
        "metrics_snapshot": (metrics or {}).get("rates"),
    }


def section_data_quality(rows, export):
    """Evidence summary for the whole report (next-step priority 2).

    Uses stickblade/data_quality.py so the report, the API and the site
    agree on what counts as real-provider evidence. Falls back to the
    export's embedded `data_quality` block if the module is unavailable.
    """
    done = [r for r in rows if r.get("status") == "done"] or rows
    if not done:
        return None
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                               / "stickblade"))
        import data_quality as DQ
        summ = DQ.summary(done)
        labels = DQ.EVIDENCE_LABELS
    except Exception:                                   # noqa: BLE001
        summ = (export or {}).get("data_quality") if isinstance(export, dict) \
            else None
        labels = {}
        if not summ:
            return None
    versions = sorted({str(r.get("benchmark_version")) for r in done} - {"None"})
    prompts = sorted({str(r.get("prompt_version")) for r in done} - {"None"})
    fps = sorted({str(r.get("spec_fingerprint")) for r in done} - {"None"})
    ds = sorted({str(r.get("dataset_version")) for r in done} - {"None"})
    return {"summary": summ, "labels": labels, "benchmark_versions": versions,
            "prompt_versions": prompts, "fingerprints": fps,
            "dataset_versions": ds}


def section_rankings(leaderboard, objective, prev_rows):
    if not leaderboard:
        return None
    rows = leaderboard if isinstance(leaderboard, list) else \
        leaderboard.get("rows", [])
    top = sorted(rows, key=lambda r: -(r.get("rating") or 0))[:15]
    out = []
    prev_rating = {}
    for r in (prev_rows or []):
        key = (r.get("model"), r.get("sharp"), r.get("weapon"))
        try:
            prev_rating[key] = float(r.get("rating"))
        except (TypeError, ValueError):
            pass
    for r in top:
        key = (r.get("model"), r.get("sharp"), r.get("weapon"))
        delta = None
        if key in prev_rating and r.get("rating") is not None:
            delta = round(float(r["rating"]) - prev_rating[key], 1)
        n = (r.get("wins") or 0) + (r.get("losses") or 0) + (r.get("draws") or 0)
        out.append({"model": r.get("model"), "rating": r.get("rating"),
                    "n": n, "delta": delta,
                    "provisional": n < 10,
                    "win_rate": r.get("win_rate"),
                    "ci": (r.get("win_rate_lo"), r.get("win_rate_hi"))})
    obj_top = []
    if objective:
        orows = objective if isinstance(objective, list) else \
            objective.get("rows", [])
        obj_top = sorted(orows, key=lambda r: -(r.get("damage_per_turn") or 0))[:5]
    return {"top": out, "objective_top": obj_top}


def section_ratings(bt, stats):
    """Bradley-Terry + full metric table (action-plan §5).

    Deliberately rendered as its own section rather than merged into the
    Elo table: they are different estimators answering different questions,
    and a reader who sees one number per model will assume it is the
    result. Publishing the interval next to the point estimate is the point.
    """
    if not bt and not stats:
        return None
    out = {"comparisons": None, "bootstraps": None, "rows": [],
           "stats": [], "separable_pairs": None, "not_separable_pairs": None}
    if bt:
        rows = bt.get("rows", []) if isinstance(bt, dict) else bt
        out["comparisons"] = bt.get("comparisons")
        out["bootstraps"] = bt.get("bootstraps")
        rows = sorted(rows, key=lambda r: -(r.get("rating") or 0))
        # Tie bands: greedy overlap grouping, same rule the UI uses.
        bands, cur = [], None
        for r in rows:
            if cur and r["ci_low"] <= cur:
                cur = max(cur, r["ci_high"]); bands[-1].append(r)
            else:
                cur = r["ci_high"]; bands.append([r])
        for i, band in enumerate(bands):
            letter = chr(97 + i)
            for r in band:
                out["rows"].append({**r, "band": letter})
        # How many pairs are actually separable? If the answer is "almost
        # none", the honest report says the field is not ranked yet.
        n = len(rows)
        sep = tot = 0
        for i in range(n):
            for j in range(i + 1, n):
                tot += 1
                if rows[i]["ci_low"] > rows[j]["ci_high"]:
                    sep += 1
        out["separable_pairs"] = sep
        out["not_separable_pairs"] = tot - sep
        out["pairs"] = tot
    if stats:
        srows = stats.get("rows", []) if isinstance(stats, dict) else stats
        out["stats"] = sorted(srows, key=lambda r: -(r.get("win_rate") or 0))
    return out


def render(ctx):
    today = ctx["generated"]
    notes = ctx.get("notes") or []
    L = ["# Stickblade Arena — benchmark report", "",
         f"**Period:** {ctx.get('period', 'unspecified')}  ",
         f"**Generated:** {today}  ",
         f"**Benchmark version:** {ctx.get('benchmark_version', '?')}  ",
         f"**Spec fingerprint:** `{ctx.get('fingerprint', '?')}`", "",
         "This report is generated by `tools/benchmark_report.py` from raw "
         "exports. Sections whose input data was not supplied are marked "
         "*not supplied* rather than omitted.", ""]
    if ctx.get("sources"):
        L += ["**Inputs:**", ""]
        for label, path in ctx["sources"].items():
            L.append(f"- {label}: `{path}`")
        L.append("")

    L += ["## 0. Data quality — what this report is evidence of", ""]
    dq = ctx.get("data_quality")
    if not dq:
        L += ["*not supplied* — pass `--export`", ""]
    else:
        sm = dq["summary"]
        lvl = sm.get("evidence_level")
        headline = {
            "scripted_only": "**Scripted baselines only.** Every match below "
                             "was fought by mock:/bot: fighters. This report "
                             "validates the pipeline and says nothing about "
                             "any language model.",
            "insufficient_real": "**Insufficient real-provider evidence.** Some "
                                 "matches were fought by real models, fewer "
                                 "than the board minimum. Treat every ranking "
                                 "below as exploratory.",
            "real": "Real-provider evidence present at board level; "
                    "per-model status still applies.",
        }.get(lvl, f"evidence level `{lvl}`")
        L += [headline, "",
              f"- Dataset version(s): {', '.join(f'`{d}`' for d in dq['dataset_versions']) or '*not a versioned release*'}",
              f"- Benchmark version(s): {', '.join(dq['benchmark_versions']) or '?'} · "
              f"prompt version(s): {', '.join(dq['prompt_versions']) or '?'} · "
              f"spec fingerprint(s): {', '.join(f'`{f}`' for f in dq['fingerprints']) or '?'}",
              f"- Matches: **{sm.get('matches')}** = "
              f"{sm.get('real_provider_matches', 0)} real-provider + "
              f"{sm.get('mixed_provider_matches', 0)} mixed + "
              f"{sm.get('scripted_matches', 0)} scripted-baseline",
              f"- Ranking-eligible real-provider matches: "
              f"{sm.get('real_ranked_matches', 0)} "
              f"(board minimum {sm.get('min_real_for_board')}, per-model "
              f"minimum {sm.get('min_real_ranked_per_model')})",
              f"- Fallback: {sm.get('fallback_matches', 0)} matches; silent "
              f"(fallback yet still ranked): {sm.get('silent_fallback_matches', 0)}",
              f"- Provider/model unidentified: {sm.get('unidentified_matches', 0)}",
              f"- Token coverage on real-provider sides: "
              f"{sm.get('token_coverage') if sm.get('token_coverage') is not None else 'n/a'}",
              f"- Last match: {_iso(sm.get('last_match_at'))}", ""]

    L += ["## 1. Volume", ""]
    vol = ctx.get("volume")
    if not vol:
        L += ["*not supplied* — pass `--export`", ""]
    else:
        L += [f"- Matches exported: **{vol['matches_exported']}** "
              f"(completed: {vol['completed']})",
              f"- Active models: **{vol['active_models']}**",
              f"- By weapon: {vol['by_weapon']}",
              f"- By arena: {vol['by_arena']}",
              f"- By control mode: {vol['by_mode']}", "",
              "### Most-played models", "",
              "| model | matches |", "|---|---:|"]
        L += [f"| `{m}` | {n} |" for m, n in vol["top_models"]]
        L += [""]

    L += ["## 2. Reliability", ""]
    rel = ctx.get("reliability")
    if not rel:
        L += ["*not supplied*", ""]
    else:
        L += [f"- Matches analysed: {rel['matches']}",
              f"- Provider fallback: {rel['fallback_matches']} matches "
              f"({rel['fallback_rate']})",
              f"- Invalid actions: {rel['invalid_actions']}",
              f"- Ranking-ineligible matches: {rel['ranking_ineligible']}",
              f"- Decision latency: p50 {rel['latency_ms_p50']} ms, "
              f"p95 {rel['latency_ms_p95']} ms, max {rel['latency_ms_max']} ms",
              f"- Average match length: {rel['avg_turns']} turns", ""]
        if rel.get("metrics_snapshot"):
            L += [f"Live rate snapshot: {rel['metrics_snapshot']}", ""]

    L += ["## 3. Rankings", ""]
    rank = ctx.get("rankings")
    if not rank:
        L += ["*not supplied* — pass `--leaderboard`", ""]
    else:
        L += ["| # | model | rating | Δ vs previous | matches | win rate "
              "(95% CI) |", "|---:|---|---:|---:|---:|---:|"]
        for i, r in enumerate(rank["top"], 1):
            ci = (f"[{r['ci'][0]}, {r['ci'][1]}]"
                  if r.get("ci") and r["ci"][0] is not None else "—")
            delta = r["delta"] if r["delta"] is not None else "—"
            prov = " (provisional)" if r["provisional"] else ""
            L.append(f"| {i} | `{r['model']}` | {r['rating']} | {delta} "
                     f"| {r['n']}{prov} | {r['win_rate']} {ci} |")
        L += [""]
        if rank.get("objective_top"):
            L += ["### Objective skill (physics-derived, vote-independent)",
                  "", "| model | damage/turn | hit rate | fallback rate |"
                  " matches |", "|---|---:|---:|---:|---:|"]
            for r in rank["objective_top"]:
                L.append(f"| `{r.get('model')}` | {r.get('damage_per_turn')} "
                         f"| {r.get('hit_rate')} | {r.get('fallback_rate')} "
                         f"| {r.get('matches')} |")
            L += [""]

    rt = ctx.get("ratings")
    if rt:
        L += ["## 3b. Ratings with uncertainty (Bradley–Terry)", ""]
        L += [f"- Comparisons fitted: **{rt['comparisons']}** "
              f"(bootstrap resamples: {rt['bootstraps']})",
              f"- Separable pairs: **{rt['separable_pairs']} / {rt['pairs']}**. "
              "A pair is separable only when the lower bound of one model is "
              "above the upper bound of the other; everything else is a tie "
              "the data cannot resolve.", ""]
        L += ["| band | model | rating | 95% CI | n | preference rate |",
              "|---|---|---:|---|---:|---:|"]
        for r in rt["rows"]:
            prov = " ?" if r.get("provisional") else ""
            pref = r.get("preference_rate")
            L.append(f"| {r['band']} | `{r['model']}`{prov} | {r['rating']} "
                     f"| [{r['ci_low']}, {r['ci_high']}] | {r['matches']} "
                     f"| {pref if pref is not None else '—'} |")
        L += ["", "Models sharing a band letter are **not statistically "
              "separated**. `?` = provisional.", ""]
        if rt["stats"]:
            L += ["### Full metrics per model", "",
                  "| model | n | win | pref | dmg/turn | hits/atk | lethal | "
                  "survived | timeout | invalid | fallback | latency |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for r in rt["stats"][:25]:
                f_ = lambda k: "—" if r.get(k) is None else r.get(k)   # noqa: E731
                L.append(f"| `{r['model']}` | {r.get('matches')} | {f_('win_rate')} "
                         f"| {f_('preference_rate')} | {f_('damage_per_turn')} "
                         f"| {f_('hit_rate')} | {f_('lethal_rate')} "
                         f"| {f_('survival_rate')} | {f_('timeout_rate')} "
                         f"| {f_('invalid_action_rate')} | {f_('fallback_rate')} "
                         f"| {r.get('latency_ms_mean')} ms |")
            L += ["", "`hits/atk` can exceed 1.0 (contact events per decision, "
                  "not accuracy). `lethal` counts kills only, so an attrition "
                  "fighter shows 0 with a high win rate.", ""]

    L += ["## 4. Balance", ""]
    bal = ctx.get("balance")
    if not bal:
        L += ["*not supplied* — run `tools/weapon_balance.py` and pass "
              "`--balance`", ""]
    else:
        L += ["| weapon | matches | side-A win rate (95% CI) | avg damage | "
              "avg turns | lethal rate |", "|---|---:|---:|---:|---:|---:|"]
        for r in bal.get("by_weapon", []):
            ci = f"[{r['ci_lo']}, {r['ci_hi']}]" if r["ci_lo"] is not None else "—"
            L.append(f"| {r['weapon']} | {r['matches']} | "
                     f"{r['side_a_win_rate']} {ci} | {r['avg_damage']} | "
                     f"{r['avg_turns']} | {r['lethal_rate']} |")
        L += [""]
        if bal.get("flags"):
            L += ["### Flags", ""] + [f"- {f}" for f in bal["flags"]] + [""]

    L += ["## 5. Methodology changes", ""]
    L += ([f"- {n}" for n in notes] if notes
          else ["- None recorded this period."])
    L += [""]

    L += ["## 6. Known limitations", ""]
    L += [
        "- Rankings are segmented per (model, sharp, weapon, mode, arena, "
        "blindfolded); cells with fewer than 10 matches are provisional.",
        "- Match outcomes depend on real-time provider latency; a slow but "
        "strong model is penalised by timeouts, which is why latency, "
        "fallback and invalid-action rates are published alongside ratings.",
        "- Human tactical votes are the ranked signal; entertainment and "
        "execution votes are collected separately and are not ranked.",
        "- Scripted fallback turns are counted per fighter and surfaced on "
        "every match; strict-policy matches are excluded from rankings.",
        "- LLM decisions are not reproducible from a seed; only the physics "
        "and scripted brains are. Reproducibility is audited by replaying "
        "the stored action log, not by re-calling providers.",
        "",
    ]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export")
    ap.add_argument("--prev-export")
    ap.add_argument("--leaderboard")
    ap.add_argument("--objective")
    ap.add_argument("--metrics")
    ap.add_argument("--balance")
    ap.add_argument("--ratings", help="JSON from /api/leaderboard/bradley_terry")
    ap.add_argument("--stats", help="JSON from /api/model_stats")
    ap.add_argument("--period", default=None)
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    export = load(args.export)
    rows = match_rows(export)
    # Record WHICH files produced the report. A report nobody can trace back
    # to its inputs is an opinion; printing the exact paths makes every
    # number in here checkable by re-running the pipeline.
    supplied = {k: v for k, v in (
        ("matches", args.export), ("previous month", args.prev_export),
        ("leaderboard", args.leaderboard), ("objective", args.objective),
        ("metrics", args.metrics), ("balance", args.balance),
        ("bradley-terry ratings", args.ratings),
        ("model stats", args.stats)) if v}
    ctx = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "period": args.period,
        "notes": args.note,
        "sources": supplied,
        "benchmark_version": (export or {}).get("benchmark_version")
                             or (rows[0].get("benchmark_version") if rows else None)
                             or "1.0",
        "fingerprint": (rows[0].get("spec_fingerprint") if rows else None),
        "data_quality": section_data_quality(rows, export),
        "volume": section_volume(rows),
        "reliability": section_reliability(rows, load(args.metrics)),
        "rankings": section_rankings(load(args.leaderboard),
                                     load(args.objective),
                                     match_rows(load(args.prev_export))),
        "balance": load(args.balance),
        "ratings": section_ratings(load(args.ratings), load(args.stats)),
    }
    md = render(ctx)
    if args.out:
        p = pathlib.Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        print(f"  → report: {p}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
