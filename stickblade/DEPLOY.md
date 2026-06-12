# 🚀 Deploying STICKBLADE ARENA for $0

Three free accounts, ~30 minutes, no credit card.

```
[Visitors] ──► Vercel (Next.js frontend, stickblade-web/)
                  │  NEXT_PUBLIC_API_BASE
                  ▼
              Hugging Face Space (FastAPI + physics sim, stickblade/)
                  │                      │
                  ├──► OpenRouter (LLMs) └──► Supabase (votes, Elo, replays)
```

---

## Step A — Supabase (persistent database) ~5 min

1. Sign up at **supabase.com** → *New project* (free tier).
2. Open **SQL Editor** → *New query* → paste the contents of
   `supabase_schema.sql` → **Run**.
3. Go to **Storage** → *New bucket* → name it exactly `replays`
   (keep it **private** — the backend reads it with the service key).
4. Go to **Settings → API** and copy two values:
   - `Project URL` → this is `SUPABASE_URL`
   - `service_role` key → this is `SUPABASE_KEY`
     ⚠️ service_role bypasses row security — backend env vars only,
     **never** in frontend code or a Git repo.

> Skip this step if you accept votes/Elo resetting on server restarts —
> the app falls back to local SQLite automatically.

## Step B — OpenRouter (LLM access) ~3 min

1. Sign up at **openrouter.ai** → *Keys* → create a key (`sk-or-...`).
2. That's `OPENROUTER_API_KEY`. Models ending in `:free` cost nothing.
3. **Recommended:** in OpenRouter → *Settings → Credits*, set a **spending
   cap** (e.g. $5). This is your hard ceiling no matter what happens.

## Step C — Hugging Face Space (the backend) ~10 min

1. Sign up at **huggingface.co** → *New Space*:
   - SDK: **Docker** · Hardware: **CPU basic (free)**
2. Upload the whole `stickblade/` folder to the Space
   (web upload, or `git clone` the Space repo and push).
   The included `Dockerfile` is detected automatically.
3. In the Space → **Settings → Variables and secrets** add **secrets**:

   | Secret | Value |
   |---|---|
   | `OPENROUTER_API_KEY` | `sk-or-...` (Step B) |
   | `SUPABASE_URL` | `https://xxxx.supabase.co` (Step A) |
   | `SUPABASE_KEY` | service_role key (Step A) |

   And (after Step D gives you your Vercel URL) one **variable**:

   | Variable | Value |
   |---|---|
   | `CORS_ORIGINS` | `https://your-app.vercel.app` |

4. The Space builds (~2–3 min) → live at
   `https://<username>-<space-name>.hf.space`
   Quick test: open `https://<...>.hf.space/api/models` — you should see the
   model list as JSON.

## Step D — Vercel (the frontend) ~10 min

1. Push the **`stickblade-web/`** folder to a GitHub repository.
   - Either as its own repo, or as a subfolder of a monorepo.
2. Sign up at **vercel.com** (free Hobby plan) → **Add New… → Project**
   → *Import* your GitHub repo.
3. Configure the project:
   - **Framework Preset:** Next.js (auto-detected)
   - **Root Directory:** if the repo contains both folders, click *Edit* and
     select `stickblade-web` — otherwise leave as is.
   - **Environment Variables** → add:

     | Name | Value |
     |---|---|
     | `NEXT_PUBLIC_API_BASE` | `https://<username>-<space-name>.hf.space` (from Step C, **no trailing slash**) |

4. Click **Deploy** (~1–2 min). Your arena is live at
   `https://<project>.vercel.app`.
5. **Lock CORS:** go back to the HF Space → Settings → set
   `CORS_ORIGINS=https://<project>.vercel.app` → restart the Space.
   Now only your frontend can call the API from a browser.
6. Verify the full loop: open the Vercel URL → pick two free models →
   choose MACRO or JOINT mode → FIGHT → watch → vote → check `/leaderboard`.

Custom domain (optional, still free): Vercel → Project → Settings →
Domains → add your domain and follow the DNS instructions.

---

## 🔐 Security (already built in — know your knobs)

The backend ships with `security.py`, active out of the box:

| Protection | Default | Env var |
|---|---|---|
| Matches per IP per hour | 6 | `RL_MATCHES_PER_HOUR` |
| Votes per IP per hour | 30 | `RL_VOTES_PER_HOUR` |
| Any API requests per IP per minute | 120 | `RL_REQS_PER_MIN` |
| Max queued sims (backpressure) | 10 | `MAX_QUEUE` |
| **Global daily match cap (spend ceiling)** | 300 | `MAX_MATCHES_PER_DAY` |
| Custom model ids must be `:free` | on | `ALLOW_PAID_CUSTOM=1` to lift |

Also active: strict model-id validation (regex, length caps), Pydantic input
limits, one-vote-per-match, API docs disabled in production
(`/docs`, `/openapi.json` → 404), and security headers
(`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
`Cross-Origin-Opener-Policy`) on every response.

**The spend model in plain words:**
- Roster models (the dropdown) can include paid ones **you** chose — fine.
- Strangers typing custom ids can only use `:free` models — they cannot
  spend your money.
- `MAX_MATCHES_PER_DAY` caps total burn even from roster models.
- Your OpenRouter credit cap (Step B.3) is the final backstop.

**What's intentionally NOT included (and when to add it):**
- *Accounts/log-in* — add if vote manipulation actually becomes a problem
  (per-IP limits are enough at hobby scale; LMSYS ran anonymous for a year).
- *Distributed rate limiting (Redis)* — only needed if you scale past one
  backend instance; in-memory windows are correct for a single free dyno.
- *Cloudflare in front* — free tier gives DDoS protection + caching if the
  site takes off.

## Checklist before you share the link

- [ ] Secrets are in HF Space *secrets* (not in code, not in Git history)
- [ ] OpenRouter spending cap set
- [ ] `CORS_ORIGINS` set to your exact Vercel URL
- [ ] `https://<space>.hf.space/docs` returns 404
- [ ] Burst-refresh the Vercel page ~10×: keeps working; the 121st API call
      in a minute would 429 (that's the throttle working)
- [ ] Supabase: confirm a `matches` row + a `replays/<id>.json` object appear
      after a test duel

## Alternatives to Step C

- **Render.com** free web service: connect repo, Docker runtime, same env
  vars. Free instances sleep after ~15 min idle (~1 min cold start).
- **Railway.app**: similar, small monthly free credit.

## Local run with cloud persistence (test Step A before deploying)

```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_KEY=eyJ...
export OPENROUTER_API_KEY=sk-or-...
uvicorn server:app --port 8000
# console prints:  [server] storage: Supabase (persistent)
```

## Scaling notes (when you outgrow free)

- The sim worker is one background thread — fine for a hobby arena. For real
  traffic: multiple workers, or move sims to a job queue.
- Replays are ~100–250 KB gzipped; Supabase free storage (1 GB) holds
  thousands. Add a cleanup job when you get there.
- Past one instance: move rate limiting to Redis/Upstash (free tier exists).
