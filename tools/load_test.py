#!/usr/bin/env python3
"""Concurrency load test (action-plan §20).

Measures what the deployment can actually absorb: 1 / 5 / 25 / 100
concurrent matches, plus a read-only pass that hammers the cheap endpoints
a status page would poll.

Design notes:
  * uses `mock:` fighters by default — these cost no tokens and no money,
    so the test measures OUR capacity (queue, worker, physics, storage),
    not a provider's rate limit. Use `--model` to test the real path
    against your own quota if you want end-to-end numbers.
  * submits in waves, polls the queue, and reports per-wave completion,
    wall clock, and error rate.
  * fails loudly (exit 1) if the failure rate exceeds `--max-failure-rate`,
    so it can gate a deploy.

Usage:
    # against a local dev server
    python3 tools/load_test.py --backend http://localhost:8000 --waves 1,5,25

    # reads only (safe against production)
    python3 tools/load_test.py --read-only --rps 5 --seconds 20

    # gate a deploy: fail if >5% of matches error
    python3 tools/load_test.py --waves 25 --max-failure-rate 0.05
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request


def _get(base, path, timeout=30):
    with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(base, path, body, timeout=30):
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def read_only_pass(base, rps, seconds):
    """Hammer the cheap endpoints and report latency."""
    print(f"read-only: {rps} req/s for {seconds}s against {base}")
    lat, errors, stop = [], [], time.time() + seconds
    lock = threading.Lock()

    def worker():
        while time.time() < stop:
            t0 = time.time()
            try:
                _get(base, "/api/health", timeout=10)
                _get(base, "/api/metrics", timeout=10)
                with lock:
                    lat.append((time.time() - t0) * 1000)
            except Exception as e:
                with lock:
                    errors.append(str(e)[:120])
            time.sleep(1.0 / max(1, rps))

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(max(1, rps))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if lat:
        lat.sort()
        print(f"  requests: {len(lat)}  errors: {len(errors)}")
        print(f"  latency ms: p50 {lat[len(lat)//2]:.0f}  "
              f"p95 {lat[min(len(lat)-1, int(.95*len(lat)))]:.0f}  "
              f"max {lat[-1]:.0f}")
    return {"requests": len(lat), "errors": len(errors),
            "p95_ms": (lat[min(len(lat) - 1, int(.95 * len(lat)))]
                       if lat else None)}


def match_wave(base, n, model_a, model_b, length, timeout_s, poll=1.0):
    """Submit n matches at once and wait for all to settle."""
    t0 = time.time()
    ids, submit_errors = [], []
    lock = threading.Lock()

    def submit(_):
        try:
            r = _post(base, "/api/match", {
                "model_a": model_a, "model_b": model_b, "sharp": ["tip"],
                "match_length": length, "fallback_policy": "operational"})
            with lock:
                ids.append(r["match_id"])
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:160]
            except Exception:
                pass
            with lock:
                submit_errors.append(f"HTTP {e.code}: {body}")
        except Exception as e:
            with lock:
                submit_errors.append(str(e)[:160])

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    done, failed, pending = [], [], list(ids)
    while pending and time.time() - t0 < timeout_s:
        time.sleep(poll)
        still = []
        for mid in pending:
            try:
                st = _get(base, f"/api/match/{mid}", timeout=10)
            except Exception as e:
                failed.append({"match_id": mid, "error": str(e)[:120]})
                continue
            if st.get("status") == "done":
                done.append(st)
            elif st.get("status") == "error":
                failed.append({"match_id": mid,
                               "error": st.get("error") or "error"})
            else:
                still.append(mid)
        pending = still

    elapsed = time.time() - t0
    turns = [d.get("turns") for d in done if d.get("turns")]
    return {
        "concurrency": n,
        "submitted": len(ids),
        "submit_errors": submit_errors,
        "completed": len(done),
        "failed": len(failed) + len(submit_errors),
        "timeout": len(pending),
        "elapsed_s": round(elapsed, 1),
        "throughput_per_min": round(len(done) / (elapsed / 60), 2) if elapsed else 0,
        "avg_turns": round(statistics.mean(turns), 1) if turns else None,
        "failure_rate": round((len(failed) + len(submit_errors)) / max(1, n), 4),
        "errors": failed[:5],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--waves", default="1,5,25",
                    help="comma list of concurrency levels")
    ap.add_argument("--model", default="mock:duelist")
    ap.add_argument("--model-b", default="mock:berserker")
    ap.add_argument("--length", default="sprint",
                    choices=["sprint", "standard", "full"])
    ap.add_argument("--timeout", type=float, default=900,
                    help="seconds to wait for a whole wave")
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--rps", type=int, default=5)
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--max-failure-rate", type=float, default=0.05)
    ap.add_argument("--out", default=None, help="write JSON results here")
    args = ap.parse_args(argv)

    base = args.backend.rstrip("/")
    try:
        health = _get(base, "/api/health")
    except Exception as e:
        print(f"backend unreachable at {base}: {e}")
        return 2
    print(f"backend {base}: up={health.get('up')} "
          f"queue={health.get('queue')} version={health.get('version')}")

    results = {"backend": base, "at": time.time(),
               "read_only": None, "waves": []}
    if args.read_only:
        results["read_only"] = read_only_pass(base, args.rps, args.seconds)

    worst = 0.0
    for n in [int(x) for x in args.waves.split(",") if x.strip()]:
        print(f"\nwave: {n} concurrent matches ({args.length})…")
        r = match_wave(base, n, args.model, args.model_b, args.length,
                       args.timeout)
        results["waves"].append(r)
        worst = max(worst, r["failure_rate"])
        print(f"  completed {r['completed']}/{n} in {r['elapsed_s']}s "
              f"({r['throughput_per_min']} matches/min) — "
              f"failures {r['failed']}, timeouts {r['timeout']}, "
              f"failure rate {r['failure_rate']}")
        if r["errors"]:
            for e in r["errors"][:3]:
                print(f"    ! {e}")

    print("\n=== capacity summary ===")
    print(f"{'conc':>6} {'done':>6} {'min':>8} {'thru/min':>10} {'fail%':>8}")
    for r in results["waves"]:
        print(f"{r['concurrency']:>6} {r['completed']:>6} "
              f"{r['elapsed_s']:>8} {r['throughput_per_min']:>10} "
              f"{r['failure_rate']*100:>7.1f}%")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n→ {args.out}")

    if worst > args.max_failure_rate:
        print(f"\nFAIL: worst failure rate {worst} exceeds "
              f"{args.max_failure_rate}")
        return 1
    print(f"\nPASS: worst failure rate {worst} within {args.max_failure_rate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
