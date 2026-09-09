#!/usr/bin/env python3
"""Versioned public dataset release (action-plan §27, next-step priority 3).

Builds a self-describing release directory in the Hugging Face layout:

    <out-dir>/<version>/
        README.md            dataset card: what, how, licence, reproduction
        MANIFEST.json        version, source, counts, benchmark/prompt/physics
                             versions, spec fingerprint, data-quality summary,
                             SHA-256 of every file
        SCHEMA.json          data dictionary: every column of every table
        SHA256SUMS           sha256sum-compatible
        matches/matches.{jsonl,csv,parquet}   one row per finished match
        votes/votes.{jsonl,csv,parquet}       one row per human vote
        events/events.{jsonl,csv,parquet}     hits/clashes from replays
        actions/actions.{jsonl,csv,parquet}   per-turn decisions + provenance

Parquet is written when pyarrow/pandas are importable, otherwise skipped
and said so in the manifest. Every table goes through a column
**whitelist** (`TABLES`), so nothing leaves the database that is not in
the data dictionary: no API keys, no provider headers, no prompts, no IPs,
no user ids (none are stored, but the whitelist is the guarantee, not the
absence). `error` text is dropped for the same reason.

Sources:
    --backend URL   /api/export for matches+votes, /api/replay/{id} for
                    events/actions (pass --replays 0 to skip the per-match
                    fetch)
    --db PATH       a local arena.db + sibling replays/ directory (offline)

Verification (the "results regenerable from exported data" criterion):
    python3 tools/export_dataset.py verify <out-dir>/<version>
re-hashes every file against SHA256SUMS and refits the Bradley–Terry
ranking from matches+votes in the release, printing it next to the
`ratings_snapshot` recorded in MANIFEST.json at export time.

Usage:
    # offline, from a local database
    python3 tools/export_dataset.py build --db stickblade/arena_data/arena.db \\
        --out-dir research/exports --version v2026.09.09

    # from a running backend (rate-limit friendly, resumes nothing: it's a snapshot)
    python3 tools/export_dataset.py build --backend https://<host> \\
        --out-dir research/exports --version v2026.09.09 --replays 500

    python3 tools/export_dataset.py verify research/exports/v2026.09.09
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stickblade"))

DEFAULT_BACKEND = "https://pioneer37-stickman-arena.hf.space"
DATASET_ID = "Pioneer37/stickblade-matches"
LICENSE = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
REPO = "https://github.com/Cometbuster4969/STICKBLADE-ARENA"

# ------------------------------------------------------------ dictionary
# (name, type, description). Order = column order in CSV/Parquet. This IS
# the whitelist: a column not listed here is not exported.
TABLES = {
    "matches": [
        ("match_id", "string", "Match id (12 hex). Join key for votes/events/actions."),
        ("created", "float", "Unix epoch (UTC) the match was created."),
        ("dataset_version", "string", "Release this row was exported in."),
        ("benchmark_version", "string", "Frozen ruleset version (docs/BENCHMARK_SPEC.md)."),
        ("physics_version", "string", "Simulation ruleset version (benchmark.PHYSICS_VERSION; bumped on any physics change). The pymunk engine version is in the spec, not per row."),
        ("prompt_version", "int", "System-prompt version (brains.PROMPT_VERSION). Ratings are not comparable across versions."),
        ("spec_fingerprint", "string", "12-hex hash of the benchmark spec (benchmark.py --fingerprint)."),
        ("seed", "int|null", "RNG seed. null = unseeded (not reproducible)."),
        ("match_length", "string", "sprint (4 turns) | standard (12) | full (24)."),
        ("max_turns", "int|null", "Turn cap actually applied."),
        ("fallback_policy", "string", "strict | operational | demo (see METHODOLOGY.md)."),
        ("model_a", "string", "Model REQUESTED for slot A (request order)."),
        ("model_b", "string", "Model REQUESTED for slot B (request order)."),
        ("flip", "int", "1 = model_a was rendered as canvas side B. All *_a/*_b provenance/metric columns and winner_side are in CANVAS order; use flip to map back to model_a/model_b."),
        ("model_used_a", "string|null", "Model that actually answered for canvas side A (after any fallback)."),
        ("model_used_b", "string|null", "Same for canvas side B."),
        ("provider_used_a", "string|null", "openrouter | groq | openai | google | scripted | error … for canvas A."),
        ("provider_used_b", "string|null", "Same for canvas B."),
        ("evidence", "string", "real_provider | mixed_provider | scripted_baseline (from provider_used_*)."),
        ("ranking_eligible", "int|null", "1 = counted toward ratings (no fallback under strict, both sides LLM, seeded…)."),
        ("fallback_used", "int|null", "1 = at least one turn was decided by a fallback (buddy model or scripted)."),
        ("fallback_turns_a", "int|null", "Turns decided by fallback, canvas A."),
        ("fallback_turns_b", "int|null", "Turns decided by fallback, canvas B."),
        ("invalid_actions_a", "int|null", "Turns where canvas A returned an invalid action/footwork."),
        ("invalid_actions_b", "int|null", "Same for canvas B."),
        ("latency_ms_a", "float|null", "Mean decision latency, canvas A (wall clock, ms)."),
        ("latency_ms_b", "float|null", "Same for canvas B."),
        ("prompt_tokens_a", "int|null", "Provider-billed prompt tokens, canvas A (0/null for scripted)."),
        ("completion_tokens_a", "int|null", "Provider-billed completion tokens, canvas A."),
        ("prompt_tokens_b", "int|null", "Prompt tokens, canvas B."),
        ("completion_tokens_b", "int|null", "Completion tokens, canvas B."),
        ("api_calls_a", "int|null", "Provider calls incl. retries, canvas A."),
        ("api_calls_b", "int|null", "Same for canvas B."),
        ("sharp", "string", "Comma list of sharp weapon zones (e.g. tip)."),
        ("weapon", "string", "sword | flail | bow."),
        ("mode", "string", "macro (action vocabulary) | joint (raw joint control)."),
        ("arena", "string", "normal | ice | low_gravity."),
        ("blindfolded", "int", "1 = derived spatial hints stripped from the state."),
        ("blind", "int", "1 = model identities hidden from the voter until after voting."),
        ("status", "string", "Always 'done' in a release (queued/running/error rows are not exported); kept so tools that filter on status work unchanged."),
        ("winner_side", "string|null", "a | b | draw — CANVAS side."),
        ("method", "string|null", "kill | points | timeout_draw | mutual_destruction | …"),
        ("turns", "int|null", "Turns played."),
        ("damage_dealt_a", "float|null", "HP removed by canvas A."),
        ("damage_dealt_b", "float|null", "HP removed by canvas B."),
        ("hits_landed_a", "int|null", "Hits landed by canvas A."),
        ("hits_landed_b", "int|null", "Hits landed by canvas B."),
        ("hits_attempted_a", "int|null", "Attack actions attempted by canvas A."),
        ("hits_attempted_b", "int|null", "Attack actions attempted by canvas B."),
        ("avg_distance", "float|null", "Mean inter-fighter distance at decision time (px)."),
        ("voted", "int", "1 = at least one human vote exists."),
        ("votes_total", "int", "Number of votes on this match."),
        ("votes_a", "int", "Votes for canvas A (tactical axis)."),
        ("votes_b", "int", "Votes for canvas B."),
        ("votes_draw", "int", "Draw votes."),
        ("votes_expert", "int", "Votes from self-declared expert tier."),
        ("votes_casual", "int", "Votes from casual tier."),
        ("has_replay", "int", "1 = events/actions rows for this match are in this release."),
    ],
    "votes": [
        ("vote_id", "string", "Vote id (random)."),
        ("match_id", "string", "Match voted on."),
        ("created", "float", "Unix epoch (UTC)."),
        ("choice", "string", "a | b | draw — tactical vote, CANVAS side. This is the only axis that moves ratings."),
        ("execution", "string|null", "a | b | draw | null — who executed better."),
        ("entertainment", "string|null", "a | b | draw | null — who was more fun to watch."),
        ("deserved", "string|null", "a | b | draw | null — did the winner deserve it."),
        ("confidence", "int|null", "Self-reported 1–5."),
        ("voter_tier", "string", "casual | expert (self-declared, unverified)."),
    ],
    "events": [
        ("match_id", "string", "Match."),
        ("frame", "int", "Replay frame index (30 fps sampling)."),
        ("kind", "string", "hit | clash."),
        ("by", "string|null", "Attacker CANVAS side for hits: a | b; null for clashes."),
        ("x", "float", "World x (px)."),
        ("y", "float", "World y (px)."),
        ("damage", "float", "HP removed (0 for clashes)."),
        ("sharp", "int", "1 = a sharp zone connected."),
        ("lethal", "int", "1 = this hit ended the match."),
        ("part", "string", "Body part struck (head, torso, …) or empty."),
    ],
    "actions": [
        ("match_id", "string", "Match."),
        ("turn", "int", "1-based turn."),
        ("side", "string", "a | b — CANVAS side."),
        ("action", "string|null", "Macro action chosen (thrust, guard, …) or 'joints' in joint mode."),
        ("footwork", "string|null", "advance | retreat | lunge | hop_back | hold | …"),
        ("joints", "string|null", "JSON object of joint commands (joint mode only)."),
        ("fire", "int|null", "1 = released an arrow this turn (bow, joint mode)."),
        ("model", "string|null", "Model that produced this decision (after fallback)."),
        ("provider", "string|null", "Provider that served it."),
        ("latency_ms", "float|null", "Decision latency for this turn."),
        ("fallback", "int", "1 = decided by a fallback."),
        ("invalid", "int", "1 = the reply was invalid and was sanitised."),
        ("thought", "string|null", "Model's one-line stated intent (public in the app; not a prompt)."),
    ],
}

# ----------------------------------------------------------------- input
def fetch_json(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def load_backend(backend, since=None, until=None, limit=50000, replays=200,
                 verbose=True):
    q = {"fmt": "json", "limit": str(limit), "include_votes": "1"}
    if since is not None:
        q["since"] = str(since)
    if until is not None:
        q["until"] = str(until)
    payload = fetch_json(f"{backend.rstrip('/')}/api/export?"
                         f"{urllib.parse.urlencode(q)}")
    rows = payload.get("matches", [])
    replay_map = {}
    for i, r in enumerate(rows[:max(0, replays)]):
        try:
            replay_map[r["id"]] = fetch_json(
                f"{backend.rstrip('/')}/api/replay/{r['id']}", timeout=60)
        except (urllib.error.URLError, ValueError) as e:
            if verbose:
                print(f"  replay {r['id']} skipped: {e}")
        if verbose and i and i % 50 == 0:
            print(f"  replays: {i}/{min(len(rows), replays)}")
    meta = {"source": backend, "export_prompt_version": payload.get("prompt_version"),
            "exported_at": payload.get("exported_at")}
    return rows, replay_map, meta


def load_db(db_path, since=None, until=None, limit=50000, replays=10**9):
    from storage import LocalStorage
    root = pathlib.Path(db_path).resolve().parent
    store = LocalStorage(root=str(root))
    rows = store.export_matches(since=since, until=until, limit=limit,
                                include_votes=True)
    replay_map = {}
    for r in rows[:max(0, replays)]:
        rep = store.get_replay(r["id"])
        if rep:
            replay_map[r["id"]] = rep
    return rows, replay_map, {"source": f"local:{db_path}"}


# ---------------------------------------------------------------- tables
def _int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(bool(v))


def build_tables(rows, replay_map, dataset_version):
    """Whitelisted, flat tables from export rows + replay dicts."""
    import data_quality as DQ
    matches, votes, events, actions = [], [], [], []
    for r in rows:
        vs = r.get("votes") or []
        rep = replay_map.get(r.get("id"))
        m = {k: r.get(k) for k, _, _ in TABLES["matches"]}
        m["match_id"] = r.get("id")
        m["dataset_version"] = dataset_version
        m["evidence"] = r.get("evidence") or DQ.evidence_class(r)
        for k in ("flip", "blindfolded", "blind", "voted", "ranking_eligible",
                  "fallback_used"):
            m[k] = _int(r.get(k))
        m["votes_total"] = len(vs)
        m["votes_a"] = sum(1 for v in vs if v.get("choice") == "a")
        m["votes_b"] = sum(1 for v in vs if v.get("choice") == "b")
        m["votes_draw"] = sum(1 for v in vs if v.get("choice") == "draw")
        m["votes_expert"] = sum(1 for v in vs
                                if (v.get("voter_tier") or "casual") == "expert")
        m["votes_casual"] = m["votes_total"] - m["votes_expert"]
        m["has_replay"] = int(rep is not None)
        matches.append(m)
        for v in vs:
            votes.append({
                "vote_id": v.get("id"), "match_id": r.get("id"),
                "created": v.get("created"), "choice": v.get("choice"),
                "execution": v.get("execution"),
                "entertainment": v.get("entertainment"),
                "deserved": v.get("deserved"), "confidence": v.get("confidence"),
                "voter_tier": v.get("voter_tier") or "casual"})
        if rep:
            events.extend(_events_from_replay(r["id"], rep))
            actions.extend(_actions_from_replay(r["id"], rep))
    return {"matches": matches, "votes": votes, "events": events,
            "actions": actions}


def _side_of(name, meta):
    p1 = (meta.get("p1") or {}).get("name")
    p2 = (meta.get("p2") or {}).get("name")
    return "a" if name == p1 else "b" if name == p2 else None


def _events_from_replay(mid, rep):
    meta = rep.get("meta") or {}
    out = []
    for e in rep.get("events") or []:
        out.append({"match_id": mid, "frame": e.get("f"), "kind": e.get("k"),
                    "by": _side_of(e.get("by"), meta) if e.get("by") else None,
                    "x": e.get("x"), "y": e.get("y"), "damage": e.get("d"),
                    "sharp": _int(e.get("s")), "lethal": _int(e.get("l")),
                    "part": e.get("part") or ""})
    return out


def _actions_from_replay(mid, rep):
    meta = rep.get("meta") or {}
    log = {a.get("turn"): a for a in meta.get("action_log") or []}
    tel = {t.get("turn"): t for t in (meta.get("telemetry") or {}).get("turns") or []}
    thoughts = {}
    for th in rep.get("thoughts") or []:
        thoughts[th.get("turn")] = th
    out = []
    for turn in sorted(set(log) | set(tel)):
        a, t, th = log.get(turn, {}), tel.get(turn, {}), thoughts.get(turn, {})
        for side in ("a", "b"):
            d, tt = a.get(side) or {}, t.get(side) or {}
            joints = d.get("joints")
            out.append({
                "match_id": mid, "turn": turn, "side": side,
                "action": d.get("action"), "footwork": d.get("footwork"),
                "joints": json.dumps(joints, separators=(",", ":"))
                if joints is not None else None,
                "fire": _int(d.get("fire")) if "fire" in d else None,
                "model": tt.get("model"), "provider": tt.get("provider"),
                "latency_ms": tt.get("latency_ms"),
                "fallback": _int(tt.get("fallback")) or 0,
                "invalid": _int(tt.get("invalid")) or 0,
                "thought": th.get(side)})
    return out


# --------------------------------------------------------------- writers
def _cols(table):
    return [c for c, _, _ in TABLES[table]]


def to_jsonl(table, rows):
    cols = _cols(table)
    return "\n".join(json.dumps({c: r.get(c) for c in cols},
                                separators=(",", ":"), ensure_ascii=False,
                                default=str)
                     for r in rows) + ("\n" if rows else "")


def to_csv(table, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_cols(table), extrasaction="ignore",
                       restval="")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def to_parquet(table, rows, path):
    try:
        import pandas as pd
    except ImportError:
        return None
    cols = _cols(table)
    df = pd.DataFrame([{c: r.get(c) for c in cols} for r in rows],
                      columns=cols)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception as e:                       # noqa: BLE001
        print(f"  (parquet skipped for {table}: {e})")
        return None


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def schema_doc(dataset_version):
    return {
        "dataset": DATASET_ID, "dataset_version": dataset_version,
        "layout": {t: f"{t}/{t}.{{jsonl,csv,parquet}}" for t in TABLES},
        "join_keys": {"votes.match_id": "matches.match_id",
                      "events.match_id": "matches.match_id",
                      "actions.match_id": "matches.match_id"},
        "side_convention": (
            "All *_a/*_b columns, winner_side, votes.choice, events.by and "
            "actions.side are CANVAS sides (A = green/left, B = blue/right). "
            "matches.model_a/model_b are in REQUEST order; matches.flip = 1 "
            "means model_a fought as canvas B. To credit a vote to a model: "
            "model = model_b if flip else model_a for choice 'a', and vice "
            "versa. ratings.preference_pairs_from_votes() does exactly this."),
        "tables": {t: [{"name": n, "type": ty, "description": d}
                       for n, ty, d in cols] for t, cols in TABLES.items()},
        "excluded_by_design": [
            "API keys, provider request headers, BYOK residue",
            "system/user prompts (see stickblade/brains.py in the tagged code release)",
            "IP addresses, user identifiers (never stored)",
            "commentary and error text",
            "replay frame arrays (fetch /api/replay/{match_id} if needed)",
        ],
    }


def ratings_snapshot(tables, bootstraps=200):
    """Refit Bradley–Terry from the release tables — the number a verifier
    must be able to reproduce from the files alone."""
    from ratings import fit_with_ci, preference_pairs_from_votes
    by_mid = {m["match_id"]: m for m in tables["matches"]}
    joined = []
    for v in tables["votes"]:
        m = by_mid.get(v["match_id"])
        if not m:
            continue
        joined.append({"model_a": m["model_a"], "model_b": m["model_b"],
                       "flip": m["flip"], "choice": v["choice"],
                       "ranking_eligible": bool(m["ranking_eligible"])
                       if m["ranking_eligible"] is not None else True})
    pairs = preference_pairs_from_votes(joined)
    rows = fit_with_ci(pairs, bootstraps=bootstraps)
    return {"model": "bradley-terry-davidson", "comparisons": len(pairs),
            "bootstraps": bootstraps,
            "rows": [{k: r.get(k) for k in ("model", "rating", "ci_low",
                                            "ci_high", "matches", "wins",
                                            "losses", "draws")} for r in rows]}


def write_release(tables, out_dir, dataset_version, src_meta, bootstraps=200):
    import data_quality as DQ
    out = pathlib.Path(out_dir) / dataset_version
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for t, rows in tables.items():
        d = out / t
        d.mkdir(exist_ok=True)
        (d / f"{t}.jsonl").write_text(to_jsonl(t, rows), encoding="utf-8")
        (d / f"{t}.csv").write_text(to_csv(t, rows), encoding="utf-8")
        files[t] = {"rows": len(rows), "formats": ["jsonl", "csv"]}
        if to_parquet(t, rows, str(d / f"{t}.parquet")):
            files[t]["formats"].append("parquet")
    matches = tables["matches"]
    created = [m["created"] for m in matches if m.get("created")]
    versions = sorted({str(m.get("benchmark_version")) for m in matches} - {"None"})
    prompts = sorted({str(m.get("prompt_version")) for m in matches} - {"None"})
    fps = sorted({str(m.get("spec_fingerprint")) for m in matches} - {"None"})
    physics = sorted({str(m.get("physics_version")) for m in matches} - {"None"})
    # data_quality.summary wants provider_used_* keys — the matches table has them.
    dq = DQ.summary(matches) if matches else DQ.summary([])
    snap = ratings_snapshot(tables, bootstraps=bootstraps)
    manifest = {
        "dataset": DATASET_ID, "dataset_version": dataset_version,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": src_meta.get("source"),
        "code": REPO,
        "license": LICENSE, "license_url": LICENSE_URL,
        "cite": f"{REPO}/blob/main/CITATION.cff",
        "counts": {t: len(rows) for t, rows in tables.items()},
        "date_range": {"min": min(created) if created else None,
                       "max": max(created) if created else None},
        "benchmark_versions": versions, "prompt_versions": prompts,
        "physics_versions": physics, "spec_fingerprints": fps,
        "data_quality": dq,
        "ratings_snapshot": snap,
        "files": files,
        "hashes": {},        # filled below
        "reproduce": [
            f"python3 tools/export_dataset.py verify <dir>/{dataset_version}",
            "python3 tools/benchmark_report.py --export "
            f"<dir>/{dataset_version}/matches/matches.jsonl --out report.md",
        ],
    }
    (out / "SCHEMA.json").write_text(json.dumps(schema_doc(dataset_version),
                                                indent=2), encoding="utf-8")
    (out / "README.md").write_text(render_readme(manifest), encoding="utf-8")
    # Hash everything except MANIFEST.json / SHA256SUMS themselves.
    hashes = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name not in ("MANIFEST.json", "SHA256SUMS"):
            hashes[str(p.relative_to(out))] = sha256_file(p)
    manifest["hashes"] = hashes
    (out / "SHA256SUMS").write_text(
        "".join(f"{h}  {n}\n" for n, h in hashes.items()), encoding="utf-8")
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2,
                                                  default=str),
                                       encoding="utf-8")
    return out, manifest


def render_readme(man):
    dq = man["data_quality"]
    c = man["counts"]
    lines = [
        "---",
        f"license: {LICENSE.lower()}",
        "task_categories: [reinforcement-learning, other]",
        "language: [en]",
        "tags: [llm-benchmark, physics, embodied, pairwise-preference, bradley-terry]",
        f"pretty_name: STICKBLADE ARENA matches {man['dataset_version']}",
        "configs:",
    ]
    for t in TABLES:
        lines += [f"  - config_name: {t}", f"    data_files: {t}/{t}.jsonl"]
    lines += [
        "---", "",
        f"# STICKBLADE ARENA — match dataset `{man['dataset_version']}`", "",
        "LLM-vs-LLM sword/bow duels in a 2-D ragdoll physics arena, judged by "
        "blind human votes. Every row carries the provenance needed to say who "
        "actually decided each turn and whether the match counts toward a "
        "ranking.", "",
        "## What is in this release", "",
        "| table | rows | one row per |", "|---|---:|---|",
        f"| `matches` | {c['matches']} | finished match |",
        f"| `votes` | {c['votes']} | human vote (anonymous) |",
        f"| `events` | {c['events']} | hit / clash in a replay |",
        f"| `actions` | {c['actions']} | (turn, side) decision with model, provider, latency |",
        "",
        f"Generated {man['generated_at']} from `{man['source']}`. "
        f"Benchmark version(s): {', '.join(man['benchmark_versions']) or 'n/a'}; "
        f"prompt version(s): {', '.join(man['prompt_versions']) or 'n/a'}; "
        f"physics: {', '.join(man['physics_versions']) or 'n/a'}; "
        f"spec fingerprint(s): {', '.join(man['spec_fingerprints']) or 'n/a'}.",
        "",
        "## Data quality — read this before ranking anything", "",
        f"* evidence level: **`{dq.get('evidence_level')}`**",
        f"* {dq.get('real_provider_matches', 0)} real-provider matches, "
        f"{dq.get('mixed_provider_matches', 0)} mixed, "
        f"{dq.get('scripted_matches', 0)} scripted-baseline",
        f"* {dq.get('fallback_matches', 0)} matches used a fallback; "
        f"{dq.get('silent_fallback_matches', 0)} of those are still marked "
        "ranking-eligible (should be 0)",
        f"* token coverage on real-provider sides: "
        f"{dq.get('token_coverage') if dq.get('token_coverage') is not None else 'n/a'}",
        "",
        "Scripted-baseline rows (`evidence = scripted_baseline`) validate the "
        "pipeline and say nothing about any language model. Filter on "
        "`evidence` and `ranking_eligible` before fitting anything.", "",
        "## Side convention (the one thing people get wrong)", "",
        "`*_a`/`*_b`, `winner_side`, `votes.choice`, `events.by`, `actions.side` "
        "are **canvas** sides. `matches.model_a/model_b` are in **request** "
        "order; `flip = 1` means `model_a` fought as canvas B. See "
        "`SCHEMA.json → side_convention`.", "",
        "## Reproduce the ranking", "",
        "```bash",
        f"pip install pandas pyarrow    # optional, for parquet",
        f"python3 tools/export_dataset.py verify {man['dataset_version']}/",
        "```",
        "",
        "`verify` re-hashes every file against `SHA256SUMS` and refits the "
        "Bradley–Terry (Davidson ties) model with bootstrap CIs from "
        "`matches` + `votes`, then prints it beside `ratings_snapshot` in "
        "`MANIFEST.json`. Two models are only called different when their "
        "95 % intervals do not overlap.", "",
        f"* code: {REPO}",
        "* methodology: `STICKBLADE-ARENA/METHODOLOGY.md`",
        "* frozen ruleset: `STICKBLADE-ARENA/docs/BENCHMARK_SPEC.md`", "",
        "## What is deliberately not here", "",
    ]
    lines += [f"* {x}" for x in schema_doc(man["dataset_version"])["excluded_by_design"]]
    lines += ["", "## Licence", "",
              f"Data: [{LICENSE}]({LICENSE_URL}). Code: Apache-2.0. "
              f"Cite via `CITATION.cff` in the repository.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- verify
def verify_release(release_dir, bootstraps=200, verbose=True):
    d = pathlib.Path(release_dir)
    man = json.loads((d / "MANIFEST.json").read_text())
    bad = []
    for line in (d / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        h, name = line.split("  ", 1)
        p = d / name
        if not p.exists() or sha256_file(p) != h:
            bad.append(name)
    tables = {}
    for t in TABLES:
        p = d / t / f"{t}.jsonl"
        tables[t] = ([json.loads(l) for l in p.read_text().splitlines() if l]
                     if p.exists() else [])
    counts_ok = all(len(tables[t]) == man["counts"].get(t, 0) for t in TABLES)
    snap = ratings_snapshot(tables, bootstraps=bootstraps)
    recorded = man.get("ratings_snapshot", {})
    point_ok = ([(r["model"], round(r["rating"], 1)) for r in snap["rows"]]
                == [(r["model"], round(r["rating"], 1))
                    for r in recorded.get("rows", [])])
    ok = not bad and counts_ok and point_ok
    if verbose:
        print(f"release {man['dataset_version']} from {man['source']}")
        print(f"  hashes: {'OK' if not bad else 'MISMATCH ' + str(bad)}")
        print(f"  row counts match manifest: {counts_ok}")
        print(f"  ratings refit: {snap['comparisons']} comparisons, "
              f"{len(snap['rows'])} models, point estimates "
              f"{'match' if point_ok else 'DIFFER from'} manifest")
        for r in snap["rows"]:
            print(f"    {r['model']:40s} {r['rating']:7.1f} "
                  f"[{r['ci_low']:.0f}, {r['ci_high']:.0f}] n={r['matches']}")
        if not snap["rows"]:
            print("    (no voted, ranking-eligible matches — nothing to rank)")
        print(f"  evidence level: {man['data_quality'].get('evidence_level')}")
        print("  RESULT:", "VERIFIED" if ok else "FAILED")
    return ok, {"hash_mismatches": bad, "counts_ok": counts_ok,
                "ratings_match": point_ok, "refit": snap}


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write a versioned release directory")
    src = b.add_mutually_exclusive_group()
    src.add_argument("--backend", default=None)
    src.add_argument("--db", default=None)
    b.add_argument("--out-dir", required=True)
    b.add_argument("--version", default=None,
                   help="release tag, default v<YYYY.MM.DD>")
    b.add_argument("--since", type=float, default=None, help="unix epoch")
    b.add_argument("--until", type=float, default=None, help="unix epoch")
    b.add_argument("--limit", type=int, default=50000)
    b.add_argument("--replays", type=int, default=200,
                   help="max per-match replays to fetch for events/actions "
                        "(backend only; --db reads all)")
    b.add_argument("--bootstraps", type=int, default=200)
    v = sub.add_parser("verify", help="check hashes + refit ratings")
    v.add_argument("release_dir")
    v.add_argument("--bootstraps", type=int, default=200)
    args = ap.parse_args(argv)

    if args.cmd == "verify":
        ok, _ = verify_release(args.release_dir, bootstraps=args.bootstraps)
        return 0 if ok else 1

    version = args.version or time.strftime("v%Y.%m.%d")
    if args.db:
        rows, replays, meta = load_db(args.db, args.since, args.until, args.limit)
    else:
        rows, replays, meta = load_backend(args.backend or DEFAULT_BACKEND,
                                           args.since, args.until, args.limit,
                                           replays=args.replays)
    print(f"loaded {len(rows)} matches, {len(replays)} replays from {meta['source']}")
    tables = build_tables(rows, replays, version)
    out, man = write_release(tables, args.out_dir, version, meta,
                             bootstraps=args.bootstraps)
    for t, n in man["counts"].items():
        print(f"  {t:8s} {n:7d} rows  ({', '.join(man['files'][t]['formats'])})")
    print(f"  evidence level: {man['data_quality'].get('evidence_level')}")
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
