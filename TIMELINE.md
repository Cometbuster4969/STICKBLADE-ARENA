# STICKBLADE ARENA — Timeline & Roadmap

> Single source of truth for what's shipped, what's queued, and what's
> deliberately deprioritized. Every AI agent (Claude, Codex, Cursor,
> Copilot, etc.) working on this repo must:
> 1. **Read this file at the start of any session** to know current state.
> 2. **Update this file at the end of any session** where anything
>    shipped, was discussed for the future, or was explicitly killed.
>
> The commit log is authoritative for *what* changed; this doc is
> authoritative for *why*, *what's next*, and *what we decided not to do*.
> Never delete deprioritized items — keep them as ledger entries so future
> sessions don't re-propose them.

**Last updated:** 2026-07-27 · Tier-A #1 + #2 + #3 shipped (schema + bots + dataset export endpoint)
**Live grades (per AGENTS.md §0.5 anchors):** Codebase 8.4 · Security 8.7 · Research 8.2

---

## Table of Contents

1. [Current state at a glance](#current-state-at-a-glance)
2. [Shipping timeline (what's done)](#shipping-timeline-whats-done)
3. [What's next (roadmap)](#whats-next-roadmap)
4. [Deliberately deprioritized (do NOT re-propose)](#deliberately-deprioritized)
5. [Live surfaces + credentials](#live-surfaces--credentials)
6. [How to update this file](#how-to-update-this-file)

---

## Current state at a glance

**Product:** Physics-based LLM benchmark. Two language models sword-fight
in a 2D pymunk arena. Humans vote blind on who fought smarter. Per-model
Elo tracks it across 6 eval axes: model × sharp zone × weapon × control
mode × arena × blindfolded variant.

**External validation earned:**
- 🏆 Featured on the [official Pymunk showcase](https://www.pymunk.org/en/latest/showcase.html#stickblade-arena) (Non-Games)
- 🥉 Bronze — Product of the Day on [peerpush.com](https://peerpush.com/p/stickblade-arena)
- 🤖 Google AI Overview: *"a brilliant example of gamified AI evaluation"*
- 📮 Organic issue from Victor Blomqvist (pymunk maintainer) endorsing the project

**Traffic baseline (Vercel Analytics, first ~5 weeks):**
- 197 visitors · 495 page views · 65% bounce · 2.5 pv/visitor
- Top referrers: reddit.com (33), l.threads.com (27), google.com (11)

**Vote-through baseline (recorded 2026-07-18):**
- Lifetime: 22.6% (93 / 411 completed matches)
- Trailing 7-day: 34.2% (13 / 38)
- This is the pre-reveal-as-reward number. Compare against post-Tier-S
  window rates to judge whether legibility fixes moved the needle.

**Stack:**
- Backend: Python 3.13 + FastAPI + pymunk 6.x on Hugging Face Spaces (Docker)
- Frontend: Next.js 15 + React 19 on Vercel
- Storage: Supabase (Postgres + storage bucket) with atomic `apply_elo_vote()` RPC; SQLite fallback for local dev
- Models: 29 free-tier across OpenRouter (21) + Groq (8), BYOK supported
- CI: 8 parallel GitHub Actions jobs, ~1 min wall time

---

## Shipping timeline (what's done)

Reverse chronological. Every ship gets: date · commit(s) · one-line summary.
Long commits get a "Why it mattered" note.

### Tier-A rigor arc (Jul 27, 2026 →)

- **2026-07-27** · workspace tip — **Tier-A #3: Dataset export endpoint** (`/api/export`)
  - Backend-only ship. Both JSON (`{count, exported_at, prompt_version, since, until, limit, matches:[...]}`) and JSONL (`application/x-ndjson`, one match per line, streaming-friendly for HF Datasets ingestion) formats.
  - Query params: `since`, `until` (unix epoch bounds), `limit` (clamped [1, 50000], default 10000), `fmt` (json | jsonl), `include_votes` (default true — attaches anonymous vote objects).
  - Includes: model_a/b, sharp, weapon, mode, arena, blindfolded, status, winner_side, method, turns, commentary, ALL proxy metrics (damage/hits/fallback per side + avg_distance), prompt_version tag per row.
  - Deliberately excludes replay JSON blobs (per-match multi-MB; consumers fetch via existing `/api/replay/{mid}` after seeing the id in export). Prevents response bloat + OOM on HF Space.
  - No PII: no IPs, no user IDs, no BYOK residue. Same exposure profile as `/api/leaderboard`.
  - Both storage backends implemented. Supabase path handles two-sided bounds via PostgREST `and=(...)` composite (documented in the method — non-obvious).
  - **What's NOT shipped (needs your involvement):** daily cron push to `huggingface.co/datasets/Pioneer37/stickblade-matches`. Requires: (1) you creating the dataset repo on HF, (2) `HF_TOKEN` secret added to HF Space env vars, (3) a small GitHub Action or Vercel cron hitting `/api/export?fmt=jsonl` daily and pushing the result via `huggingface_hub`. Filed as Tier-A #3b explicit handoff.
  - **Why it mattered:** single biggest gap between us and citable-artifact status. No dataset = no citation. This gets the endpoint live so anyone can `curl -o matches.jsonl 'https://.../api/export?fmt=jsonl'` today, even before the automated HF snapshot exists.
  - Verified: both backends' `export_matches()` have matching signatures, endpoint validates `fmt` (400 on garbage), NDJSON path emits correct MIME + Content-Disposition.
  - Anchor grade delta: Research **8.0 → 8.2** (endpoint alone is a real unlock; +0.3 more comes when HF snapshot ships).

- **2026-07-27** · workspace tip — **Tier-A #2: Non-LLM baseline bots** (Reviewer #4 + Session #3 LLM #1)
  - NEW `stickblade/bots.py` (238 lines) with 4 bots subclassing `Brain`:
    - `RandomBot` — uniform pick over weapon's action + FOOTWORK. Floor baseline.
    - `GreedyAttackBot` — always sharp-attack + advance (bow: shoot + hold). No HP/distance check.
    - `DistanceHolderBot` — reads state.distance, holds ideal range per weapon (sword=90, dagger=75, spear=150, flail=130, bow=300) with ±25 buffer.
    - `ScriptedProBot` — hand-tuned state machine: exploits knocked-down enemy, defends when low HP + being hit, spins flail before attacking, bow ranged-only, distance-appropriate action selection.
  - Wired into `brains.make_brain()` for `bot:*` model IDs. New file (not in brains.py) because these are pure heuristics with zero network I/O — different concern than LLM adapters.
  - Added to `config.ARENA_MODELS` (4 new entries) and mirrored in `stickblade-web/lib/models.js`. Roster is now 33 entries (29 LLMs + 2 mocks + 4 bots).
  - Deterministic-per-seed via `random.Random(seed)` on each instance. Foundation for Tier-A #4 (frozen eval pack) reproducibility.
  - **Why it mattered:** scale-independent y-axis anchors. "GPT-OSS 120B beats ScriptedPro 78%% of matches" is a portable claim any reviewer can reproduce; a raw Elo of 1247 is not. Reviewer #4's specific ask.
  - Verified: all 4 bots compile clean, all 4 override `decide()`, `_BOT_REGISTRY` has all 4 keys, frontend build clean at 12.9kB/117kB (unchanged from prior — bots are backend-only, roster just gets new entries).
  - Anchor grade delta: Research **7.7 → 8.0**.

- **2026-07-27** · workspace tip — **Tier-A #1: Strict `json_schema` enforcement on GPTBrain + GeminiBrain**
  - Added `_decide_json_schema(allowed_actions)` (OpenAI-flavor) and
    `_gemini_response_schema(allowed_actions)` (Gemini-flavor) helpers
    in `brains.py`. Both constrain the model at generation time to emit
    the exact `{thought, action, footwork}` shape with per-weapon enum
    on `action` + FOOTWORK enum on `footwork`.
  - Wired into `GPTBrain.decide()` and `GeminiBrain.decide()` (skipped
    in joint mode where reply shape differs). Both paths fall back to
    plain JSON mode on any exception so the match still resolves.
  - Deliberately NOT wired into OpenRouter or Groq adapters — per-model
    schema support varies there, would silently 400 half the roster.
    Deferred to Tier B (probe-support-per-model-at-startup).
  - **Why it mattered:** cuts the ~15-20% fallback rate seen in the
    brain-error debug endpoint on the ~15% of matches that use direct
    OpenAI/Gemini paths. Small-model malformed-JSON turns become
    schema-rejected at API level instead of parser-rejected downstream.
  - Anchor grade delta: Research **7.5 → 7.7**.

### Tier-S research-grade arc (Jul 17 – Jul 27, 2026)

- **2026-07-27** · `d833022` (GitHub) / `d66daff` (workspace) — **Tier-S #3: proxy metrics + objective leaderboard + blindfolded variant**
  - Ships: 10 new match columns (damage/hits/fallback per side + avg_distance), new `blindfolded` bool + 6th eval axis on elo PK, `/api/leaderboard/objective` endpoint, ObjectiveLeaderboardTable with sortable columns, "🙈 Blindfolded" toggle in fight setup + LB filter, apply_elo_vote RPC promoted to 8-arg signature.
  - **Why it mattered:** decouples ranking from small-N vote pool (Reviewer #2's top pick); blindfolded variant isolates 2D geometry ability from pre-parsed booleans (Reviewer #4's novel insight, publishable angle).
  - Anchor grade delta: Research **6.8 → 7.5** (workshop-paper-submittable methodology).
  - Required Supabase migration ran before push. Live: all endpoints 200.

- **2026-07-23** · `a7d0e9c` — **UX legibility pass**
  - Post-friend-feedback: hero rewrite ("Two LLMs make real API calls to decide sword-fight moves"), inline "How this works" `<details>`, WaitPanel phase labels + elapsed timer + "why is this slow" hint + read-while-you-wait about section, FAQ component (6 items), dropped `(free)` from all 29 display names, toned down neon.
  - **Why it mattered:** friends couldn't tell it wasn't a game; solved the first-15-seconds bounce for BOTH normies and distracted researchers without pivoting the research positioning.

- **2026-07-18** · `87c1d5d` — **Tier-S #2: stratify Elo by mode (macro/joint) and arena**
  - Elo PK extended to `(model, sharp, weapon, mode, arena)`. Backend + frontend + SQL migration. Fixed executescript-vs-implicit-txn SQLite bug during dev.
  - Anchor grade delta: Research **6.4 → 6.8**.

- **2026-07-17** · `4b1a507` — **Tier-S #1: PROMPT_VERSION pin + Wilson-CI on win-rate**
  - `PROMPT_VERSION = 1` constant, exposed via `/api/version` + every LB row. `_wilson_ci()` helper (draws=½ wins), new "Win% (95% CI)" column. Not bootstrap — Wilson is O(1), matches LMSys standard.
  - AGENTS.md §10.5 PROMPT_VERSION_LOG + ELO CELL KEY changelog added.
  - Anchor grade delta: Research **6.0 → 6.4**.

- **2026-07-17** · `838463f` — **Engagement: reveal-as-reward vote panel + N-per-model + vote-rate baseline**
  - Gold-bordered "🔒 Models hidden — vote to reveal" card; lifetime prediction accuracy in localStorage (wins/total); N + provisional flag on leaderboard (K=32 noise below N=10); `/api/stats/vote_rate` endpoint for post-intervention measurement.

### SEO / agent-discovery hardening (Jul 15, 2026)

- **2026-07-15** · `685c336` — Content-Signal directive + `/llms-full.txt` (322 lines) + RFC 8288 `Link:` response headers on `/`. Skipped: DNS-AID (needs custom domain, not `*.vercel.app`); Cloudflare markdown-negotiation (Vercel not CF, `llms-full.txt` covers same need).
- **2026-07-15** · `c49a5b0` — OG image (1200×630 cyan/magenta duel), full JSON-LD (`SoftwareApplication`), `metadataBase`, `/sitemap.xml`, `/robots.txt` with per-bot allow rules for GPTBot/ClaudeBot/PerplexityBot/etc., `/llms.txt`. Nilkick Findable 60 → ~90.

### AGENTS.md & anti-sycophancy protocol (Jul 13, 2026)

- **2026-07-13** · `ed22911` — Anti-sycophancy protocol §0.5. No claim without `file:line` citation. Never move a grade based on another LLM's pushback alone. Anchor grades planted with evidence: Codebase 8.4 / Security 8.7 / Research 6.0.
- **2026-07-13** · `8747d84` — Original AGENTS.md working conventions (~545 lines).

### CI pipeline (Jul 12–13, 2026)

- **2026-07-13** · `5497bbb` — bump `actions/setup-node@v4→v5` (kill Node 20 deprecation warning).
- **2026-07-13** · `577b70e` — Fix roster job (needed full requirements.txt + SDL2, not just httpx) + security job (added B608 to bandit `--skip` — false positive on parameterized SQL with hardcoded WHERE clauses). Also bumped `checkout@v4→v5`, `setup-python@v5→v6`.
- **2026-07-12** · `c1dc5e8` — Comprehensive 6-job GitHub Actions workflow: matrix backend tests (Python 3.11/3.12/3.13 with weapon + arena + storage regression + brain routing), matrix frontend build (Node 20/22), Bandit + secret-history scan, roster consistency check, link check.

### Match-loop hardening (Jul 5–12, 2026)

- **2026-07-12** · `561a8ba` — Match deadline 45min → 3min (worker hang fix) + README hero rewrite with external validation callouts.
- **2026-07-06** · `340ad5d` — Aligned tagline with "benchmark" positioning across all surfaces.
- **2026-07-05** · `0c8b3d5` — Copy: "Use my own" → "Use your own OpenRouter key".
- **2026-07-05** · `3313e16` — Groq: correct llama-4-scout ID + skip cooling buddies before firing (429 breaker awareness).
- **2026-07-05** · `8165544` — Groq payload shape fix (`include_reasoning: False` vs OpenRouter's `reasoning:{enabled:false}` — was 400ing every Groq call).
- **2026-07-05** · `76d19d8` — **Groq as 2nd LLM provider**. Kills single-provider dependency. Provider-diverse buddy failover.

### Feature + polish sprint (Jul 2–4, 2026)

- **2026-07-04** · `dfc14bd` — Tournament current-match hero + pulsing bracket card + commentator quote card.
- **2026-07-04** · `361bbc1` — Elo trend arrow vs 1000 baseline (↑/↓/→ with ±20 dead-zone).
- **2026-07-04** · `f915539` — Onboarding card + real copy-to-clipboard share button.
- **2026-07-04** · `9083c40` — `lib/models.js` as last-line displayName fallback.
- **2026-07-04** · `c93fde4` — **BYOK (bring-your-own-key)** + GitHub Sponsors funding. Key lives 30s in-memory, popped in `try/finally`, `_KEY_LEAK_RE` scrubs from error surfaces.
- **2026-07-02** · `174fb32` — README refresh: wait screen, resilience, debug endpoints, audit fixes.
- **2026-07-02** · `6bf8789` — **Live wait screen** — quips + queue pos + combat ticker + head-to-head. Replaced dots-only spinner.
- **2026-07-02** · `b5e4a2c` — Audit sweep: Elo race + player.js dedup + XFF spoof + 5 other findings.
- **2026-07-02** · `01b4beb` — Fix: shared replay was showing wrong model as winner ~50% of the time (blind flip axis); flail mock was frozen.
- **2026-07-02** · `f797b61` — 429 circuit breaker (parses `retry_after_seconds` from OR/Groq metadata) + provider-diverse buddy failover.

### OpenRouter reasoning routing crisis (Jun 29–30, 2026)

- **2026-06-30** · `8062795` — **Catalog-driven reasoning policy.** Was sending wrong knob per family, caused ~100% fallback. Fixed by mapping each model to correct params.
- **2026-06-30** · `0f26493` — Always-on reasoning guard (substring detector missed gemma-4, laguna, cohere-north).
- **2026-06-30** · `e45ec4d` — Kill "immediate fallback" on reasoning models (gpt-oss, nemotron, etc.).
- **2026-06-30** · `8e6f389` — Debug: brain-error ring buffer + OpenRouter ping endpoint.
- **2026-06-29** · `c46a6ca` — **Ice arena**: physics + LLM aware (damping 0.99 → 0.996, shin friction override, system prompt hint).

### Match hardening (Jun 21, 2026)

- **2026-06-22** · `099ed1e` — Resilience: retry + buddy-model fallback + keepalive. Cut fallback rate.
- **2026-06-21** · `e75c970` — Bow fallback brain now actually shoots arrows (was sword-swinging).
- **2026-06-21** · `7ce0ba5` — Loose ends: hide raw errors, fix dead model IDs, fallback banner, `/api/health`.
- **2026-06-21** · `10e6321` — Security fixes + Supabase fix.

### Initial launch arc (Jun 13–14, 2026)

- **2026-06-14** · `c651070` — **Tournaments** (single-elim brackets, 4/8 models) + refreshed free model roster.
- **2026-06-14** · `3be8fdc` — Trash talk + post-fight roast + weapons (dagger + spear) + arena modifiers (ice + low-gravity).
- **2026-06-14** · `f3474ce` — Random A/B color flip (blind vote integrity fix) + sounds + killcam + predict-streak + per-weapon LB.
- **2026-06-14** · `0319077` — **Joint mode** (raw joint control) + fire arrows + weapon-aware prompt + spatial awareness state.
- **2026-06-14** · `f926de1` — UI redesign with cyberpunk arena aesthetic.
- **2026-06-14** · `4338869` — Perf + a11y + security: drop legacy polyfills, label selects, reserve CLS space, CSP/COOP/XFO/Permissions-Policy headers.
- **2026-06-13** · `24a54d8` — Vercel Web Analytics.

---

## What's next (roadmap)

Ranked by anticipated impact per weekend of effort. Anchor grade targets
listed so we can measure whether a ship actually moves the number.

### TIER A — 2-4 weeks total

These push Research 7.7 → 8.5 (from "workshop paper submittable" to
"citable research artifact with downloadable dataset").

- [x] ~~**Strict json_schema enforcement**~~ — **SHIPPED 2026-07-27**
  (moved to Shipping timeline). Was proposed by Reviewer #5 as
  A1. Follow-up: probe json_schema support per OpenRouter/Groq model
  at startup + toggle per adapter. Slot as Tier B item below.

- [x] ~~**Non-LLM baseline bots**~~ — **SHIPPED 2026-07-27**
  (moved to Shipping timeline). RandomBot / GreedyAttackBot /
  DistanceHolderBot / ScriptedProBot in new `bots.py`. Reviewer #4
  + Session #3 LLM #1 proposal fully addressed.

- [x] ~~**Dataset export endpoint**~~ — **SHIPPED 2026-07-27**
  (moved to Shipping timeline). `/api/export?fmt=jsonl` live. Cron
  push to HF Datasets is the remaining piece (see Tier-A #3b below).

- [ ] **Tier-A #3b: Daily HF Datasets snapshot** (HANDOFF — needs user)
  - Push `/api/export?fmt=jsonl` output daily to
    `huggingface.co/datasets/Pioneer37/stickblade-matches` via
    `huggingface_hub.upload_file`
  - **Needs from you:**
    1. Create the dataset repo on HF (2 min): huggingface.co → New → Dataset
    2. Generate a HF write token: huggingface.co/settings/tokens
    3. Add `HF_DATASET_TOKEN` secret to the HF Space env vars
    4. Confirm the dataset repo name (default: `Pioneer37/stickblade-matches`)
  - Once above done, I'll ship a ~30-line GitHub Actions cron
    (`.github/workflows/dataset-snapshot.yml`) that runs daily,
    curls the export endpoint, and uploads via `huggingface_hub`.
  - Effort after handoff: 30 min.

- [ ] **Dataset dump + daily HF snapshot** (Reviewer #2 #19, Reviewer #4 phase-3)
  - `GET /api/export?since=YYYY-MM-DD&format=jsonl`
  - Cron daily push to `huggingface.co/datasets/Pioneer37/stickblade-matches`
  - Includes replays + proxy metrics + prompt_version tags
  - **Single biggest thing between us and citable-artifact status.** No dataset = no citation.
  - Effort: ~1 weekend

- [ ] **Frozen eval pack (100 canonical matchups)** (all 4 reviewers agreed)
  - 20 per weapon × 5 sharp zones, fixed seeds, `prompt_version=v1` locked
  - Run all 29 models against it, publish CSV alongside live leaderboard
  - Reviewers download CSVs, not live leaderboards
  - Effort: 1 weekend + a few hours of compute

- [ ] **Best-of-3 series with mid-series sharp-zone flip** (Reviewer #3 phase-2)
  - Same pair fights 3 rounds; server flips sharp zone between rounds
  - Track "adaptation delta" — does the model change behavior after seeing new zone?
  - Effort: 1 weekend

- [ ] **JOINT-mode reach-target Gym variant** ⭐ (Reviewer #4 phase-2, novel)
  - No weapon, no opponent — just "touch this target with your hand"
  - Pure motor-control benchmark, isolates "can it actuate joints coherently" from tactics
  - Effort: 1-2 weekends

### TIER B — Next quarter

Nice-to-have; ships once Tier A stabilizes.

- [ ] **LLM-as-judge automated jury agent** ⭐ (Reviewer #5 A4, novel)
  - High-tier reflection model (GPT-4o / Claude 3.5 Sonnet) reads the
    full match trajectory (state + actions + damage events + winner)
    and outputs a critique + tactical-quality score
  - **Third rating axis** alongside human vote + objective metrics.
    Chatbot Arena literature (Zheng et al 2023) shows GPT-4-as-judge
    ~0.85 correlates with human votes on text; nobody has measured
    this on physics tactics. Publishable finding either way.
  - Blocked on: Tier A #7 (dataset dump) — judge outputs need to be
    downloadable to be citable. Also cost management: 1 judge call
    per match adds ~$0.002-0.01 per match depending on model.
  - Effort: ~2 weekends

- [ ] **BYOA (Bring Your Own Agent) tournament** (Reviewer #5 C4)
  - Different from BYOK. BYOK = paste API key. BYOA = submit a custom
    system prompt / fine-tune / small OSS model + get ranked separately
    from the official leaderboard.
  - Drives real repeat traffic ("check my ranking"). Requires: prompt-
    injection-safe sandbox for custom system prompts, GitHub PR intake
    harness, isolated Elo pool so custom entries don't contaminate the
    canonical leaderboard.
  - Blocked on: Tier A #7 (dataset dump) so custom entries have
    infrastructure to run against.
  - Effort: ~2-3 weekends

- [ ] **VLM dual-modality benchmark** (Reviewer #5 A2)
  - Rasterize low-res canvas snapshot every 3s, pack alongside the
    existing coord JSON. Text models vs vision models on identical
    scenarios = clean paper.
  - Blocked on: Tier A #8 (frozen eval pack). Without a fixed 100-
    matchup set, text-vs-VLM comparisons are apples-to-oranges.
  - Cost warning: image tokens are 2-3x more expensive per turn.
    Budget only for the frozen eval pack runs, not general leaderboard.
  - Effort: ~1-2 weekends after eval pack ships

- [ ] **Probe per-model json_schema support** (Tier-A #1 follow-up)
  - Extend the schema enforcement shipped 2026-07-27 to OpenRouter +
    Groq adapters by probing each model's response_format capability
    at process startup + toggling per-adapter.
  - Currently only GPTBrain + GeminiBrain use strict schemas because
    per-model OR/Groq support varies. This closes the coverage gap.
  - Effort: ~1 weekend

- [ ] **Split `brains.py`** (currently 1296 lines, held-back grade of Codebase 8.4)
  - Split into `brains/{base,openrouter,groq,mock,policy}.py`
  - Zero behavior change, huge legibility win
  - Anchor grade target: Codebase 8.4 → 8.5
  - Effort: 1 evening

- [ ] **Docker starter-bot template repo** (Reviewer #3 phase-3)
  - "Build your first Stickblade bot in 30 min" — lowers external-contributor barrier
  - Effort: 1 weekend

- [ ] **Cross-benchmark correlation study** (Reviewer #4 phase-3)
  - Run top-10 models, correlate Stickblade Elo vs published MMLU/GPQA/Arena-Hard
  - Blog post or arXiv note
  - This is the "paper acceptance" item, not the "get to research grade" item
  - Depends on: Tier A #1 (dataset dump) being real
  - Effort: 1-2 weekends + writing time

- [ ] **Model cards / strategy writeups** (Reviewer #2 #12)
  - Community-lore layer: "Model X dominates close range by spamming low kicks"
  - Ships after there's a community to write for
  - Effort: ongoing

- [ ] **Trash-talk manipulation as security benchmark** ⭐ (Reviewer #4, novel)
  - Does hostile trash-talk actually degrade the opponent LLM's decisions?
  - New research angle, cheap to test
  - Effort: 1 weekend

- [ ] **Dependabot + pip-audit in CI**
  - Closes last real security-posture gap
  - Anchor grade target: Security 8.7 → 8.9
  - Effort: 15 min

- [ ] **Custom domain + DNS-AID SVCB records**
  - Currently blocked: on `*.vercel.app` we don't own the DNS zone
  - Buy `stickblade.arena` or similar (~$12/yr) then complete agent-readiness Tier 1
  - Effort: 30 min after domain purchased

- [ ] **`/about` canonical explainer page**
  - Currently the FAQ + inline `<details>` cover most needs
  - `/about` becomes the URL you link from HN/Twitter/LinkedIn
  - Ships when we have a real HN re-submit ready
  - Effort: 1 evening

- [ ] **METHODOLOGY.md**
  - 300-line honest doc: how Elo is computed, K-factor, prompt version protocol, known biases
  - Unlocks the "here's the paper's methodology section" story
  - Effort: 1 evening

### Marketing / distribution (whenever the product is boring)

- [ ] **GitHub topic tags + `awesome-*` list submissions** (Reviewer #5 D4)
  - Add topic tags on the repo: `llm-evaluation`, `ai-agents`, `pymunk`,
    `structured-outputs`, `reinforcement-learning`. Takes 30 seconds
    in GitHub UI, drives high-intent developer traffic.
  - Submit PRs to: `awesome-llm-evaluation`, `awesome-ai-agents`,
    `awesome-llm`. Each is a ~5-line PR against a public list repo.
  - Cheap, real, do this week.
- [ ] **HN re-submit** — same URL, better account (need 20+ karma), Tuesday-Thursday 9am ET / 6:30pm IST
  - Blocked on: karma-building (currently 1). Need to comment thoughtfully on 20-30 unrelated threads over 2-3 weeks.
  - Previous attempt (`48951304`, 2026-07-17): flagged first comment due to 1-karma account + 3 external links.
- [ ] **r/LocalLLaMA post** — drafted earlier, never shipped. Best for post-Tier-A when we can point at a downloadable dataset.
- [ ] **LinkedIn / Twitter victory-lap post** — 3 pillars: pymunk showcase + peerpush bronze + CI passing badge. Ship after Tier A #2 (dataset dump).
- [ ] **HuggingFace Grants Program application** (Reviewer #5 M4)
  - HF grants pay $2-10k, worth applying to when we have Tier A shipped
    + a downloadable dataset on HF Datasets. Not sustaining income,
    but real runway extension.
  - Blocked on: Tier A #7 (dataset dump).

---

## Deliberately deprioritized

**Do NOT re-propose these in future sessions unless the underlying
reasoning has changed.** All were considered, weighed, and killed with
specific rationale.

- ❌ **B2B enterprise testing API (LMSYS-model monetization)** (Reviewer #5 M1)
  — LMSYS didn't monetize this way until they had ~1M matches on the
  leaderboard; we have ~400. Foundation labs (OpenAI/Anthropic/Meta)
  don't pay for third-party evals; they run internal ones and *cite*
  public benchmarks. Trying to sell enterprise access at 197 monthly
  visitors signals "small project seeking rent" and hurts credibility
  with the academic audience we want. Building enterprise API infra
  (SLAs, auth, dashboards) is 3+ months that eats the Tier-A runway.
  Revisit: if we hit 100k matches AND a lab publicly cites Stickblade
  in a paper. Before that, no.

- ❌ **Leaderboard sponsorships (Lambda/Together AI "hardware partner" badges)**
  (Reviewer #5 M2) — Same problem, smaller scale. Sponsors want traffic,
  not potential (197 visitors/month insufficient). "Sponsored by X"
  on a benchmark leaderboard actively hurts the neutrality-of-eval
  story. Chatbot Arena rejects sponsorships for exactly this reason.

- ❌ **Dual-license the pymunk + LLM framework (commercial-enterprise tier)**
  (Reviewer #5 M3) — Premature and legally shaky. Codebase is 6 weeks
  old with 1 star. Zero commercial demand. Also: pymunk is MIT, so the
  "physics agent-loop architecture" we'd be selling is 95%% someone
  else's work. Dual-licensing only works for proven infrastructure
  (MongoDB, Elastic); we're not there.

- ❌ **Display ads on the site** (user suggestion 2026-07-27)
  — 197 visitors × $0.50 RPM = **$0.10/month** in ad revenue. Ten cents.
  Meanwhile ads on an eval benchmark kill 100%% of research credibility
  (nobody cites a leaderboard site with programmatic ads). Asymmetric
  loss. If infra costs become real, add a "Sponsor on GitHub" nudge
  (already live) or credit line for ONE aligned company — not display
  ads. Never.

- ❌ **Separate "premium" tier for self-trained / fine-tuned models**
  (user suggestion 2026-07-27) — BYOK already covers "use your fine-tune
  via an OpenRouter model ID." Adding a paywall between free and BYOA
  (Tier B) kills conversion completely at 200 monthly visitors. Extend
  BYOK/BYOA discoverability instead of splitting tiers.

- ❌ **Celery + Redis + WebSocket refactor for horizontal scaling**
  (Reviewer #5 A3) — Right direction, wrong timing. We have zero
  scaling problem: 197 visitors in 5 weeks, 1 HF Space container
  handling everything at ~300ms p50. Also: HF Spaces doesn't easily
  support Redis; scaling would mean moving off HF entirely, changing
  the whole deploy story. Revisit: when `/api/health` p95 exceeds
  5s under load, not before. Do not ship.

- ❌ **24/7 Twitch stream of random model battles**
  (Reviewer #5 D3) — Requires (a) $50-200/mo paid API budget for
  constant matches, (b) OBS streaming infra we don't have, (c) chat
  moderation, (d) 24/7 babysitting. Cost/benefit is upside-down for
  our stage. Small clips shared manually to Twitter/LinkedIn is fine;
  full always-on stream is not.

- ❌ **Twitter/LinkedIn 10-second video loops as primary marketing**
  (Reviewer #5 D1) — Video editing has real setup cost (screen record
  + trim + captions per clip) that eats bandwidth better spent shipping
  Tier A. Passive channels (PeerPush, pymunk showcase referrals) do
  the same reach for zero recurring work. Revisit after Tier A when
  we have a real "here's the dataset, here's the finding" hook worth
  showing off.

- ❌ **Multi-agent FFA / 2v2 / co-op modes** — pushed by all 4 reviewers. Complexity multiplier before single-agent signal is stabilized. Revisit only after Tier A ships.
- ❌ **Twitch streams, spectator chat, highlight reels** (Reviewer #2) — community-scaling before methodology-lock. Cart before horse.
- ❌ **User-designed arenas, custom weapons** (Reviewer #2) — amplifies contamination risk. Kill until prompt versioning + frozen eval pack exist.
- ❌ **Dynamic hazards, procedural maps, stamina, wind** (Reviewers #1 + #2) — adds simulation surface area without corresponding scientific measurement.
- ❌ **Prize tournaments, seasonal challenges** (Reviewer #2) — tournaments already exist (`tournament.py`). More frequency ≠ more rigor.
- ❌ **Adversarial noise injection into state** (Reviewer #2) — legitimate research angle but Tier C. Do Tier S then A first.
- ❌ **Partner with LMSYS** (Reviewer #4) — wish, not a "do this." Reach out only after Research ≥ 8.0 + published dataset.
- ❌ **JOINT-mode hybrid controller** (Reviewer #1) — interesting but doesn't unblock main benchmark. Save for Tier C.
- ❌ **"Video is being simulated" copy** (user suggestion during legibility session) — the word "video" makes it MORE game-like; used "Running match — LLMs are thinking" instead.
- ❌ **Reverse countdown timer on wait screen** — reverse countdowns that hit 0:00 while nothing happened would panic the user. Used elapsed + expected range instead.
- ❌ **Separate `/about` page as first legibility move** — bounce happens before the click; put explainer inline in hero + FAQ + wait panel first. `/about` is Tier B nice-to-have.
- ❌ **Force voting before showing any reveal** — kills first-time visitor experience; they'll bounce not vote. Used soft "reveal locked behind vote" framing instead.
- ❌ **Email capture / login for leaderboard access** — kills 90%+ of anonymous traffic. Never.
- ❌ **Bootstrap Elo confidence intervals** (originally in Tier-S #4) — compute-heavy on every LB load. Wilson score CI on win-rate is closed-form O(1) and is the LMSys standard; shipped instead as `_wilson_ci()`.

---

## Live surfaces + credentials

| Surface | URL |
|---|---|
| Frontend (Vercel) | https://stickblade-arena.vercel.app |
| Backend API (HF Space) | https://pioneer37-stickman-arena.hf.space |
| GitHub source | https://github.com/Cometbuster4969/STICKBLADE-ARENA |
| HF Space | https://huggingface.co/spaces/Pioneer37/Stickman-Arena |
| Pymunk showcase | https://www.pymunk.org/en/latest/showcase.html#stickblade-arena |
| PeerPush listing | https://peerpush.com/p/stickblade-arena |
| GitHub Sponsors | https://github.com/sponsors/Cometbuster4969 |

**Deploy pipeline:**
- Push to `origin` → GitHub → Vercel auto-deploys frontend (~90s)
- Push to `huggingface` → HF Space rebuilds Docker (~2 min)
- **Schema changes:** ALWAYS run `stickblade/supabase_schema.sql` in
  Supabase Dashboard SQL Editor BEFORE pushing to HuggingFace, or the
  backend picks up new code against old schema and everything breaks.
  Migration is idempotent. Learned the hard way (Jul 18 + Jul 23).

**GitHub Actions status:** 8 jobs, ~1 min wall time, matrix Py 3.11-13 + Node 20/22.

---

## How to update this file

**Every session that ships anything or discusses future work must update
this file before the session ends.** Rules:

1. **New ship** → add a bullet to the top of "Shipping timeline" with:
   - Date · commit SHA · one-line summary
   - Optional "Why it mattered" note if the reasoning isn't obvious
   - Anchor grade delta if applicable (Codebase / Security / Research)
   - Update "Last updated" at the top of the file with new tip SHA
2. **New idea discussed but not shipped** → add to Roadmap under the
   appropriate tier. Include:
   - Effort estimate (weekends)
   - Anchor grade target if measurable
   - Which reviewer(s) or session(s) suggested it, if applicable
3. **Idea rejected** → add to "Deliberately deprioritized" WITH THE
   REASONING. Future sessions must be able to see why. Never delete
   entries from this section; the ledger prevents re-relitigation.
4. **Idea moved between sections** — leave a note (e.g., "was Tier B,
   promoted to Tier A because dataset dump shipped").

**Anti-pattern to avoid:** don't update TIMELINE.md as marketing copy.
It's a working document for future agents. Honesty > polish. If an item
is behind schedule, say so. If a shipped feature turned out to be worse
than expected, log it under "Shipping timeline" with a "reality check"
note.

**Format discipline:**
- Reverse chronological in "Shipping timeline"
- Ranked by impact/effort in Roadmap (highest first per tier)
- Kill list stays sorted roughly by "how many times someone re-proposed
  this" — put the most tempting-to-re-propose items at the top so
  future agents hit them first when skimming.

**When there's a genuinely different opinion** about whether to ship
something, log both sides briefly in Roadmap and let the maintainer
(@Cometbuster4969, Ayush Kumar) decide. Don't cave to whichever LLM
argued last — that's exactly the sycophancy protocol §0.5 of AGENTS.md
exists to prevent.
