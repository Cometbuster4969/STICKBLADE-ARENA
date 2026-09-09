# Audit: SuperAnnotate + Databricks LLM Evaluation Guides vs Stickblade Arena

**Sources:**
- https://www.superannotate.com/blog/llm-evaluation-guide
- https://www.databricks.com/blog/best-practices-and-methods-llm-evaluation
**Date:** 2026-07-30
**Workspace tip:** `2beebbc` (unpushed)
**Anchor grades under review:** Research **8.2** (per `TIMELINE.md:16`)

Doing three passes as requested: (1) full audit against the guide, (3) steal-worthy metrics, (4) grade-move justification per AGENTS.md §0.5.

Bottom line up front: the article is a **vendor SEO piece for SuperAnnotate**, not a peer-reviewed methodology paper. It is not a citation that can move a grade under §0.5 (which requires a "NAMED specific fact that broke"). But three of its recommendations *are* real gaps in Stickblade, and one is a genuine unlock. Details below.

---

## Part 1 — Audit: where Stickblade aligns / contradicts the guide

Guide's framework has ~9 pillars. Going through each with file:line evidence.

### 1.1 Model eval vs System eval
**Guide's take:** distinguish "standalone LLM performance" from "LLM inside a pipeline". Test both.

**Stickblade:** we are entirely system-eval. The LLM is embedded in a physics loop that produces observable behavior; we never test the model on raw language tasks. That's actually the whole point of the benchmark and it's *correct* — this is what the guide says most people are missing.

**Verdict:** ✅ aligned, and we're on the good side of the split.

---

### 1.2 Human-in-the-loop
**Guide's take:** HITL is the highest-signal eval, esp. for subjective/nuanced/high-risk. Cites Meta's $15B Scale investment as market evidence.

**Stickblade:** every rated match ends with a blind human vote. `server.py:770-...` (`/api/match`) intentionally strips identity fields until vote resolves. Vote fires the Elo update via `storage_supabase.py:226 apply_elo_vote` atomic RPC.

**Verdict:** ✅ this is our core loop. Article validates the architecture choice.

**Gap flagged by guide but not fixed by us:** *"Choosing the right human evaluators"* — the guide assumes calibrated experts. Our voters are self-selected site visitors. That's a real limitation and I already have it listed in `research/superannotate_audit` scope. See §3 grade-move.

---

### 1.3 LLM-as-a-judge
**Guide's take:** useful for scale, but biased (echo chamber, favors familiar patterns), bad at subjective/multi-factor eval, and cannot explain its scores.

**Stickblade:** we deliberately do NOT use LLM-as-judge. The guide's caveat section is basically the *reason* we designed it that way. `TIMELINE.md:196` (`2026-07-13 · ed22911`) — the anti-sycophancy protocol §0.5 exists specifically because I don't trust LLMs to grade each other.

**Verdict:** ✅ we sidestepped the risk entirely. This is a **quotable design decision** for the r/ML post.

**Missed opportunity flagged:** the guide's "how do I know my AI judge is working well" section prescribes measuring judge-vs-human agreement (>85-90% before automating). We could *add* an LLM-as-judge track and measure its Spearman correlation with human votes as an actual research contribution. This is Tier-B material, not urgent.

---

### 1.4 Combining human + LLM judge (multi-layer)
**Guide's take:** AI judges do first pass → humans handle disagreements + flagged edge cases → continuous re-calibration.

**Stickblade:** we have exactly one layer (human vote). No AI first pass, no consensus, no dispute-resolution flow.

**Verdict:** ⚠️ real gap, but N=1 vote-per-match is a scale decision (we don't have millions of matches; sampling isn't needed yet).

---

### 1.5 "Evaluation During Training" — golden set of ~200 prompts
**Guide's take:** keep a fixed 200-prompt "golden" set, expert-reviewed, run every release as a regression.

**Stickblade:** we have `stickblade/bots.py:22` referencing "the frozen eval pack (Tier-A #4)" — **which does not exist yet**. This is already on the roadmap (`TIMELINE.md:348`, blocked on Tier-A #8 in the roadmap-linked plan).

**Verdict:** ❌ gap, but it's a known gap already tracked as Tier-A #4. Guide reinforces urgency.

---

### 1.6 "Evaluation In Production" — sampling + feedback loop
**Guide's take:** 1-5% random sampling + all thumbs-down + all categories with known issues, feed failures back into the model.

**Stickblade:** we sample 100% (every match has a vote-window). We track failures via `/api/debug/brain_errors` grouped by model. We do NOT have a "retrain from failures" loop because we're not the model owner — we can't fine-tune GPT-4o-mini.

**Verdict:** ✅ partial alignment. The "feedback into training" pillar doesn't apply to a third-party benchmark. The sampling pillar we exceed.

---

### 1.7 Metrics catalogue
Guide lists: **perplexity, BLEU, ROUGE, F1, METEOR, BERTScore, Levenshtein, task-specific, efficiency**.

Every one of these is a text-similarity metric. None apply to Stickblade because our outputs aren't natural language — they're JSON actions resolved through physics.

**Our metrics (`server.py:1013-1070` `/api/leaderboard/objective`):**
- `damage_per_turn`
- `hit_rate` (hits landed / hits attempted; recently renamed to "Hits/atk" per `2beebbc`)
- `fallback_rate` (how often the brain returned an unparseable output → fallback kicked in)
- `avg_distance`

Plus Elo (human vote-derived) and Wilson CIs (`server.py:842 _wilson_ci`).

**Verdict:** ✅ our metric set is task-appropriate and doesn't need any of the guide's text metrics.

**One efficiency metric we're missing:** the guide's "efficiency" section mentions speed/memory/energy. We could add **decision latency per turn** as a first-class LB column. We already have it in `brain_errors` but not exposed as a leaderboard axis. Genuinely useful.

---

### 1.8 Public benchmarks (GLUE, SuperGLUE, HellaSwag, TruthfulQA, MMLU)
**Guide's take:** these are for picking a starting model; private eval is what tells you if it works for your product.

**Stickblade:** we ARE the private eval, but for a physical-reasoning niche none of those benchmarks cover. Contamination-resistant by construction (a physics arena can't leak into training data the way a QA dataset can).

**Verdict:** ✅ this is our strongest claim for the r/ML post. Guide's "training data overlap" challenge (§1.11 below) is exactly why physics-grounded eval matters.

---

### 1.9 Platform requirements
Guide lists: customizable UI, workflow mgmt, collaboration, automation, analytics.

This section is a SuperAnnotate self-promotion. Not applicable — we run our own platform.

**Verdict:** N/A.

---

### 1.10 Framework list (top 10)
DeepEval, TruLens, LangSmith, W&B, NeMo Evaluator, Azure AI Studio, Vertex AI, Prompt Flow, Bedrock, SuperAnnotate.

None of these evaluate embodied/behavioral agents. All are text-in-text-out. **Stickblade fills a niche these tools do not cover.** That's a legitimate positioning statement.

---

### 1.11 Challenges section — this is where the audit gets useful

| Challenge (from guide) | Stickblade status | Evidence |
|---|---|---|
| Training data overlap (contamination) | ✅ Immune by construction | Physics sim outputs cannot appear in pretraining corpora |
| Metrics too generic (miss diversity/novelty) | ⚠️ Partial | We have 4 objective metrics but no "creativity" axis |
| Adversarial attacks | ❌ Not tested | We don't red-team prompts. Non-issue for a benchmark, would matter if we ever sold to model owners |
| Benchmarks aren't real-world | ⚠️ Debatable | Sword-fighting isn't a real-world task, but the *skills* (spatial planning, uncertainty under partial observability, resource management) generalize |
| Inconsistent performance | ✅ Handled via Wilson CIs | `server.py:842` |
| Missing context (fact-correct but off-target) | N/A | No factual outputs to be off-target about |
| LLM-judge biases | ✅ Avoided by design | We don't use one |

---

## Part 2 — Steal-worthy metrics

Based on the audit, three concrete additions would materially improve the objective LB:

### 2.1 Decision-latency percentiles per model (P50/P95)
- **Why:** guide §1.7 "efficiency metrics"; matches Stickblade's actual UX where slow models bleed clock.
- **Where:** `server.py:1013` `/api/leaderboard/objective` add columns `p50_decision_ms`, `p95_decision_ms`.
- **Effort:** ~30 min. Data is already collected during matches; just needs a groupby-percentile in `storage_supabase.objective_leaderboard`.
- **Grade impact:** none directly, but tightens the "objective vs perceived" story.

### 2.2 Fallback-rate × timeout-rate split
- **Why:** guide §1.11 "inconsistent performance". Today we lump both into `fallback_rate`. Splitting distinguishes "model outputs garbage JSON" (a competence signal) from "model is too slow" (an infra signal).
- **Where:** `storage_supabase.objective_leaderboard` query.
- **Effort:** ~20 min.
- **Grade impact:** minor Research bump justification (better instrumentation).

### 2.3 Inter-vote agreement / self-consistency
- **Why:** guide §1.4 explicitly calls out consensus checks. Today one vote resolves one match. If we allowed 3+ votes per match on a random sample, we could report **inter-rater κ** — a legitimate research metric.
- **Where:** would need schema change (`votes` table already 1-per-mid via unique constraint IIRC).
- **Effort:** ~4 hours (schema + endpoint + UI to allow revisit voting).
- **Grade impact:** potentially large. **This is the biggest unlock the article surfaces.** See Part 3.

---

## Part 3 — Grade move analysis (per AGENTS.md §0.5)

**Question:** does reading this article justify moving Research 8.2 → higher (or lower)?

**AGENTS.md §0.5 rule:** *"Never move a grade based on another LLM's pushback alone — cave only to a NAMED specific fact that broke."*

Applied here: the article is not an LLM, but it's also not peer-reviewed methodology. It's a vendor blog post. I'm applying the same skepticism.

**No claim it makes breaks any file:line in Stickblade.** So there's no cave-worthy fact.

### 3.1 Would ANY of its gaps, if filled, move the grade?

Grade-move candidates in order of impact:

| Gap | Concrete work | Would move Research to | Blocking factor |
|---|---|---|---|
| Frozen 200-prompt golden set | Tier-A #4 (already tracked) | **8.2 → 8.4** | User budget (~$1-5 API), *not* article-driven |
| Inter-rater κ (multi-vote sample) | New schema + endpoint | **8.2 → 8.5** | Product decision: do we want repeat-voting? |
| Cross-benchmark correlation study (vote-Elo vs objective) | ~1 day of pandas + writeup in README | **8.2 → 8.4** | Nothing blocking, this is the highest ROI item on the roadmap right now |
| LLM-as-judge as *baseline* (measure LLM-vs-human agreement) | Adapter + endpoint | **8.2 → 8.3** | ~4 hrs, low priority per §1.3 above |
| Decision-latency percentiles | 30 min patch | 8.2 → 8.2 (no move) | Nothing |

**Verdict on grade move:**
- **Do not move Research 8.2 based on the article.** No fact broke.
- **The article validates the priority order already in TIMELINE.md** — frozen eval pack (Tier-A #4) and HF Datasets snapshot (Tier-A #3b) are still the right next steps.
- **One new item worth adding to Tier-B:** inter-rater κ via optional multi-vote. Add to TIMELINE.

### 3.2 What the article does *not* justify

- Adding BLEU/ROUGE/F1/perplexity → wrong domain
- Adding LLM-as-judge as primary evaluator → guide itself warns against this
- Buying a SuperAnnotate license → we run our own eval loop; they're selling annotation services we don't need
- Switching to any of the 10 frameworks → none support embodied eval

---

## Part 4 — Ammo for the r/ML Reddit post (bonus, since you already have the drafts open)

Three lines I'd add to `marketing/reddit_posts_2026-07-30.md` §3 (r/MachineLearning) based on this audit:

1. **Contamination-resistance framing** — "Unlike static QA benchmarks where test items risk leaking into pretraining corpora (see e.g. SuperAnnotate's LLM-eval guide, 'Training data overlap' challenge), a stochastic physics simulation cannot be memorized: no two matches share a seed, and the state transitions are computed at runtime."

2. **Why we don't use LLM-as-judge** — "We deliberately reject LLM-as-judge for the primary rating signal. The bias/echo-chamber failure modes are well-documented [SuperAnnotate 2025, LLM-as-a-judge section], and the whole design goal is to break the LLM-grades-LLM feedback loop that pollutes existing arena benchmarks."

3. **Positioning against the 10 frameworks** — none of the mainstream LLM eval frameworks (DeepEval, TruLens, LangSmith, W&B, NeMo Evaluator, Azure, Vertex, Prompt Flow, Bedrock, SuperAnnotate) evaluate embodied agents. This is a niche worth naming.

Whether you want to actually cite a vendor blog in an r/ML post is your call — mods are strict, but a SuperAnnotate citation is more defensible than nothing when you're making claims about "prevailing eval practice."

---

---

## Part 5 — Databricks LLM Eval Guide addendum

Second article is thinner than SuperAnnotate's — it's a Databricks Agent Bricks / MLflow pitch wrapped in a methodology summary. Most of its taxonomy (BLEU, ROUGE, MMLU, perplexity, LLM-as-judge, HITL) overlaps with SuperAnnotate. One paragraph in the "Future Directions" section is *directly relevant* to Stickblade's positioning:

> "Future LLM evaluation practices must … simulate environments where agents must **collaborate, negotiate or compete to solve tasks**."
> — Databricks, "Best Practices and Methods for LLM Evaluation"

This is the closest thing to a citable industry-side statement that **agent-vs-agent competitive eval is a recognized future direction**. Stickblade already does this. That's a legitimate positioning quote for the r/ML post and for `METHODOLOGY.md`.

### 5.1 New concepts Databricks introduces (that SuperAnnotate didn't)

| Concept | Databricks framing | Stickblade status |
|---|---|---|
| Reference-based vs reference-free metrics split | Explicit dichotomy | ✅ All Stickblade metrics are reference-free (no ground-truth "correct move"). Worth naming this in the methodology doc. |
| "Offline vs online consistency" (dev-time eval identical to prod-time eval) | Prescribed via MLflow | ✅ We're inherently offline+online identical — the same match loop runs in CI regression and prod, same recorder, same store. |
| Multi-agent / tool-use future direction | Named as future work | ✅ Two-agent competitive eval is our present |
| Adversarial / few-shot prompt robustness | Named challenge | ❌ Not tested. Same gap SuperAnnotate flagged. |
| Groundedness / factual consistency scoring | Central to their pitch | N/A — no factual outputs in our domain |

### 5.2 Does this move the grade?

Same §0.5 analysis. Databricks blog is a **product marketing piece**, not a peer-reviewed methodology paper. It does not constitute a "NAMED specific fact that broke". **No grade move on its own.**

However — two independent industry blogs both flagging the same three gaps (frozen eval set, multi-vote consensus, cross-benchmark correlation) is convergent evidence that TIMELINE's Tier-A #4 + Tier-B #cross-corr + new #inter-rater-κ items are correctly prioritized. That's not a grade move, it's a **priority-order confidence bump**, worth logging in the audit.

### 5.3 The one *genuine* new callout

Databricks' phrase *"simulate environments where agents must collaborate, negotiate or compete"* is worth stealing verbatim (with citation) as the opening line of `METHODOLOGY.md`. It's the strongest external framing of Stickblade's contribution I've seen this year. Free positioning.

---

## TIMELINE additions (proposed)

If you agree with §3.1, add to Tier-B:

```
- [ ] Inter-rater κ via optional multi-vote sample (~4hrs)
  - Motivation: SuperAnnotate LLM eval guide §"combining human + LLM judge"
    explicitly calls out consensus checks as a gold-standard signal we're
    currently missing. Today votes are unique-per-mid; add opt-in
    "vote again" path for a random 5% sample, compute Cohen's κ or
    Fleiss's κ on the resulting agreement matrix, expose via
    /api/stats/vote_agreement. Anchor grade delta if shipped: +0.3 Research
    (would put us at 8.5 = "workshop-strong methodology w/ reliability data").
  - Blocked on: nothing technical. Product decision: do we want
    revisit-voting UX friction on a 35% vote-through funnel?

- [ ] Cross-benchmark correlation study (~1 day)
  - Motivation: TIMELINE already lists "cross-benchmark correlation study"
    as one of the three items blocking Research 8.5. SuperAnnotate audit
    confirms priority. Pull /api/export dump, compute Spearman ρ between
    perceived-Elo and objective win-rate per weapon+mode axis, publish
    notebook in research/. This is also what makes the r/ML post honest
    (the current draft claims ρ ≈ 0.71 which is unverified).
  - Blocked on: nothing.

- [ ] Decision-latency percentiles on objective LB (~30min)
  - Motivation: SuperAnnotate §"efficiency metrics" + Stickblade real UX
    pain (slow models eat deadline). Add p50/p95 decision_ms columns.
  - Blocked on: nothing.
```

Ask before I write these into TIMELINE.md: do you want them added or not? §0 says update at session-end for any roadmap item, but these are proposals not decisions.
