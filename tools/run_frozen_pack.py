#!/usr/bin/env python3
"""
Stickblade Arena — Frozen Eval Pack v1 runner
==============================================

Reads research/frozen_pack_v1.yaml, submits each match to the live backend
(POST /api/match), polls until done (GET /api/match/{mid}), appends the
result to a CSV. Resumable — if the CSV already has a row for match i,
it's skipped.

Usage:
    # dry run (validate config + roster, don't dispatch matches)
    python3 tools/run_frozen_pack.py --dry-run

    # real run (default)
    python3 tools/run_frozen_pack.py

    # rerun a specific range (after fixing something)
    python3 tools/run_frozen_pack.py --start 40 --end 60

    # target a different backend (local dev)
    python3 tools/run_frozen_pack.py --backend http://localhost:8000

Output:
    research/frozen_pack_v1_results.csv    - one row per match completed
    research/frozen_pack_v1_errors.jsonl   - one line per match that errored

Rate-limit awareness:
    Backend caps at 50 matches/hour/IP (security.py:RL_MATCHES_PER_HOUR).
    Runner throttles itself to 40 matches/hour by default (~90s between
    match submissions). Full 100-match pack takes ~2.5 hours.

Idempotency:
    Match i's outcome is written atomically after the backend reports
    status=done. If the runner is killed mid-pack, restart and it skips
    completed rows. Errored rows are NOT skipped on restart (retry logic
    is intentional — most errors are transient rate limits).
"""
from __future__ import annotations
import argparse
import csv
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows-safe stdout: force UTF-8 so print() can emit ρ, τ, —, ≥ etc.
# Python on Windows defaults stdout to cp1252 which crashes on these chars.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = pathlib.Path(__file__).parent.parent
PACK_PATH = HERE / "research" / "frozen_pack_v1.yaml"
RESULTS_CSV = HERE / "research" / "frozen_pack_v1_results.csv"
ERRORS_JSONL = HERE / "research" / "frozen_pack_v1_errors.jsonl"

# CSV schema — locked at v1. Adding columns is safe; renaming or removing
# is a breaking change for downstream consumers (notebook / dataset dump).
CSV_HEADER = [
    "i", "seed", "weapon", "sharp",
    "model_a", "model_b",
    "match_id", "backend_prompt_version",
    "status", "winner_side", "winner_model", "method", "turns",
    "damage_dealt_a", "damage_dealt_b",
    "hits_landed_a", "hits_landed_b",
    "hits_attempted_a", "hits_attempted_b",
    "fallback_turns_a", "fallback_turns_b",
    "avg_distance",
    "error", "duration_sec", "completed_at",
]


# ---------- YAML parsing (no pyyaml dep) ----------

def load_pack():
    matches = []
    header = {}
    in_matches = False
    # encoding="utf-8" required — the YAML contains em-dashes and other
    # non-ASCII characters that Windows cp1252 default can't decode.
    for raw in PACK_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("matches:"):
            in_matches = True
            continue
        if in_matches and line.startswith("- {"):
            d = {}
            for part in line[3:-1].split(","):
                k, _, v = part.partition(":")
                d[k.strip()] = v.strip()
            d["i"] = int(d["i"])
            d["seed"] = int(d["seed"])
            matches.append(d)
        elif not in_matches and ":" in line:
            k, _, v = line.partition(":")
            # Strip inline "# comment" tails from values (YAML allows them)
            v = v.split("#", 1)[0]
            header[k.strip()] = v.strip().strip('"')
    return header, matches


# ---------- HTTP helpers (stdlib only) ----------

def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "frozen-pack-runner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_post(url, body, timeout=30):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": "frozen-pack-runner/1.0",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------- Pre-flight checks ----------

def preflight(backend, header):
    """Fail fast if the backend is down or on a different PROMPT_VERSION."""
    print(f"Pre-flight against {backend}")
    ver = http_get(f"{backend}/api/version", timeout=10)
    print(f"  backend version={ver.get('version')} prompt_version={ver.get('prompt_version')}")
    required = int(header.get("prompt_version_required", 1))
    if ver.get("prompt_version") != required:
        print(f"❌ ABORT: pack requires prompt_version={required}, "
              f"backend reports prompt_version={ver.get('prompt_version')}")
        print(f"   Bump pack_version and regenerate before running.")
        sys.exit(2)

    health = http_get(f"{backend}/api/health", timeout=10)
    print(f"  backend health up={health.get('up')} queue={health.get('queue')}")
    if not health.get("up"):
        print(f"❌ ABORT: backend reports up=false")
        sys.exit(2)

    models = http_get(f"{backend}/api/models", timeout=10)
    roster = {m["id"] for m in models}
    print(f"  roster size={len(roster)}")
    return roster


# ---------- Match dispatch ----------

def submit_match(backend, m):
    """POST /api/match. Returns the match_id."""
    body = {
        "model_a": m["model_a"],
        "model_b": m["model_b"],
        "sharp":   [m["sharp"]],
        "weapon":  m["weapon"],
        "blind":   True,           # Frozen-pack matches are NOT for public
                                   # vote; blind so the reveal panel doesn't
                                   # leak identity if someone stumbles on
                                   # the match id via /replay.
        "mode":    "macro",
        "arena":   "normal",
        "blindfolded": False,
    }
    return http_post(f"{backend}/api/match", body, timeout=30)


def poll_until_done(backend, mid, max_wait_sec=600):
    """Poll /api/match/{mid} every 5s until status ∈ {done, error}."""
    started = time.time()
    while True:
        elapsed = time.time() - started
        if elapsed > max_wait_sec:
            return {"status": "timeout", "error": f"runner-side timeout after {elapsed:.0f}s"}
        try:
            m = http_get(f"{backend}/api/match/{mid}", timeout=15)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Match got _delayed_clear()'d before we polled. Rare but
                # possible on fast matches.
                return {"status": "gone", "error": "match no longer in backend cache"}
            raise
        if m.get("status") in ("done", "error"):
            return m
        time.sleep(5)


# ---------- CSV persistence ----------

def load_completed_ids():
    """Return set of match indices already in results.csv."""
    if not RESULTS_CSV.exists():
        return set()
    # encoding="utf-8" for Windows compatibility (Python default is cp1252
    # on Windows, which barfs on non-ASCII in commentary strings).
    with RESULTS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {int(row["i"]) for row in reader if row.get("i")}


def ensure_csv_header():
    """Create the CSV with header if it doesn't exist."""
    if RESULTS_CSV.exists():
        return
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()


def append_result(row):
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writerow(row)


def append_error(m, err_msg):
    ERRORS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with ERRORS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "i": m.get("i"), "seed": m.get("seed"),
            "weapon": m.get("weapon"), "sharp": m.get("sharp"),
            "model_a": m.get("model_a"), "model_b": m.get("model_b"),
            "error": err_msg,
            "at": time.time(),
        }) + "\n")


# ---------- Main loop ----------

def run(backend, matches, roster, throttle_sec, poll_wait_sec):
    ensure_csv_header()
    completed = load_completed_ids()
    if completed:
        print(f"Resuming: {len(completed)} matches already in "
              f"{RESULTS_CSV.name}, will skip those")

    remaining = [m for m in matches if m["i"] not in completed]
    print(f"To run: {len(remaining)} matches")
    print(f"Throttle: {throttle_sec}s between submissions "
          f"(~{3600/throttle_sec:.0f} matches/hour)")
    print(f"Poll timeout: {poll_wait_sec}s per match")
    print()

    total_started = time.time()
    for idx, m in enumerate(remaining, 1):
        # Roster sanity — skip matches referencing dead models
        for slot in ("model_a", "model_b"):
            if m[slot] not in roster:
                msg = f"model {m[slot]} not in current roster"
                print(f"[{m['i']:3d}] SKIP: {msg}")
                append_error(m, msg)
                break
        else:
            # Both models valid, dispatch
            print(f"[{m['i']:3d}] {m['weapon']:6s} sharp={m['sharp']:9s} "
                  f"seed={m['seed']}  {m['model_a'][:35]:35s} vs {m['model_b'][:35]:35s} ",
                  end="", flush=True)
            match_start = time.time()
            try:
                resp = submit_match(backend, m)
                mid = resp["match_id"]
                result = poll_until_done(backend, mid, max_wait_sec=poll_wait_sec)
            except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
                dur = time.time() - match_start
                msg = f"{type(e).__name__}: {e}"
                print(f"ERR ({dur:.0f}s): {msg}")
                append_error(m, msg)
                # Still throttle after errors so we don't hammer a dead backend
                time.sleep(throttle_sec)
                continue

            dur = time.time() - match_start

            if result.get("status") != "done":
                err = result.get("error") or f"status={result.get('status')}"
                print(f"NOT-DONE ({dur:.0f}s): {err}")
                append_error(m, err)
                time.sleep(throttle_sec)
                continue

            # Success → record. Note: /api/match returns only public fields;
            # to get the objective proxy metrics (damage_dealt_a etc) we hit
            # /api/export?limit=1 filtered on this mid. Simpler: fetch the
            # single match from export.
            try:
                exp = http_get(
                    f"{backend}/api/export?fmt=json&limit=1000", timeout=30)
                match_row = next(
                    (x for x in exp.get("matches", []) if x["id"] == mid), None)
            except Exception:
                match_row = None

            winner_side = result.get("engine_winner_side") or (
                match_row.get("winner_side") if match_row else None)
            # winner_model = whichever slot won. flip randomization is
            # server-side; result already includes canvas_a_model/canvas_b_model
            # after reveal, but for frozen pack we care about the ORIGINAL pick
            # order (model_a, model_b as passed in). Compute from winner_side.
            if winner_side == "a":
                winner_model = m["model_a"]
            elif winner_side == "b":
                winner_model = m["model_b"]
            else:
                winner_model = ""  # draw

            row = {
                "i": m["i"], "seed": m["seed"],
                "weapon": m["weapon"], "sharp": m["sharp"],
                "model_a": m["model_a"], "model_b": m["model_b"],
                "match_id": mid,
                "backend_prompt_version": (match_row or {}).get("prompt_version", ""),
                "status": "done",
                "winner_side": winner_side or "",
                "winner_model": winner_model,
                "method": result.get("method") or "",
                "turns": result.get("turns") or 0,
                "damage_dealt_a":    (match_row or {}).get("damage_dealt_a", ""),
                "damage_dealt_b":    (match_row or {}).get("damage_dealt_b", ""),
                "hits_landed_a":     (match_row or {}).get("hits_landed_a", ""),
                "hits_landed_b":     (match_row or {}).get("hits_landed_b", ""),
                "hits_attempted_a":  (match_row or {}).get("hits_attempted_a", ""),
                "hits_attempted_b":  (match_row or {}).get("hits_attempted_b", ""),
                "fallback_turns_a":  (match_row or {}).get("fallback_turns_a", ""),
                "fallback_turns_b":  (match_row or {}).get("fallback_turns_b", ""),
                "avg_distance":      (match_row or {}).get("avg_distance", ""),
                "error": "",
                "duration_sec": round(dur, 1),
                "completed_at": time.time(),
            }
            append_result(row)
            print(f"DONE ({dur:.0f}s) winner={winner_side or 'draw':4s} turns={row['turns']}")

        # Progress + throttle
        elapsed_min = (time.time() - total_started) / 60
        remaining_est = elapsed_min * (len(remaining) - idx) / max(idx, 1)
        print(f"    ({idx}/{len(remaining)} done · elapsed {elapsed_min:.1f}min "
              f"· eta {remaining_est:.1f}min)")

        if idx < len(remaining):
            time.sleep(throttle_sec)

    print()
    print("=" * 72)
    print(f"Complete. Results: {RESULTS_CSV}")
    if ERRORS_JSONL.exists():
        print(f"Errors: {ERRORS_JSONL}  (review before rerunning)")
    print("Next step: re-run research/cross_benchmark_correlation.py")
    print("           with an updated data-load path that reads this CSV.")


def dry_run(backend, matches, roster):
    print(f"DRY RUN — no matches submitted")
    print(f"Pack size: {len(matches)}")
    unknown = set()
    for m in matches:
        for slot in ("model_a", "model_b"):
            if m[slot] not in roster:
                unknown.add(m[slot])
    if unknown:
        print(f"⚠  {len(unknown)} models NOT in current live roster:")
        for u in sorted(unknown):
            print(f"    {u}")
        print("   Fix the pack (or wait for the roster to include them) "
              "before running for real.")
    else:
        print("✅ All 21 models in the pack are live on the backend.")
    print(f"Estimated total runtime at 40 matches/hour: "
          f"~{len(matches) / 40 * 60:.0f} minutes = {len(matches) / 40:.1f} hours")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None,
                    help="Backend base URL (default: from pack header)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate config + roster, don't dispatch")
    ap.add_argument("--start", type=int, default=None,
                    help="Skip matches with i < start")
    ap.add_argument("--end", type=int, default=None,
                    help="Skip matches with i > end")
    ap.add_argument("--throttle-sec", type=float, default=90.0,
                    help="Seconds between match submissions (default 90 = "
                         "40/hour, under the 50/hour backend limit)")
    ap.add_argument("--poll-wait-sec", type=int, default=600,
                    help="Runner-side timeout per match (default 600 = 10min)")
    args = ap.parse_args()

    if not PACK_PATH.exists():
        print(f"ERROR: pack file not found: {PACK_PATH}")
        sys.exit(1)

    header, matches = load_pack()
    backend = args.backend or header.get("backend_base_url",
                                         "https://pioneer37-stickman-arena.hf.space")
    backend = backend.rstrip("/")

    # Filter by --start / --end
    if args.start is not None:
        matches = [m for m in matches if m["i"] >= args.start]
    if args.end is not None:
        matches = [m for m in matches if m["i"] <= args.end]

    roster = preflight(backend, header)
    print()

    if args.dry_run:
        dry_run(backend, matches, roster)
        return

    run(backend, matches, roster,
        throttle_sec=args.throttle_sec,
        poll_wait_sec=args.poll_wait_sec)


if __name__ == "__main__":
    main()
