# Deployment guide

Two deployable units: a **FastAPI backend** (Docker, currently Hugging Face
Spaces) and a **Next.js frontend** (Vercel). They are independent — the
frontend points at the backend through `NEXT_PUBLIC_API_BASE`.

---

## Backend

### Docker (works on HF Spaces, Render, Railway, Fly, any VM)

```bash
docker build -t stickblade-arena .
docker run --rm -p 7860:7860 \
  -e SDL_VIDEODRIVER=dummy \
  -e OPENROUTER_API_KEY=sk-or-... \
  -e GROQ_API_KEY=gsk_... \
  -e SUPABASE_URL=https://xxx.supabase.co \
  -e SUPABASE_KEY=eyJ... \
  stickblade-arena
```

The image sets `SDL_VIDEODRIVER=dummy` and listens on **7860** (the HF Spaces
convention). Override the port with `PORT` or by changing the `CMD`.

Post-deploy checks:

```bash
curl $BACKEND/api/health    # {"up": true, "has_openrouter": true, ...}
curl $BACKEND/api/version   # prompt_version must match what the frontend expects
curl $BACKEND/api/status    # component health + spec fingerprint
```

### Hugging Face Spaces

1. Create a Space → SDK **Docker** → push this repo's contents (the
   `Dockerfile` is at the repo root of `STICKBLADE-ARENA/stickblade/` for the
   backend-only image, and at `STICKBLADE-ARENA/Dockerfile` for the whole repo).
2. Add the secrets in *Settings → Repository secrets*: `OPENROUTER_API_KEY`,
   `GROQ_API_KEY`, and — if using Postgres — `SUPABASE_URL` / `SUPABASE_KEY`.
3. Spaces sleep after inactivity. The frontend pings `/api/health` every 5
   minutes from open tabs, which keeps it warm; cold starts are still ~30–60 s
   and are the #1 cause of fallback turns.

### Bare metal / VM

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r stickblade/requirements.txt
export SDL_VIDEODRIVER=dummy STICKBLADE_DATA_DIR=/var/lib/stickblade
cd stickblade && uvicorn server:app --host 0.0.0.0 --port 8000
```

Run it under systemd or a supervisor; there is no built-in process manager.

---

## Storage: SQLite vs Supabase

- **No `SUPABASE_URL`** → local SQLite under `STICKBLADE_DATA_DIR`
  (default `arena_data/`). Fine for development; **not** suitable for
  multi-instance or ephemeral-filesystem hosting (an HF Space restart loses it).
- **`SUPABASE_URL` + `SUPABASE_KEY`** → Postgres via the REST API. Run
  `stickblade/supabase_schema.sql` first; it is idempotent
  (`add column if not exists`), so re-running it after an upgrade is safe.

Both backends degrade gracefully: if a column doesn't exist yet the write is
retried without it, so a partially migrated database keeps serving matches.

---

## Frontend (Vercel)

1. Import `stickblade-web/` as the project root.
2. Set `NEXT_PUBLIC_API_BASE` to the deployed backend origin
   (e.g. `https://pioneer37-stickman-arena.hf.space`). Leave it empty only for
   local dev, where the Next server proxies `/api/*` to `BACKEND_ORIGIN`.
3. Build command `next build`, output `.next`. No server-side secrets.

The Content-Security-Policy is generated in `next.config.mjs` and includes the
backend origin in `connect-src`. **If you change the backend URL, update
`API_ORIGIN` in `next.config.mjs`** or every API call will be blocked by the
browser.

---

## Frontend + backend on one origin

The default dev setup proxies `/api/*` through Next, which is also a valid
production topology (one container, no CORS). To do that:

```bash
BACKEND_ORIGIN=http://127.0.0.1:8000 next build && next start
# with NEXT_PUBLIC_API_BASE left empty
```

---

## Post-deploy checklist

- [ ] `/api/health` reports the provider keys you expect
- [ ] `/api/version` `prompt_version` matches the value the frontend was built against
- [ ] `/api/benchmark/spec` fingerprint is the one in [docs/BENCHMARK_SPEC.md](./BENCHMARK_SPEC.md) (`09de66effd02` for prompt v2; `029281ed627a` was prompt v1)
- [ ] A scripted match runs end to end and votes: `./tools/run_match.py verify …`
- [ ] `CORS_ORIGINS` includes the frontend origin
- [ ] Rate limits are production values, not the relaxed test values
- [ ] `docker logs` shows no `storage: local SQLite` warning where you expect Postgres

## Rollback

Ratings are keyed by the version triple. If a deploy changes physics or
prompting without a version bump, **previously recorded matches become
non-comparable and there is no clean rollback that fixes the data** — you have
to segment by version. This is why the spec is frozen and the fingerprint is
asserted in CI.
