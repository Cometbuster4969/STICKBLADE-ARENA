#!/usr/bin/env python3
"""Controlled real-provider calibration batch (next-step priority 1).

The benchmark's infrastructure is validated by 200+ tests; its *model*
conclusions are not, because almost every stored match was fought by
scripted baselines. The first real-provider run must therefore be a
**calibration** of the measurement pipeline, not a tournament:

    * 4–6 models across as many providers as are configured
    * 2 weapons × 2 arenas × 2 control modes
    * a fixed, recorded seed set
    * equal colour (canvas side) assignment per pair
    * N matches per matchup (20–30 for a powered pair)
    * strict no-fallback research mode
    * full token + latency capture

Every run is stored with the field list the plan asks for:

    benchmark_version  prompt_version  physics_version  spec_fingerprint
    model_requested_{a,b}  model_used_{a,b}  provider_{a,b}  seed  weapon
    arena  control_mode  sharp  match_length  fallback_policy  voter_tier
    latency_ms_{a,b}  latency_ms_max_{a,b}  prompt_tokens_{a,b}
    completion_tokens_{a,b}  api_calls_{a,b}  fallback_status
    eligibility_status  evidence  status  winner_model  method  turns

and the runner finishes with an **acceptance audit** against the criteria
in the plan: 100 % provider + model identified, 100 % eligibility status
recorded, no silent fallback in strict mode, ≥ 95 % token coverage (or the
gap reported), failed matches retained but excluded from outcomes.

Two execution paths share one plan format:

    --local     run in-process through tools/simcore.py. Works offline
                with mock:/bot: fighters (pipeline dry-run, always
                scripted evidence) and with real models when the provider
                keys are in the environment (no server needed).
    --backend   dispatch to a running server via POST /api/match and read
                results back from /api/export, so the batch lands in the
                same database the leaderboard reads. Resumable.

Usage:
    # 1. plan only — inspect the design, count matches, estimate cost
    python3 tools/run_calibration_batch.py plan \\
        --models groq:llama-3.3-70b-versatile,openai/gpt-oss-20b:free,\\
                 google/gemma-4-31b-it:free,groq:openai/gpt-oss-120b \\
        --n 20 --out research/calibration/2026-09/plan.json

    # 2. offline pipeline dry-run with scripted fighters (no keys)
    python3 tools/run_calibration_batch.py run --local \\
        --models bot:pro,mock:duelist,bot:greedy,bot:distance --n 4 \\
        --out-dir research/calibration/dry-run

    # 3. the real thing, against a backend with keys configured
    python3 tools/run_calibration_batch.py run --backend http://localhost:8000 \\
        --plan research/calibration/2026-09/plan.json \\
        --out-dir research/calibration/2026-09

    # 4. audit an existing results file against the acceptance criteria
    python3 tools/run_calibration_batch.py audit \\
        research/calibration/2026-09/results.jsonl
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "stickblade"))

import simcore  # noqa: E402

DEFAULT_WEAPONS = ("sword", "bow")
DEFAULT_ARENAS = ("normal", "ice")
DEFAULT_MODES = ("macro", "joint")
DEFAULT_LENGTH = "standard"
DEFAULT_POLICY = "strict"
DEFAULT_BASE_SEED = 20260909

# Default sharp zone per weapon: the first zone in WEAPON_ZONES, resolved at
# plan time so the plan file is explicit about what was fought.
RESULT_FIELDS = [
    "run_id", "batch_id", "idx", "pair_id", "cell_id", "flip",
    "benchmark_version", "physics_version", "prompt_version",
    "spec_fingerprint",
    "model_requested_a", "model_requested_b", "model_used_a", "model_used_b",
    "provider_a", "provider_b", "seed", "weapon", "arena", "control_mode",
    "sharp", "match_length", "fallback_policy", "voter_tier",
    "latency_ms_a", "latency_ms_b", "latency_ms_max_a", "latency_ms_max_b",
    "prompt_tokens_a", "completion_tokens_a", "prompt_tokens_b",
    "completion_tokens_b", "api_calls_a", "api_calls_b",
    "invalid_actions_a", "invalid_actions_b", "fallback_turns_a",
    "fallback_turns_b", "fallback_status", "eligibility_status", "evidence",
    "status", "error", "match_id", "winner_side", "winner_model", "method",
    "turns", "damage_a", "damage_b", "wall_s", "created",
]


# ------------------------------------------------------------------ plan
def provider_of(model_id: str) -> str:
    """Provider a roster id is routed to (mirrors brains.make_brain)."""
    m = (model_id or "").lower()
    if m.startswith(("bot:", "mock:", "scripted:")):
        return "scripted"
    if m.startswith("groq:"):
        return "groq"
    if m in ("gpt",):
        return "openai"
    if m in ("gemini",):
        return "google"
    if "/" in m:
        return "openrouter"
    return "unknown"


def build_plan(models, n_per_pair=20, weapons=DEFAULT_WEAPONS,
               arenas=DEFAULT_ARENAS, modes=DEFAULT_MODES,
               match_length=DEFAULT_LENGTH, fallback_policy=DEFAULT_POLICY,
               base_seed=DEFAULT_BASE_SEED, sharps=None, run_id=None):
    """Balanced plan: every unordered pair × every configuration cell.

    Within a pair, matches alternate canvas side (flip) so each model plays
    equally often as Fighter A and as Fighter B — and, because cells are
    also rotated, each model is on each side equally often *within* every
    cell whenever `n_per_pair` is a multiple of 2 × |cells|. Seeds are
    `base_seed + global index`, so the plan is fully reproducible from the
    header alone.
    """
    from weapons import WEAPON_ZONES
    models = list(dict.fromkeys(models))            # dedupe, keep order
    if len(models) < 2:
        raise ValueError("need at least two models")
    sharps = sharps or {w: WEAPON_ZONES[w][0] for w in weapons}
    cells = list(itertools.product(weapons, arenas, modes))
    if n_per_pair % (2 * len(cells)):
        print(f"  note: n={n_per_pair} is not a multiple of 2×{len(cells)} "
              f"cells — sides/cells will be as balanced as n allows",
              file=sys.stderr)
    run_id = run_id or time.strftime("cal-%Y%m%d-%H%M%S")
    matches = []
    g = 0
    for a, b in itertools.combinations(models, 2):
        pair_id = f"{a}|{b}"
        for i in range(n_per_pair):
            weapon, arena, mode = cells[i % len(cells)]
            # flip alternates every time the SAME cell recurs for this
            # pair, so within each cell the sides are balanced.
            flip = bool((i // len(cells)) % 2)
            matches.append({
                "idx": g, "pair_id": pair_id, "flip": flip,
                "model_a": a, "model_b": b,
                "left": b if flip else a, "right": a if flip else b,
                "weapon": weapon, "arena": arena, "control_mode": mode,
                "sharp": sharps[weapon], "seed": base_seed + g,
                "cell_id": f"{weapon}/{arena}/{mode}",
            })
            g += 1
    header = {
        "run_id": run_id, "created": time.time(),
        "models": models,
        "providers": sorted({provider_of(m) for m in models}),
        "n_per_pair": n_per_pair, "pairs": len(models) * (len(models) - 1) // 2,
        "weapons": list(weapons), "arenas": list(arenas), "modes": list(modes),
        "cells": [f"{w}/{a}/{m}" for w, a, m in cells],
        "sharps": sharps, "match_length": match_length,
        "fallback_policy": fallback_policy, "base_seed": base_seed,
        "total_matches": len(matches),
        "design": ("balanced: every unordered pair × every cell, sides "
                   "alternated per cell, seed = base_seed + idx"),
    }
    return {"header": header, "matches": matches}


def plan_summary(plan):
    h = plan["header"]
    by_provider = {}
    for m in h["models"]:
        by_provider.setdefault(provider_of(m), []).append(m)
    lines = [f"calibration plan {h['run_id']}",
             f"  models ({len(h['models'])}): " + ", ".join(h["models"]),
             f"  providers: " + ", ".join(
                 f"{p} ×{len(ms)}" for p, ms in sorted(by_provider.items())),
             f"  cells ({len(h['cells'])}): " + ", ".join(h["cells"]),
             f"  {h['pairs']} pairs × {h['n_per_pair']} = "
             f"{h['total_matches']} matches, {h['match_length']} length, "
             f"{h['fallback_policy']} policy, seeds from {h['base_seed']}"]
    if len(by_provider) < 2 or "scripted" in by_provider:
        lines.append("  ⚠ fewer than 2 real providers in this plan — fine "
                     "for a pipeline dry-run, not for a calibration claim")
    # Side balance check per model.
    side = {}
    for m in plan["matches"]:
        side.setdefault(m["left"], [0, 0])[0] += 1
        side.setdefault(m["right"], [0, 0])[1] += 1
    worst = max(abs(l - r) for l, r in side.values())
    lines.append(f"  side balance: max |left−right| per model = {worst}"
                 + ("" if worst <= 1 else "  ⚠ unbalanced"))
    return "\n".join(lines)


# --------------------------------------------------------------- helpers
def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append_jsonl(path, row):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")


def _load_jsonl(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def _fallback_status(fb_turns_a, fb_turns_b, policy):
    fb = (fb_turns_a or 0) + (fb_turns_b or 0)
    if fb == 0:
        return "none"
    return "excluded" if policy == "strict" else "used"


def _eligibility_status(eligible, status):
    if status != "done":
        return "failed"
    return "ranking_eligible" if eligible else "excluded"


def _base_row(plan, m, mode_label):
    h = plan["header"]
    return {
        "run_id": h["run_id"], "batch_id": mode_label, "idx": m["idx"],
        "pair_id": m["pair_id"], "cell_id": m["cell_id"], "flip": m["flip"],
        "model_requested_a": m["left"], "model_requested_b": m["right"],
        "seed": m["seed"], "weapon": m["weapon"], "arena": m["arena"],
        "control_mode": m["control_mode"], "sharp": m["sharp"],
        "match_length": h["match_length"],
        "fallback_policy": h["fallback_policy"],
        # Votes are collected later, by humans; a calibration batch has no
        # voter, and saying so explicitly beats leaving the field out.
        "voter_tier": None,
        "created": time.time(),
    }


def _finish_row(row, prov, metrics, result_status, winner_side, method,
                turns, dmg_a, dmg_b, wall_s, error=None, match_id=None):
    import data_quality as DQ
    policy = row["fallback_policy"]
    fb_a = int((metrics or {}).get("fallback_turns_a") or 0)
    fb_b = int((metrics or {}).get("fallback_turns_b") or 0)
    eligible = bool(prov.get("ranking_eligible", True)) if prov else False
    row.update({
        "benchmark_version": prov.get("benchmark_version"),
        "physics_version": prov.get("physics_version"),
        "prompt_version": prov.get("prompt_version"),
        "spec_fingerprint": prov.get("spec_fingerprint"),
        "model_used_a": prov.get("model_used_a"),
        "model_used_b": prov.get("model_used_b"),
        "provider_a": prov.get("provider_used_a"),
        "provider_b": prov.get("provider_used_b"),
        "latency_ms_a": prov.get("latency_ms_a"),
        "latency_ms_b": prov.get("latency_ms_b"),
        "latency_ms_max_a": prov.get("latency_ms_max_a"),
        "latency_ms_max_b": prov.get("latency_ms_max_b"),
        "prompt_tokens_a": prov.get("prompt_tokens_a"),
        "completion_tokens_a": prov.get("completion_tokens_a"),
        "prompt_tokens_b": prov.get("prompt_tokens_b"),
        "completion_tokens_b": prov.get("completion_tokens_b"),
        "api_calls_a": prov.get("api_calls_a"),
        "api_calls_b": prov.get("api_calls_b"),
        "invalid_actions_a": prov.get("invalid_actions_a"),
        "invalid_actions_b": prov.get("invalid_actions_b"),
        "fallback_turns_a": fb_a, "fallback_turns_b": fb_b,
        "fallback_status": _fallback_status(fb_a, fb_b, policy),
        "eligibility_status": _eligibility_status(eligible, result_status),
        # A failed match has no provenance; labelling it "scripted" would
        # quietly inflate the scripted tally in the audit. None = unknown.
        "evidence": (DQ.evidence_class({
            "provider_used_a": prov.get("provider_used_a"),
            "provider_used_b": prov.get("provider_used_b")})
            if result_status == "done" and prov else None),
        "status": result_status, "error": error, "match_id": match_id,
        "winner_side": winner_side,
        "winner_model": (row["model_requested_a"] if winner_side == "a"
                         else row["model_requested_b"] if winner_side == "b"
                         else None),
        "method": method, "turns": turns,
        "damage_a": dmg_a, "damage_b": dmg_b, "wall_s": round(wall_s, 1),
    })
    return {k: row.get(k) for k in RESULT_FIELDS}


def _prepare_out_dir(plan, out_dir):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    simcore.write_json(out_dir / "plan.json", plan)
    return out_dir / "results.jsonl"


def finalize_run(plan, out_dir):
    """Audit results.jsonl and write results.csv / audit.json / audit.md.

    Separate from the runners so a batch that was interrupted (or run on
    another machine) can still be finalised from its results file.
    """
    out_dir = pathlib.Path(out_dir)
    rows = _load_jsonl(out_dir / "results.jsonl")
    a = audit(rows)
    simcore.write_json(out_dir / "audit.json", a)
    (out_dir / "audit.md").write_text(render_audit(a, plan["header"]),
                                      encoding="utf-8")
    simcore.write_csv(out_dir / "results.csv", rows, fields=RESULT_FIELDS)
    return a


# ------------------------------------------------------------ local run
def run_local(plan, out_dir, verbose=True, resume=True):
    """Run the plan in-process. Real models work if provider keys are set.

    Writes plan.json + results.jsonl (append, resumable) and then the
    audit/CSV via finalize_run(). Returns the audit dict.
    """
    simcore.bootstrap()
    results_path = _prepare_out_dir(plan, out_dir)
    done_idx = {r["idx"] for r in _load_jsonl(results_path)} if resume else set()
    h = plan["header"]
    total = h["total_matches"]
    for m in plan["matches"]:
        if m["idx"] in done_idx:
            continue
        row = _base_row(plan, m, "local")
        t0 = time.time()
        try:
            match, replay = simcore.run_headless_match(
                m["left"], m["right"], sharp=[m["sharp"]],
                weapon=m["weapon"], arena=m["arena"], mode=m["control_mode"],
                seed=m["seed"], match_length=h["match_length"],
                fallback_policy=h["fallback_policy"])
            meta = replay.get("meta") or {}
            prov = meta.get("provenance") or {}
            metrics = meta.get("metrics") or {}
            res = match.result or {}
            w = res.get("winner")
            side = "a" if w == match.f1.name else "b" if w == match.f2.name \
                else "draw"
            out = _finish_row(row, prov, metrics, "done", side,
                              res.get("method"), res.get("turns"),
                              metrics.get("damage_dealt_a"),
                              metrics.get("damage_dealt_b"),
                              time.time() - t0)
        except Exception as e:                       # noqa: BLE001
            # Failed matches are operational data: kept, flagged, excluded
            # from outcomes by eligibility_status.
            out = _finish_row(row, {}, {}, "error", None, None, None, None,
                              None, time.time() - t0, error=str(e)[:200])
        _append_jsonl(results_path, out)
        if verbose:
            print(f"  [{m['idx']+1:4d}/{total}] {out['cell_id']:22s} "
                  f"seed={out['seed']} {out['status']:5s} "
                  f"{out['evidence'] or '-':17s} fb={out['fallback_status']:8s} "
                  f"win={out['winner_model'] or out['winner_side'] or '-'}")
    return finalize_run(plan, out_dir)


# ---------------------------------------------------------- backend run
def _http(method, url, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"User-Agent": "calibration-batch/1.0",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


_SIDED = ("model_used", "provider_used", "latency_ms", "latency_ms_max",
          "prompt_tokens", "completion_tokens", "api_calls",
          "invalid_actions", "fallback_turns", "damage_dealt", "hits_landed",
          "hits_attempted")


def _unflip(row: dict) -> dict:
    """Return an export row re-keyed into request order (model_a, model_b).

    Storage keeps `model_a`/`model_b` in request order but every sided
    provenance column and `winner_side` in canvas order; `flip` links the
    two. Pure function so the test suite can pin it.
    """
    out = dict(row)
    if not row.get("flip"):
        return out
    for base in _SIDED:
        a, b = row.get(f"{base}_a"), row.get(f"{base}_b")
        out[f"{base}_a"], out[f"{base}_b"] = b, a
    ws = (row.get("winner_side") or "").lower()
    out["winner_side"] = "b" if ws == "a" else "a" if ws == "b" else ws
    return out


def preflight_backend(backend, plan):
    ver = _http("GET", f"{backend}/api/version", timeout=15)
    health = _http("GET", f"{backend}/api/health", timeout=15)
    print(f"  backend {backend}: version={ver.get('version')} "
          f"prompt_version={ver.get('prompt_version')} "
          f"up={health.get('up')} openrouter={health.get('has_openrouter')} "
          f"groq={health.get('has_groq')}")
    if not health.get("up"):
        raise SystemExit("backend reports up=false")
    need = set(plan["header"]["providers"]) - {"scripted", "unknown"}
    have = {p for p, ok in (("openrouter", health.get("has_openrouter")),
                            ("groq", health.get("has_groq"))) if ok}
    missing = need - have - {"openai", "google"}
    if missing:
        raise SystemExit(f"backend has no key for provider(s): "
                         f"{sorted(missing)} — a strict batch would be "
                         f"100% excluded. Configure the key or change the "
                         f"roster.")
    roster = {m["id"] for m in _http("GET", f"{backend}/api/models")}
    unknown = [m for m in plan["header"]["models"] if m not in roster
               and "/" not in m]
    if unknown:
        raise SystemExit(f"models not on backend roster: {unknown}")


def run_backend(plan, backend, out_dir, throttle_s=5.0, poll_s=4.0,
                max_wait_s=900, verbose=True, resume=True):
    backend = backend.rstrip("/")
    results_path = _prepare_out_dir(plan, out_dir)
    done_idx = {r["idx"] for r in _load_jsonl(results_path)} if resume else set()
    h = plan["header"]
    total = h["total_matches"]
    preflight_backend(backend, plan)
    for m in plan["matches"]:
        if m["idx"] in done_idx:
            continue
        row = _base_row(plan, m, "backend")
        t0 = time.time()
        try:
            created = _http("POST", f"{backend}/api/match", {
                "model_a": m["left"], "model_b": m["right"],
                "sharp": [m["sharp"]], "weapon": m["weapon"],
                "arena": m["arena"], "mode": m["control_mode"],
                "blind": True, "seed": m["seed"],
                "match_length": h["match_length"],
                "fallback_policy": h["fallback_policy"],
                # Pin canvas sides to request order. The plan already
                # alternates left/right per cell; letting the server
                # coin-flip on top would re-randomise the side balance,
                # and a seeded fight only replays for a FIXED side
                # assignment (physics is not left/right symmetric).
                # Older backends ignore the field; _unflip() covers that.
                "flip": False})
            mid = created["match_id"]
            st = None
            while time.time() - t0 < max_wait_s:
                st = _http("GET", f"{backend}/api/match/{mid}", timeout=20)
                if st.get("status") in ("done", "error"):
                    break
                time.sleep(poll_s)
            status = (st or {}).get("status") or "timeout"
            exp_row = None
            if status == "done":
                exp = _http("GET", f"{backend}/api/export?fmt=json&limit=200"
                            f"&since={int(t0) - 5}", timeout=60)
                exp_row = next((x for x in exp.get("matches", [])
                                if x.get("id") == mid), None)
            # The server assigns canvas sides at random for blind matches
            # and stores every *_a/*_b provenance column in CANVAS order
            # with `flip` = 1 meaning "model_a was rendered as canvas B".
            # This runner's rows are in REQUEST order (left, right), so the
            # export row must be un-flipped first — otherwise provider,
            # tokens and the winner are attributed to the wrong model in
            # half of all matches while everything still looks plausible.
            prov = _unflip(exp_row or {})
            metrics = {"fallback_turns_a": prov.get("fallback_turns_a"),
                       "fallback_turns_b": prov.get("fallback_turns_b")}
            out = _finish_row(row, prov, metrics, status,
                              prov.get("winner_side"), prov.get("method"),
                              prov.get("turns"), prov.get("damage_dealt_a"),
                              prov.get("damage_dealt_b"), time.time() - t0,
                              error=(st or {}).get("error"), match_id=mid)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            out = _finish_row(row, {}, {}, "error", None, None, None, None,
                              None, time.time() - t0,
                              error=f"HTTP {e.code}: {body}")
            if e.code in (429, 503):
                time.sleep(max(30.0, throttle_s * 4))
        except Exception as e:                       # noqa: BLE001
            out = _finish_row(row, {}, {}, "error", None, None, None, None,
                              None, time.time() - t0, error=str(e)[:200])
        _append_jsonl(results_path, out)
        if verbose:
            print(f"  [{m['idx']+1:4d}/{total}] {out['cell_id']:22s} "
                  f"seed={out['seed']} {out['status']:5s} "
                  f"{out['evidence'] or '-':17s} fb={out['fallback_status']:8s}"
                  f" tok={(out['prompt_tokens_a'] or 0)+(out['prompt_tokens_b'] or 0)}"
                  f" win={out['winner_model'] or out['winner_side'] or '-'}"
                  f" {out['wall_s']}s")
        time.sleep(throttle_s)
    return finalize_run(plan, out_dir)


# ----------------------------------------------------------------- audit
def audit(rows, token_coverage_min=0.95):
    """Acceptance audit against the next-step criteria. Pure function."""
    import data_quality as DQ
    n = len(rows)
    done = [r for r in rows if r.get("status") == "done"]
    failed = [r for r in rows if r.get("status") != "done"]
    real_sides = 0
    ident_ok = elig_ok = 0
    tok_ok = tok_missing = 0
    silent = []
    strict_fb_ranked = []
    lat = []
    for r in done:
        pa, pb = r.get("provider_a"), r.get("provider_b")
        if pa and pb and r.get("model_used_a") and r.get("model_used_b"):
            ident_ok += 1
        if r.get("eligibility_status") in ("ranking_eligible", "excluded"):
            elig_ok += 1
        for side in ("a", "b"):
            if DQ.is_real_provider(r.get(f"provider_{side}")):
                real_sides += 1
                toks = (r.get(f"prompt_tokens_{side}") or 0) + \
                       (r.get(f"completion_tokens_{side}") or 0)
                if toks > 0:
                    tok_ok += 1
                else:
                    tok_missing += 1
            if r.get(f"latency_ms_{side}") is not None:
                lat.append(float(r[f"latency_ms_{side}"]))
        if r.get("fallback_policy") == "strict" and \
                r.get("fallback_status") != "none" and \
                r.get("eligibility_status") == "ranking_eligible":
            silent.append(r.get("idx"))
        if r.get("fallback_policy") == "strict" and \
                r.get("fallback_status") != "none":
            strict_fb_ranked.append(r.get("idx"))
    lat.sort()
    pct = lambda p: (round(lat[min(len(lat) - 1, int(p * len(lat)))], 1)  # noqa: E731
                     if lat else None)
    ev = {"real_provider": 0, "mixed_provider": 0, "scripted_baseline": 0}
    for r in done:
        ev[r.get("evidence") or "scripted_baseline"] += 1
    tok_cov = (tok_ok / real_sides) if real_sides else None
    by_pair = {}
    for r in done:
        p = by_pair.setdefault(r["pair_id"], {"n": 0, "eligible": 0,
                                              "a_wins": 0, "b_wins": 0,
                                              "draws": 0, "left_a": 0})
        p["n"] += 1
        if r.get("eligibility_status") == "ranking_eligible":
            p["eligible"] += 1
        a, b = r["pair_id"].split("|", 1)
        w = r.get("winner_model")
        if w == a:
            p["a_wins"] += 1
        elif w == b:
            p["b_wins"] += 1
        else:
            p["draws"] += 1
        if r.get("model_requested_a") == a:
            p["left_a"] += 1
    checks = {
        "all_matches_identify_provider_and_model":
            (ident_ok == len(done), f"{ident_ok}/{len(done)}"),
        "all_matches_record_eligibility_status":
            (elig_ok == len(done), f"{elig_ok}/{len(done)}"),
        "no_silent_fallback_in_strict_mode":
            (not silent, f"{len(silent)} ranked strict matches fell back"
             + (f": idx {silent[:10]}" if silent else "")),
        "token_coverage_at_least_95pct_or_reported":
            (tok_cov is None or tok_cov >= token_coverage_min,
             "no real-provider sides" if tok_cov is None
             else f"{tok_cov:.1%} ({tok_ok}/{real_sides} real sides)"),
        "failed_matches_retained_not_ranked":
            (all(r.get("eligibility_status") == "failed" for r in failed),
             f"{len(failed)} failed, all flagged"),
        "real_provider_evidence_present":
            (ev["real_provider"] > 0,
             f"{ev['real_provider']} real / {ev['mixed_provider']} mixed / "
             f"{ev['scripted_baseline']} scripted"),
    }
    return {
        "generated": _now_iso(),
        "matches": n, "completed": len(done), "failed": len(failed),
        "evidence": ev,
        "strict_fallback_excluded": len(strict_fb_ranked),
        "token_coverage": None if tok_cov is None else round(tok_cov, 4),
        "token_missing_sides": tok_missing,
        "latency_ms": {"n": len(lat), "p50": pct(0.5), "p95": pct(0.95),
                       "max": lat[-1] if lat else None},
        "by_pair": by_pair,
        "checks": {k: {"pass": bool(v[0]), "detail": v[1]}
                   for k, v in checks.items()},
        "accepted": all(v[0] for v in checks.values()),
        "note": ("A passing audit validates the MEASUREMENT PIPELINE. It "
                 "says nothing about which model is better — that needs "
                 "the Bradley–Terry separability test on voted data."),
    }


def render_audit(a, header=None):
    L = ["# Calibration batch — acceptance audit", ""]
    if header:
        L += [f"**Run:** `{header.get('run_id')}`  ",
              f"**Models:** {', '.join('`%s` ' % m for m in header.get('models', []))}  ",
              f"**Design:** {header.get('pairs')} pairs × "
              f"{header.get('n_per_pair')} · cells: "
              f"{', '.join(header.get('cells', []))} · "
              f"{header.get('match_length')} · {header.get('fallback_policy')}"
              f" · seeds from {header.get('base_seed')}", ""]
    tok = a["token_coverage"]
    tok_txt = "n/a (no real-provider sides)" if tok is None else f"{tok:.1%}"
    L += [f"**Generated:** {a['generated']}  ",
          f"**Matches:** {a['matches']} ({a['completed']} completed, "
          f"{a['failed']} failed)  ",
          f"**Evidence:** {a['evidence']['real_provider']} real-provider · "
          f"{a['evidence']['mixed_provider']} mixed · "
          f"{a['evidence']['scripted_baseline']} scripted  ",
          f"**Token coverage:** {tok_txt}  ",
          f"**Decision latency:** p50 {a['latency_ms']['p50']} ms · "
          f"p95 {a['latency_ms']['p95']} ms · max {a['latency_ms']['max']} ms",
          "", "## Acceptance criteria", "",
          "| criterion | result | detail |", "|---|:---:|---|"]
    for k, v in a["checks"].items():
        L.append(f"| {k.replace('_', ' ')} | {'✅' if v['pass'] else '❌'} "
                 f"| {v['detail']} |")
    L += ["", f"**Overall: {'ACCEPTED' if a['accepted'] else 'NOT ACCEPTED'}**",
          "", "## Per pair", "",
          "| pair | n | eligible | A wins | B wins | draws | A on left |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for pid, p in a["by_pair"].items():
        L.append(f"| `{pid}` | {p['n']} | {p['eligible']} | {p['a_wins']} "
                 f"| {p['b_wins']} | {p['draws']} | {p['left_a']}/{p['n']} |")
    L += ["", a["note"], ""]
    return "\n".join(L)


# ------------------------------------------------------------------ main
def _parse_models(s):
    return [m.strip() for m in (s or "").split(",") if m.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _plan_args(p):
        p.add_argument("--models", help="comma list of roster ids (4–6)")
        p.add_argument("--n", type=int, default=20,
                       help="matches per pair (20–30 for a powered pair)")
        p.add_argument("--weapons", default=",".join(DEFAULT_WEAPONS))
        p.add_argument("--arenas", default=",".join(DEFAULT_ARENAS))
        p.add_argument("--modes", default=",".join(DEFAULT_MODES))
        p.add_argument("--length", default=DEFAULT_LENGTH,
                       choices=["sprint", "standard", "full"])
        p.add_argument("--fallback-policy", default=DEFAULT_POLICY,
                       choices=["strict", "operational", "demo"])
        p.add_argument("--base-seed", type=int, default=DEFAULT_BASE_SEED)
        p.add_argument("--run-id", default=None)
        p.add_argument("--plan", help="use an existing plan.json instead")

    pp = sub.add_parser("plan", help="build + print the balanced plan")
    _plan_args(pp)
    pp.add_argument("--out", help="write plan JSON here")

    pr = sub.add_parser("run", help="execute the plan")
    _plan_args(pr)
    g = pr.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", action="store_true")
    g.add_argument("--backend", help="base URL of a running server")
    pr.add_argument("--out-dir", required=True)
    pr.add_argument("--throttle-sec", type=float, default=5.0)
    pr.add_argument("--no-resume", action="store_true")
    pr.add_argument("--quiet", action="store_true")

    pa = sub.add_parser("audit", help="audit a results.jsonl")
    pa.add_argument("results")
    pa.add_argument("--plan", default=None)
    pa.add_argument("--out", default=None, help="write markdown here")

    args = ap.parse_args(argv)

    if args.cmd == "audit":
        rows = _load_jsonl(args.results)
        header = None
        if args.plan:
            header = json.loads(pathlib.Path(args.plan).read_text())["header"]
        a = audit(rows)
        md = render_audit(a, header)
        if args.out:
            pathlib.Path(args.out).write_text(md, encoding="utf-8")
            print(f"  → {args.out}")
        else:
            print(md)
        return 0 if a["accepted"] else 1

    simcore.bootstrap(quiet=True)
    if args.plan:
        plan = json.loads(pathlib.Path(args.plan).read_text())
    else:
        models = _parse_models(args.models)
        if not models:
            ap.error("--models or --plan is required")
        plan = build_plan(
            models, n_per_pair=args.n,
            weapons=tuple(_parse_models(args.weapons)),
            arenas=tuple(_parse_models(args.arenas)),
            modes=tuple(_parse_models(args.modes)),
            match_length=args.length, fallback_policy=args.fallback_policy,
            base_seed=args.base_seed, run_id=args.run_id)
    print(plan_summary(plan))

    if args.cmd == "plan":
        if args.out:
            simcore.write_json(args.out, plan)
            print(f"  → {args.out}")
        return 0

    out_dir = pathlib.Path(args.out_dir)
    if args.local:
        run_local(plan, out_dir, verbose=not args.quiet,
                  resume=not args.no_resume)
    else:
        run_backend(plan, args.backend, out_dir,
                    throttle_s=args.throttle_sec,
                    verbose=not args.quiet,
                    resume=not args.no_resume)
    a = finalize_run(plan, out_dir)
    print()
    print(render_audit(a, plan["header"]))
    print(f"  → {out_dir / 'results.jsonl'}\n  → {out_dir / 'results.csv'}\n"
          f"  → {out_dir / 'audit.md'}")
    return 0 if a["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
