# Capacity and load behaviour

Measured with `tools/load_test.py` against the real FastAPI app (no mocks,
real HTTP, real SQLite writes, real replays).

## What was measured

```bash
python3 tools/load_test.py --backend http://127.0.0.1:8000 --waves 1,5,25,100
```

- **Fighters:** `mock:` scripted brains, `sprint` (4 turns). This measures
  **our** capacity — queue, worker, physics, storage, replay writing — not a
  provider's rate limit.
- **Server:** single uvicorn worker, Python 3.11, local SQLite,
  `MAX_QUEUE=200`, rate limits raised.
- **Date:** 2026-09-09.

## Results

| Concurrency | Completed | Wall clock | Throughput | Failures | Timeouts |
|---:|---:|---:|---:|---:|---:|
| 1 | 1/1 | 1.0 s | 59 /min | 0 | 0 |
| 5 | 5/5 | 3.0 s | 99 /min | 0 | 0 |
| 25 | 25/25 | 13.5 s | 111 /min | 0 | 0 |
| 100 | 100/100 | 57.0 s | 105 /min | 0 | 0 |

Failure rate **0.0 %** at every wave (gate: ≤ 5 %).

## Reading these numbers

- **Throughput plateaus at ~105–110 matches/min.** It does not keep climbing
  with concurrency, which means the bottleneck is CPU-bound simulation in a
  single worker, not the queue or storage. More workers or a second instance
  is the fix if you need more than that.
- **100 concurrent matches did not drop a single request.** Admission control
  (`MAX_QUEUE`) rejects with `503 arena is busy` rather than letting the queue
  grow unbounded — at 200 queued the server said no instead of accepting work
  it could not finish.
- **This is the scripted-fighter ceiling, not the production number.** A real
  LLM match spends most of its wall clock waiting on a provider, so production
  throughput is *higher* in matches/min up to the provider's own rate limit,
  and per-match latency is *worse* (60–90 s vs ~1 s here). The load test
  isolates the part we control.

## What is NOT yet measured

- **Real-provider waves.** Running 100 concurrent LLM matches costs real money
  and trips free-tier rate limits. Use `--model` against your own quota:
  ```bash
  python3 tools/load_test.py --backend https://your-space.hf.space \
      --model openai/gpt-4o-mini --waves 1,5 --max-failure-rate 0.05
  ```
- **Read-only polling load** (what a status page would cost):
  ```bash
  python3 tools/load_test.py --read-only --rps 5 --seconds 30
  ```
- **Multi-worker / multi-instance.** Every number above is one process.
- **Postgres (Supabase) instead of SQLite.** Writes were local.

## Deploy gate

The tool exits non-zero when the failure rate exceeds `--max-failure-rate`, so
it can gate a release:

```yaml
- run: python3 tools/load_test.py --backend "$BACKEND" --waves 25 --max-failure-rate 0.05
```

Re-run it against your own deployment before trusting this table — hardware,
worker count and storage backend all move these numbers.
