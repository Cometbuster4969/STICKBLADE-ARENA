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

**Last updated:** 2026-08-04 · Cross-benchmark correlation study shipped (null / underpowered finding — kills fabricated ρ ≈ 0.71 claim; grade unchanged). Earlier 2026-07-30: Apache-2.0 license swap + CITATION.cff + NOTICE + 3 Tier-B items + AGPL kill; and METHODOLOGY.md seed + SuperAnnotate/Databricks audit + 3 Tier-B items.
**Live grades (per AGENTS.md §0.5 anchors):** Codebase 8.4 · Security 8.7 · Research 8.2

**Live vote-through rate (measured 2026-07-XX):**
- Lifetime: **23.9%** (106/443)
- Trailing 7-day: **35.5%** (11/31)
- ~1.5x improvement over pre-reveal-as-reward baseline (Jul 18: 22.6% / 34.2%).
  Legibility + transcript changes are holding; keep monitoring for the
  next re-baseline after HN re-submit.

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

## Pending push (workspace ahead of GitHub)

> Live-tracked list of changes committed in the workspace but not yet on
> GitHub `main`. Verified byte-for-byte against `raw.githubusercontent.com`
> whenever this section is updated. When you push from your laptop and
> `curl` confirms the file is live, move the entry to the shipping
> timeline below and delete it from here.
>
> **Why this section exists:** the workspace and laptop are separate
> clones. This session used a `patches/` folder as a transfer format but
> that added a step that could go stale. Since the user pushes directly
> from their laptop, this log is the canonical "what still needs to
> ship" tracker. Do not push anything not listed here.
>
> **Last verified against live GitHub:** 2026-08-04

### Currently pending

| Priority | File | What & Why | Ready? |
|---|---|---|---|
| 🔴 SECURITY | `.github/workflows/ci.yml` | Aikido supply-chain scan flagged `lycheeverse/lychee-action@v2` as a floating third-party ref. Pinned to SHA `e7477775783ea5526144ba13e8db5eec57747ce8` (= v2.9.0, verified via GitHub API). One-line change. | ✅ YES |
| 🟡 UX BUG | `stickblade-web/app/replay/page.js` | Missing `timeout_draw` in the draw-copy branch (parallel to `page.js` which already has the fix). One-line change. Users on `/replay?id=...` links see wrong copy on time-cap draws. | ✅ YES |
| 🟢 DOCS | `METHODOLOGY.md` | Adds § 4.1 Empirical status with honest cross-benchmark study results (null, underpowered). | ✅ YES |
| 🟢 DESIGN | `design/chatbot_widget.md` | New folder + file. Full design blueprint for post-Tier-A-#4 "Ask the Arena" chatbot widget. Retrieval-over-docs (not free-form gen), floating widget bottom-right, strict system prompt with 5 prompt-injection defense layers, rate limits, cost caps, explicit exclusion list for private docs (applications/, study/), kill-switch flag. NOT to be built until Tier-A #4 frozen eval pack ships. | ✅ YES |
| 🟢 SEO | `stickblade-web/app/layout.js` | 3 fixes: (a) meta description 96 → 152 chars (uses full Google SERP budget, names concrete model providers), (b) JSON-LD license MIT → Apache 2.0 (drift from July license swap), (c) added `icons` + `manifest` metadata for favicon set. | ✅ YES |
| 🟢 SEO | `stickblade-web/public/llms.txt` + `llms-full.txt` | Fixed stale roster count. Both files said "29 free models" — actual live roster is 24 total (18 LLMs + 4 bots + 2 mocks). Updated to accurate breakdown per provider, with pointer to live `/api/models` as authoritative source. | ✅ YES |
| 🟢 SEO | `stickblade-web/public/favicon.ico`, `favicon-16/32/48.png`, `apple-touch-icon.png`, `android-chrome-192/512.png`, `site.webmanifest` | New. Full favicon set generated from `/home/user/logos/stickblade-logo-1-action.png`. Fixes 404s on `/favicon.ico`, `/apple-touch-icon.png`, `/manifest.json` that showed up in real-audit against the site. | ✅ YES |
| 🟢 DOCS | `applications/` (6 files) | New folder. 5 grant/accelerator application drafts (HF CPU grant, Snorkel Open Benchmarks, India research programs via BIT-Mesra faculty co-sign, LTFF, Buildspace) + README. Every file has same 6-part structure: reality check + deadline + steps + ready-to-send draft + reusable template + after-you-submit. Deadlines verified 2026-08-04. Honest about odds and framing traps. | ✅ YES |
| 🟢 DOCS | `study/` (21 files) | New folder. Interview + demo prep guide. README + 20 numbered topic files across 3 tiers (must-know / should-know / skim). Every topic ties back to file:line in the codebase and has "what they'll ask" + "30-second answer" sections. | ✅ YES |
| 🟢 DOCS | `TIMELINE.md` | This file — updated with Aug 4 shipping entries + this pending-push section. | ✅ YES (self-referential) |
| 🟢 RESEARCH | `research/cross_benchmark_correlation.py` | Executable notebook. Spearman + Kendall + bootstrap CIs. | ✅ YES |
| 🟢 RESEARCH | `research/cross_benchmark_correlation_report_2026-08-04.md` | Findings write-up. Publishes null result openly. | ✅ YES |
| 🟢 RESEARCH | `research/export_snapshot_2026-08-04.json` | 467 matches, checked in for reproducibility. | ✅ YES |
| 🟢 RESEARCH | `research/lb_perceived_snapshot_2026-08-04.json` | 36 rows. | ✅ YES |
| 🟢 RESEARCH | `research/lb_objective_snapshot_2026-08-04.json` | 22 rows. | ✅ YES |
| 🟢 RESEARCH | `research/superannotate_audit_2026-07-30.md` | Industry-guide audit vs Stickblade. Prior session. | ✅ YES |
| 🟢 DOCS | `marketing/reddit_posts_2026-07-30.md` | 4 launch-post drafts. r/ML draft NOW HONEST after cross-benchmark study killed the fabricated `ρ ≈ 0.71` line. | ✅ YES |

### DO NOT PUSH (workspace differs but pushing would be a regression)

| File | Why not |
|---|---|
| `stickblade-web/package.json` | Workspace missing `@vercel/speed-insights` that GitHub has. Push would silently remove a working dep. |
| `stickblade-web/package-lock.json` | Same reason. |
| `stickblade-web/public/og-image.png` | GitHub is a 131-byte LFS pointer; workspace is 673 KB raw. Push would break LFS setup. |
| `.gitattributes` | GitHub has it, workspace doesn't. Must survive on GitHub or LFS breaks. |
| `.github/FUNDING.yml` | Workspace has instructional comments GitHub doesn't. Non-functional either way. Skip. |

### Push command reference

```powershell
cd "C:\Users\ayush\projects\helloworld\top secret\Stickman-Arena"
git pull origin main

# Copy ONLY the "Ready ✅ YES" files from the workspace, at their same
# relative paths. Explicitly check `git status` shows nothing in the
# "DO NOT PUSH" table.

git add METHODOLOGY.md TIMELINE.md .github/workflows/ci.yml \
        stickblade-web/app/replay/page.js \
        marketing/reddit_posts_2026-07-30.md \
        research/

git status  # SANITY CHECK against DO-NOT-PUSH table above

git commit -m "sec+research+ux: Aikido CI pin + cross-benchmark study (null) + replay timeout_draw fix"
git push origin main
git push huggingface main
```

### Verify after push

```bash
# Aikido pin should be SHA
curl -s https://raw.githubusercontent.com/Cometbuster4969/STICKBLADE-ARENA/main/.github/workflows/ci.yml | grep lycheeverse
# want: uses: lycheeverse/lychee-action@e7477775783ea5526144ba13e8db5eec57747ce8 # v2.9.0

# Replay page should have timeout_draw
curl -s https://raw.githubusercontent.com/Cometbuster4969/STICKBLADE-ARENA/main/stickblade-web/app/replay/page.js | grep -c "timeout_draw"
# want: 1

# Research files should be 200
for f in cross_benchmark_correlation.py cross_benchmark_correlation_report_2026-08-04.md; do
  curl -s -o /dev/null -w "$f: %{http_code}\n" "https://raw.githubusercontent.com/Cometbuster4969/STICKBLADE-ARENA/main/research/$f"
done
# want: 200 200

# METHODOLOGY §4.1 present
curl -s https://raw.githubusercontent.com/Cometbuster4969/STICKBLADE-ARENA/main/METHODOLOGY.md | grep -c "4.1 Empirical status"
# want: 1
```

---

## Shipping timeline (what's done)

Reverse chronological. Every ship gets: date · commit(s) · one-line summary.
Long commits get a "Why it mattered" note.

### Chatbot design draft — "Ask the Arena" (Aug 11, 2026)

- **2026-08-11** · workspace — **`design/chatbot_widget.md` created** (blueprint, not code)
  - User raised the idea of adding a chatbot that "tells everything about this website." Pushed back with 5 real objections: (1) vote-through 63.2% means visitors WHO LAND aren't confused, they're few — chatbot solves wrong problem; (2) 5 explainer surfaces already exist (hero, FAQ, WaitPanel, TurnTranscript, OnboardingCard) — 6th duplicates effort; (3) real cost is 3-4 days = same budget as Tier-A #4 which unblocks higher-ROI items; (4) new prompt-injection attack surface with BYOK keys in localStorage; (5) ongoing per-message LLM cost.
  - User confirmed: WANT the chatbot, but AFTER Tier-A #4 frozen eval pack. Design goal is bounce-reduction + educating curious users (not customer support).
  - Rather than ship 3-4 days of code today (wrong sequencing per own analysis), wrote a design blueprint so future-me can build in 2 days.
  - **Key design decisions locked in:**
    - Retrieval over static docs, NOT free-form LLM generation (eliminates "make up plausible lies about the project" failure mode)
    - Floating widget bottom-right (per user answer)
    - Strict system prompt with 5 rules including "cite source for every claim" and "'I don't know' is a valid answer"
    - Prompt-injection defenses layered: input filter regex + strict system prompt + output filter for key patterns + refusal for role-hijack attempts
    - Rate limits: 10 msgs/hour per IP, $5/day global cost cap with retrieval-only fallback
    - Explicit exclusion list: NEVER embed `applications/` (grant drafts w/ personal odds analysis) or `study/` (interview prep) into corpus
    - Kill switch via `config.chat_enabled` flag for 30-second rollback
    - Success/failure criteria defined so it's clear when to revert
  - **Timeline:** do NOT build until Tier-A #4 ships. Design doc estimated to save 1-2 days of build time later.
  - Anchor grade delta: **none** (design draft, not code). Building the chatbot later will not move any grade — that's the honest analysis in the doc.

### SEO fixes — real-audit vs scam-scanner (Aug 8, 2026)

- **2026-08-08** · workspace — **Real SEO audit against live URL** (killed a scam scanner + shipped 3 real fixes)
  - **Context:** user pasted results from an "On-Page and Technical SEO analysis" scanner that scored the site 75/100 with "Technical: 15/F" and a "buy the upsell to see fixes" pitch. On inspection, the scanner had scanned a MALFORMED URL (`stickblade-arena.vercel.app/https:/stickblade-arena.vercel.appGrade` — literally the homepage URL glued with the word "Grade" appended). Every downstream metric was measuring the 404 page's error content, not the actual site.
  - **Ran a real audit** using curl + Google PageSpeed Insights API + Mozilla-Observatory-style header checks. Actual grade: **A- / ~92/100.** Full audit findings kept in session log.
  - **Real issues found + fixed this commit:**
    1. `llms.txt` and `llms-full.txt` both said "29 free models" — actual live roster is 24 (18 LLMs + 4 bots + 2 mocks). Same drift class as the fabricated `ρ ≈ 0.71` cross-benchmark number. Fixed with live-verified breakdown per provider and a `curl` pointer to the authoritative `/api/models` endpoint.
    2. Meta description was 96 chars — 60%% of Google's ~155-char SERP budget wasted. Expanded to 152 chars with concrete model names (GPT-4o, Llama, Kimi) and license posture (Apache 2.0) to improve SERP CTR.
    3. JSON-LD `license` field still pointed at MIT despite the 2026-07-30 Apache 2.0 relicense. Updated to `https://www.apache.org/licenses/LICENSE-2.0` — fixes structured-data drift.
    4. `favicon.ico`, `apple-touch-icon.png`, `manifest.json` were all 404. Generated full favicon set from `/home/user/logos/stickblade-logo-1-action.png` at 16/32/48/180/192/512 sizes, added multi-res `.ico`, wrote `site.webmanifest`, wired both into `layout.js` `icons` + `manifest` metadata.
  - **Real non-issues confirmed (do not fix):** `ai.txt` (not standardized, ignore); Privacy Policy / ToS / Cookie Policy (no PII, no cookies, not required for a public benchmark); "indexable: No" (was measuring the scanner's own 404 URL, not our real page).
  - **Vercel edge served 4.8-day-stale HTML** on the tested request (`age: 416124`). Not a bug — Next.js ISR by design. Client-side JS updates on load. Flagged for future consideration if we ever add server-rendered dynamic content that must be fresh.
  - Anchor grade delta: **none.** SEO is not a §0.5 rubric category. But the "meta desc uses full budget + favicon set + accurate llms.txt" all incrementally improve discoverability and AI-agent citation quality, which supports the Research grade indirectly.

### Applications folder — 5 grant/accelerator drafts (Aug 4, 2026)

- **2026-08-04** · workspace — **`applications/` folder created** (6 files)
  - README + 5 application drafts: HF CPU grant, Snorkel Open Benchmarks, India research programs via BIT-Mesra faculty co-sign, LTFF, Buildspace Nights & Weekends.
  - Every file follows same 6-part structure: reality-check (honest odds) + verified deadline + steps-before-applying + ready-to-send draft + reusable template + after-you-submit protocol.
  - Deadlines and program details verified via web search 2026-08-04.
  - Dropped from earlier list: Open Philanthropy LLM benchmarks RFP (closed Feb 2025 after $25M distributed), Neo Scholars (US-only eligibility), YC/a16z/Sequoia (not ready per session's honest verdict).
  - **Honest framing throughout:** every draft acknowledges what's weak, what could sink the application, and what to fix before submitting. No inflated numbers, no fabricated safety-relevance connections. Vote-through and match count values are placeholders to be re-verified live before submission.
  - Priority sequence (weeks 1-8) documented in README. Recommendation: HF grant → BIT-Mesra faculty outreach → Snorkel (AFTER frozen eval pack ships) → Buildspace → LTFF (hardest, needs strongest safety framing).
  - Anchor grade delta: **none.** Prep material, not project artifact.

### Study folder — interview + demo prep guide (Aug 4, 2026)

- **2026-08-04** · workspace — **`study/` folder created** (21 files, 1079 lines)
  - README + 20 numbered topic files (`01_elo_rating.md` through `20_rlhf_lineage.md`).
  - Three tiers: **Tier 1** (must know cold — 6 topics: Elo, Wilson CI, eval paradigms, contamination, FastAPI async, pymunk); **Tier 2** (should know well — 8 topics: rank correlation, JSON schema output, retries, Next.js, Supabase, BYOK, bootstrap, supply chain); **Tier 3** (skim only — 6 topics: Docker/HF Spaces, pygame headless, CSP/CORS, statistical power, ragdoll IK, RLHF lineage).
  - Every topic file follows the same 5-part structure: What it is / Why Stickblade uses it / What they'll actually ask you / 30-second answer / Where to learn it. Every claim traces back to a file:line reference in the codebase per §0.5.
  - Includes a 5-minute pre-interview refresher + memorized 30/60-second pitch versions.
  - Anchor grade delta: **none.** Prep material for me, not a project artifact that moves grades.

### Cross-benchmark correlation study (Aug 4, 2026)

- **2026-08-04** · workspace — **Cross-benchmark correlation study executed** (Tier-B item, was highest-ROI unblocked)
  - New artifacts:
    - `research/cross_benchmark_correlation.py` (executable notebook, Spearman + Kendall + 2000-iteration bootstrap CIs, both-side sample-size filters)
    - `research/cross_benchmark_correlation_report_2026-08-04.md` (findings write-up)
    - `research/export_snapshot_2026-08-04.json` (467 rated matches, checked in for reproduction)
    - `research/lb_perceived_snapshot_2026-08-04.json`, `research/lb_objective_snapshot_2026-08-04.json`
  - **Headline finding:** **the study is underpowered at current scale.** Only 2 of 24 roster models meet the joint threshold of `perceived_n ≥ 5` AND `objective_n ≥ 5`, the minimum needed for either metric to have moved off its 1000-Elo prior / lucky-single-match win-rate.
  - Single-side-filtered ρ values (perceived_n ≥ 5 only) look striking (LLMs: ρ = −0.899, p = 0.015) but are entirely explained by objective-side small-sample noise (a model with 1 lucky win shows as `win_rate = 1.0`). Report explicitly rejects publishing these as a headline number.
  - **Anti-sycophancy dividend:** the report **kills the fabricated `ρ ≈ 0.71` line** that was sitting in the r/ML post draft (`marketing/reddit_posts_2026-07-30.md:114`). Replaced with an honest "underpowered, unblocks with frozen eval pack" statement. `METHODOLOGY.md § 4.1 Empirical status` added with the same honesty.
  - **Grade delta: NONE.** TIMELINE claimed shipping this study would push Research 8.2 → 8.4. That was conditional on producing a defensible headline number. It didn't (correctly — the data isn't there yet), so per §0.5 the grade does not move. What the report DID deliver: (1) killed a fabricated claim, (2) established the exact statistical threshold that must be crossed before the study is meaningful, (3) shipped a reproducible notebook that will auto-produce the right answer when the data catches up. That's a Research **rigor** win that doesn't move the anchor number.
  - **Unblocks:** re-run this notebook after Tier-A #4 (frozen 100-matchup eval pack) lands. Expected finish state: n ≥ 10 shared models each with n ≥ 10 per axis; then a real Spearman ρ with defensible bootstrap CI is publishable.

### License hardening + citation infra (Jul 30, 2026)

- **2026-07-30** · workspace tip — **LICENSE swap: MIT → Apache 2.0** + `NOTICE` + `CITATION.cff`
  - **Why now:** external LLM review suggested switching to AGPL for "anti-theft protection." Pushed back with evidence: AGPL is correct for SaaS-model companies (Grafana, PostHog, Supabase) but *actively harmful* for a benchmark that wants to be adopted and cited by AI labs. Google/Anthropic/OpenAI legal teams will not run their models against an AGPL suite — creates ambiguity about whether model outputs become derivative works. AGPL kills the "become the reference benchmark" path in exchange for protection against a threat model (someone forking our SaaS) that doesn't apply to us.
  - **What Apache 2.0 gets us over MIT:** (a) explicit attribution requirement in redistributions (§4c), (b) patent grant + termination on litigation (§3), (c) NOTICE file mechanism for provenance. All wins for a benchmark; zero adoption-chill vs MIT.
  - **CITATION.cff:** GitHub renders a "Cite this repository" widget on the repo homepage from this file. Half the researchers who would otherwise forget to cite will use that button. Points at repo + live site, keyword-tagged for discoverability, cites Apache-2.0.
  - **NOTICE:** Apache §4c requires this file if it exists; establishes attribution baseline for any derivative work.
  - **What this does NOT protect against:** attribution theft in papers (defense = arXiv preprint of METHODOLOGY once cross-benchmark study lands + HF Datasets DOI), a big lab re-implementing under a new brand (defense = first-mover speed + citation graph). No legal instrument fixes either.
  - Anchor grade delta: **none** (licensing is neither Codebase nor Security nor Research per §0.5). Publishing DOI + arXiv would move Research; this is just the enabling groundwork.

### METHODOLOGY.md + industry-guide audit (Jul 30, 2026)

- **2026-07-30** · workspace tip — **`METHODOLOGY.md` seed committed** (research/paper prep)
  - New root-level file. Working draft of the canonical benchmark methodology write-up: motivation, position vs static QA + LLM-as-judge arenas, per-turn protocol, 6-axis Elo rationale, Wilson CI justification, dual-leaderboard (perceived + objective) argument, baselines, threats to validity, framework positioning, refs.
  - Every claim cross-referenced back to `file:line` in Appendix A (per AGENTS.md §0.5). Anchor grades stamped in header.
  - Two external citations planted: Databricks LLM eval guide (2025) for the "future benchmarks must simulate competing agents" positioning quote — best external validation of Stickblade's contribution we have — and SuperAnnotate LLM eval guide for the LLM-as-judge bias / contamination-immunity framings.
  - **Why it mattered:** the r/MachineLearning post drafted this session claims `ρ ≈ 0.71` between perceived-Elo and objective win-rate — that number was fabricated as filler. Cannot ship the post honestly without a paper-ish methodology doc + a real correlation study to cite. METHODOLOGY.md is the first half of that; cross-benchmark correlation study (new Tier-B) is the second.
  - Anchor grade delta: **none yet.** File is a seed, not a finished paper. Grade moves only when the paired cross-benchmark study lands.

- **2026-07-30** · workspace tip — **Industry-guide audit** (`research/superannotate_audit_2026-07-30.md`)
  - Full pillar-by-pillar audit of Stickblade against SuperAnnotate's "LLM Evaluation: Frameworks, Metrics, and Best Practices" + Databricks' "Best Practices and Methods for LLM Evaluation".
  - **Verdict per AGENTS.md §0.5:** neither article constitutes a "NAMED specific fact that broke" — both are vendor SEO pieces, not peer-reviewed methodology. **No grade move on the audit alone.**
  - **Real convergent signal:** both independently flag the same three gaps in current eval practice — frozen eval set, multi-vote consensus, cross-benchmark correlation. All three were already on the Stickblade roadmap; external convergence is a priority-order confidence bump, not a grade move.
  - **Actionable output:** 3 new Tier-B items added below (inter-rater κ, cross-benchmark correlation study, decision-latency percentiles). Cross-benchmark study is the highest ROI item on the current roadmap because it unblocks: (a) grade move 8.2 → 8.4, (b) honest r/ML post, (c) METHODOLOGY.md § "gap between leaderboards is the signal" claim.

### UX polish + provider-roster maintenance (Jul 28–29, 2026)

- **2026-07-XX** · workspace tip — **Groq roster cleanup** (this session)
  - Removed 2 more dead slugs after live probe:
    - `groq:meta-llama/llama-4-scout-17b-16e-instruct` — 404 from Groq API (deprecated per Groq docs)
    - `groq:qwen/qwen3-32b` — same
  - Also removed from `_BUDDY_POOLS` in brains.py + `_PROVIDER_HOST` map. Groq roster now 6 entries (down from 8).
  - Total roster now: 24 (10 OR :free + 1 OR paid + 1 OR auto-router + 6 Groq + 2 mocks + 4 bots).
  - Real cost of the bug: 20 buffered `http_404` errors from `llama-4-scout` invocations, each costing ~20s of retry latency before falling through to a buddy. Fast-fail-on-404 (shipped in `6febb54`) softened it but didn't eliminate. Removing at source is the fix.

- **2026-07-XX** · workspace tip — **Copy hint for `timeout_draw` method** (sweep fix)
  - Reveal panel + `/replay` page previously handled `points`, `incomplete_points`, `incomplete_draw` but NOT `timeout_draw` (the most common draw method when both fighters stall at similar HP under the 3-min deadline). Added it to the same "(time-cap reached, HP roughly equal — no clear winner)" copy branch.
  - Zero-impact change but closes a visible copy gap.

- **2026-07-XX** · workspace tip — **Objective LB `hit_rate` column: honest label + formatting**
  - Was labeled "Hit %" and rendered as `Math.round(v*100)+"%"`. But `hit_rate = hits_landed / hits_attempted` isn't bounded [0,1] — multi-hit weapons (flail spike-passes, sword grazes-then-connects) produce > 1.0. Live example: `bot:distance` scored `hit_rate=1.214` which UI displayed as "121%" — misleading.
  - Renamed column to "Hits/atk" with tooltip explaining it's "hit events per attack turn, can exceed 1.0 for multi-hit weapons". Rendered as raw decimal (`1.21`) not percent. `fallback_rate` still renders as %  because that IS a real rate in [0,1].
  - API field name stays `hit_rate` for backward compat with dataset consumers.

### UX: turn-by-turn transcript + wait-panel settle pause (Jul 28, 2026)

- **2026-07-28** · `e6092b4` — **TurnTranscript component + wait-panel 2.5s settle + player.js seek listener**
  - **New component**: `stickblade-web/components/TurnTranscript.js` (198 lines). Persistent scrollable per-turn log below every replay canvas. Each row shows turn number, both fighters' raw LLM reasoning text (color-coded green/blue borders), and inline hit badges (◆ sharp/lethal, ◇ blunt) with damage + part. "⏵ jump" button per row scrubs the replay canvas to that turn's start frame.
  - **Fixed** the actual "turn-wise output not displayed" bug user reported: reasoning WAS in the replay JSON, but the ONLY UI surface was fleeting canvas speech bubbles (~1.5s per turn, y=104, easy to miss). Now visible as a persistent list, expanded by default, collapsible.
  - **`player.js` `replay-seek` event listener**: registered inside `initPlayer()` so both React-mounted players (fight page + `/replay`) pick it up. Cleaned up in `destroy()` to prevent listener accumulation across hot-swaps.
  - **WaitPanel 2.5s settle pause**: on `status=done` detection, schedules a `setTimeout` before firing `onReady`. Fast Groq matches (~30s) previously showed the wait ticker for ~1.5s (one poll cycle) then vanished. Now users get a "✓ Match complete — loading replay…" phase label for 2.5s so they can read the final turns. Cancellation-safe.
  - Blind-safe: transcript uses "Fighter A"/"Fighter B" labels, no reveal leak.
  - Wired into both `stickblade-web/app/page.js` (post-match reveal) AND `stickblade-web/app/replay/page.js` (shared /replay?id=X links).

### 3-in-1 fix arc (Jul 28, 2026)

- **2026-07-28** · `6febb54` — **Bow-specific deadline + fast-fail on dead :free + `points` copy honesty + first roster cleanup**
  - Bow deadline: 3min → 5min (only for bow, melee still 3min). Bow matches structurally slower (kite range, arrow misses).
  - Fast-fail in `decide_with_timeout`: added "unavailable for free" branch to the existing `reasoning_burnout` fast-fail pattern. Skips the redundant same-model retry (saves ~20s per turn on yanked slugs).
  - Reveal panel copy: `method=points`/`incomplete_points` now show "(time-cap reached, higher HP wins — no knockout)" hint. Same for `incomplete_draw`.
  - **First roster cleanup**: removed 10 dead OR :free slugs (verified via live probe: `llama-3.3-70b`, `llama-3.2-3b`, `qwen3-next-80b`, `qwen3-coder`, `gpt-oss-120b`, `hermes-3-405b`, `dolphin-mistral-24b`, `poolside/laguna-m.1`, `poolside/laguna-xs.2`, `liquid/lfm-2.5-1.2b`). Added 3 verified alive: `nemotron-3-nano-omni-30b-a3b-reasoning`, `poolside/laguna-xs-2.1`, `openrouter/free`.

### Prod-outage hotfix (Jul 28, 2026)

- **2026-07-28** · `410c8bc` — **HOTFIX: 100% match failure — `BODY_ORDER` import**
  - Every match on prod since Tier-S #3 push (Jul 27) was failing with `cannot import name 'BODY_ORDER' from 'ragdoll'`. Import was in `recorder._proxy_metrics()` — but `BODY_ORDER` lives at the top of `recorder.py` ITSELF, not `ragdoll.py`. Copy-paste error introduced in Tier-S #3.
  - Users saw: click Fight → wait screen → ~5s later silent error state, no reveal, no vote.
  - Fix: remove the bogus import (BODY_ORDER already in module scope).
  - Why CI didn't catch it: the CI storage regression test passes a fake `{}` replay to `finish_match()`, never calls `rec.build()` → never hits `_proxy_metrics()`. Follow-up (Tier B): add a full end-to-end sim regression that actually calls `rec.build()` to catch this class of bug.

### Tier-A rigor arc (Jul 27, 2026)

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

- [ ] **CI regression: exercise `rec.build()` end-to-end** (post-BODY_ORDER hotfix)
  - Current CI storage regression passes a fake `{'meta':{},'frames':[],'events':[],'thoughts':[]}` replay to `finish_match()`. Never runs `recorder.tick()` for real, never hits `_proxy_metrics()`. That's why the Tier-S #3 `BODY_ORDER` import bug shipped green.
  - Fix: extend the "smoke — all 5 weapons construct + finish a mock match" job to also call `rec.build()` on the completed match, then `store.finish_match(mid, ..., replay=rec.build())`. That path exercises every method the runtime actually uses.
  - Effort: ~30 min.

- [ ] **Automated roster liveness cron** (`tools/verify_models.py` + daily GHA)
  - OpenRouter yanks `:free` slugs every few weeks. Groq deprecates models on their own cadence. Currently these break silently until users report matches falling back to mocks — reported twice in one week (2026-07-27 + 2026-07-XX).
  - Fix: daily GHA that runs the probe I've been doing manually. Loop every slug in `config.ARENA_MODELS`, hit each provider's endpoint, post a GitHub Issue if any go red.
  - Effort: ~1 hour.

- [x] ~~**Cross-benchmark correlation study**~~ (research/notebook) — **SHIPPED PARTIAL 2026-08-04**
  - Notebook + report + snapshots shipped in commit [pending]. Killed the fabricated `ρ ≈ 0.71` claim from the r/ML draft. Study itself is underpowered at current traffic (only 2 models meet joint sample-size threshold) — this is documented, not hidden. See `research/cross_benchmark_correlation_report_2026-08-04.md`.
  - **Follow-up needed:** re-run the same notebook after Tier-A #4 (frozen 100-matchup eval pack) lands. At that point the ρ number becomes publishable and the anchor Research grade moves 8.2 → 8.4.
  - Anchor grade delta on this ship: **none** (per §0.5, no defensible headline number = no grade move; grade moves only when the pending Tier-A #4 unblocks it).

- [ ] **Inter-rater agreement via optional multi-vote sample** (schema + endpoint)
  - Motivation: METHODOLOGY.md §7 lists "single-vote-per-match" as threat-to-validity #2. Both source guides (SuperAnnotate §"combining human + LLM judge"; Databricks §"human oversight is essential") prescribe consensus checks as gold-standard.
  - Fix: opt-in "vote again" path on a random 5% sample of matches. Compute Cohen's κ (2 raters) or Fleiss's κ (3+) on the resulting agreement matrix, expose via `/api/stats/vote_agreement`. Publish rolling κ on the leaderboard header.
  - Anchor grade delta if shipped: **Research 8.2 → 8.5** ("workshop-strong methodology w/ reliability data" tier).
  - Blocked on: product decision — do we want revisit-voting UX friction on a 35% vote-through funnel? Might tank the funnel. A/B test the "vote again" prompt on 10% of users first.
  - Effort: ~4 hours engineering + product decision.

- [ ] **Decision-latency percentiles on objective LB** (30 min patch)
  - Motivation: Databricks §"latency is part of quality" + Stickblade real UX pain (slow models eat deadline; user-visible bug reported multiple times).
  - Fix: add `p50_decision_ms`, `p95_decision_ms` columns to `/api/leaderboard/objective`. Data is already collected per-match in `brain_errors` / recorder; needs a groupby-percentile in `storage_supabase.objective_leaderboard`.
  - Anchor grade delta: none directly, but tightens the objective-vs-perceived story and gives users a real "is this model actually usable" signal.
  - Blocked on: nothing.

- [ ] **Latency-slew evaluation: intelligence vs reflexes Pareto** ⭐ (external LLM review 2026-07-30)
  - Motivation: real production question no benchmark currently answers — does a cheap fast model (3B distilled, ~50ms) actually beat a slow smart model (405B reasoning, ~600ms) once real-world latency is in play? Frontier labs want this data to justify edge-model deployment.
  - Fix: add optional `latency_ms_a` / `latency_ms_b` parameters to match config. `decide_with_timeout` (`brains.py:718`) already gates on per-turn wall-clock; add an explicit `asyncio.sleep(clamp_ms/1000)` before the LLM call to simulate additional latency. Publish Elo curves as a function of imposed latency (per model). Novel paper hook: "at what latency does intelligence stop compensating for reflexes."
  - Anchor grade delta if shipped: **Research 8.2 → 8.4** (genuinely novel eval axis, publishable finding either direction).
  - Blocked on: nothing technical. ~1 weekend engineering + 2-3 weekends of matches to fill the grid.

- [ ] **OOD physics curriculum: dynamic gravity/friction/mass** (external LLM review 2026-07-30)
  - Motivation: static arenas invite memorization / distillation-to-strategy attacks. Testing in-context generalization to shifted physical laws (inverted gravity mid-match, ice→mud friction change, weapon mass fluctuation) probes what robotics labs actually care about.
  - Fix: extend arena config with `gravity_vec`, `friction_coeff`, `weapon_mass_multiplier` and optionally mid-match perturbation events on the pymunk `Space`. Ship a new arena mode `chaos` with randomized parameters per match; keep the standard `arena` axis unchanged so existing Elo doesn't break.
  - Aligns with Databricks' "compete/negotiate/collaborate in complex environments" future-direction quote already cited in `METHODOLOGY.md §1`.
  - Anchor grade delta if shipped: **Research 8.2 → 8.5** (paper-tier novel contribution, provided baselines are established on stable arena first).
  - Blocked on: frozen eval pack (Tier-A #4). Without a stable-arena baseline OOD comparisons are apples-to-oranges. Do NOT ship before Tier-A #4 lands.

- [ ] **Python SDK: `pip install stickblade-eval`** (external LLM review 2026-07-30 — Tier-B'd, not killed)
  - Motivation: researchers currently must use the web UI or hand-roll `httpx` calls against `/api/export`. An `stickblade.evaluate(model_a=..., model_b=..., weapons=[...], matches=N, seed=42)` Python API + CLI would let AI eng teams wire us into CI/CD pipelines for regression testing during fine-tuning.
  - Fix: package `stickblade-eval` on PyPI wrapping the existing HTTP API. Public methods: `evaluate()`, `run_tournament()`, `pull_results(match_id)`, `pull_dataset(since=...)`. Zero backend changes needed — this is pure client-side ergonomics.
  - **Priority verdict:** premature at current scale (106 lifetime votes, zero researcher SDK requests). Roadmap it, don't build until a real user asks OR until frozen eval pack (Tier-A #4) ships and creates the "reproducible eval sweep" use case that justifies an SDK. Track here so it's not forgotten and not re-proposed.
  - Anchor grade delta if shipped: **Codebase 8.4 → 8.5** (Python packaging discipline is a real signal); minor Research bump only if it drives measurable external adoption.
  - Blocked on: (a) real user demand OR (b) frozen eval pack ship. Effort ~1 weekend once triggered.

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

- ❌ **Switch LICENSE to AGPL v3.0 for "anti-theft protection"** (external LLM suggestion 2026-07-30)
  - AGPL is correct for SaaS-model companies (Grafana, PostHog, Supabase) whose competitive threat is "someone forks my SaaS." That is NOT our threat model. Our path to value is "become the reference benchmark that labs cite." AGPL kills that path — Google/Anthropic/OpenAI legal teams will not run their models against an AGPL suite due to derivative-work ambiguity around model outputs. Grad students avoid AGPL to sidestep advisor/institution review.
  - Switched to Apache 2.0 instead (§4c attribution requirement + §3 patent grant), which provides the actual protection we need (attribution + patent defense) without adoption chill. See shipping section "License hardening + citation infra (Jul 30, 2026)".
  - Do NOT re-propose AGPL. Real theft-protection defenses are: arXiv preprint of METHODOLOGY (timestamp), HF Datasets DOI (citation norm), CITATION.cff (GitHub cite button), Apache 2.0 attribution requirement. Legal instruments don't stop attribution theft in papers; those defenses do.

- ❌ **Watermark code with hidden Easter eggs / obfuscated identifiers "to prove theft later"** (external LLM suggestion 2026-07-30)
  - Theater. Git commit history + Apache 2.0 attribution requirement + PeerPush/Pymunk-showcase timestamps already provide public, cryptographic proof of prior authorship. Watermarking degrades code readability with zero incremental legal benefit. If a big lab wants to re-implement, they'll do a clean-room rewrite that no watermark could catch — and if a shady clone copy-pastes verbatim, the git history alone wins the DMCA.

- ❌ **Adversarial prompt sanitization layer for LLM brains** (external LLM suggestion 2026-07-30, defer-not-kill)
  - Not strictly killed — genuinely necessary the day BYOA (Bring Your Own Agent, Tier-B) ships and users can submit custom system prompts. Today we have ZERO user-controlled prompt surface: the state JSON is machine-generated by the physics loop and every field is a bounded numeric. There is nothing to sanitize. Building this before BYOA lands is solving a hypothetical problem.
  - Re-open the moment BYOA reaches design phase. Until then, do not re-propose.

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
