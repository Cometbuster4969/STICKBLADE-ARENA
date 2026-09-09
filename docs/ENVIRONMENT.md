# Environment variable reference

Every knob the backend, the frontend and the offline tools read. Defaults are
in parentheses. Nothing here is required to run the arena offline — with no
provider key every fight falls back to scripted baselines and is flagged as
such in its provenance record.

## Backend (`stickblade/server.py`, `stickblade/security.py`)

### Model providers

| Variable | Default | What it does |
|---|---|---|
| `OPENROUTER_API_KEY` | *(none)* | OpenRouter key. Without it, OpenRouter models fall back to scripted brains (counted as fallback turns). |
| `GROQ_API_KEY` | *(none)* | Groq key — independent provider, separate free-tier ceiling. |
| `OPENAI_API_KEY` | *(none)* | Only used by `gpt:*` brains. |
| `GEMINI_API_KEY` | *(none)* | Only used by `gemini:*` brains. |
| `STICKBLADE_OPENAI_MODEL` | model-specific | Override the default model id for `gpt:*`. |
| `STICKBLADE_GEMINI_MODEL` | model-specific | Override the default model id for `gemini:*`. |
| `ALLOW_PAID_CUSTOM` | `0` | `1` lets users submit **paid** custom model ids. Default allows only `:free` and `mock:` customs — this is the spend ceiling, don't flip it casually. |

Per-match user keys (BYOK) come in the request body, not the environment, and
are never written to storage. See [SECURITY.md](../SECURITY.md).

### Rate limits and spend caps

| Variable | Default | What it does |
|---|---|---|
| `RL_MATCHES_PER_HOUR` | `50` | Matches one IP may start per hour. |
| `RL_VOTES_PER_HOUR` | `100` | Votes one IP may cast per hour. |
| `RL_REQS_PER_MIN` | `120` | Any API requests per IP per minute. |
| `MAX_QUEUE` | `10` | Pending simulations before new matches are rejected with `503 arena is busy`. |
| `MAX_MATCHES_PER_DAY` | `300` | Global daily cap — the LLM spend ceiling. |
| `ADMIN_TOKEN` | *(none)* | If set, requests carrying a matching `X-Admin-Token` header skip all rate limits. Use for your own load tests, never in production. |

The test suite raises these via `tests/conftest.py` so rapid-fire offline
matches don't hit `503 arena is busy`. It does **not** change the defaults
shipped to production.

### Storage

| Variable | Default | What it does |
|---|---|---|
| `SUPABASE_URL` | *(none)* | Supabase project URL. When set (with the key) storage switches from SQLite to Postgres. |
| `SUPABASE_KEY` | *(none)* | Supabase service-role key. |
| `STICKBLADE_DATA_DIR` | `arena_data` | Where the SQLite DB and replays are written in local mode. |

Defaults are read at import time for `security.py` and at first use for
storage, so set them before starting the server.

### Networking

| Variable | Default | What it does |
|---|---|---|
| `CORS_ORIGINS` | the Vercel + localhost origins | Comma-separated allowlist. `*` is deliberately not the fallback. |
| `TRUST_XFF` | `0` | `1` to honour `X-Forwarded-For` for rate-limit keys. Only enable behind a proxy you control — otherwise a client can forge its own bucket. |

### Runtime

| Variable | Default | What it does |
|---|---|---|
| `SDL_VIDEODRIVER` | *(system default)* | Set to `dummy` for headless runs (CI, servers, tests). Required — pygame needs a display otherwise. |
| `PORT` | `8000` | Uvicorn/HF Spaces port. |

## Frontend (`stickblade-web`)

| Variable | Default | What it does |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `""` (same origin) | Backend origin. **Empty means same-origin**: the browser calls `/api/*` on the Next server and `next.config.mjs` proxies it to `BACKEND_ORIGIN`. That is what makes preview URLs and LAN testing work. Set it to the deployed backend URL in production. |
| `BACKEND_ORIGIN` | `http://127.0.0.1:8000` | Server-side only — the rewrite target for the proxy above. |

## Offline tools

No environment variables are required. Two that help:

```bash
SDL_VIDEODRIVER=dummy          # headless; required on any machine without a display
PYTHONPATH=stickblade          # only if you run tools/ from a directory
                               # where the package isn't importable
```

## Verifying your configuration

```bash
curl localhost:8000/api/health    # which provider keys are set, queue depth
curl localhost:8000/api/version   # API version, prompt version, weapons, modes
curl localhost:8000/api/status    # component health, failure rate, fingerprint
```
