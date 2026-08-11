# METHODOLOGY

> Stickblade Arena — a physics-grounded, competitive-agent benchmark for large language models.

**Status:** working draft (2026-07-30). This document is the canonical description of *what* we measure, *how* we measure it, and *why* the design choices are what they are. It is written to survive a peer-review round; every claim links to `file:line` or an external citation. Anchor grades (`Codebase 8.4 · Security 8.7 · Research 8.2`) are tracked in `TIMELINE.md:16`.

---

## 0. TL;DR

Two large language models are embodied as stickman agents in a 2D `pymunk` physics arena. Each turn they receive a JSON world state and return a JSON action, which is resolved through rigid-body physics. A human then watches the resulting replay **blind** (both fighters labeled A / B) and votes which side "fought smarter." The vote fires an Elo update; only *after* the vote does the frontend reveal which model was which. Ratings are keyed on six dimensions: `(model, sharp_zone_on, weapon, mode, arena, blindfolded)`.

We report two parallel leaderboards:

1. **Perceived** — Elo derived from blind human votes, with Wilson 95% CIs (`stickblade/server.py:842`, `_wilson_ci`).
2. **Objective** — win/loss/draw + damage-per-turn, hit-rate, fallback-rate, avg-distance (`stickblade/server.py:1013`, `/api/leaderboard/objective`).

Non-LLM baselines (random, greedy-attack, distance-holder, scripted-heuristic) are always present so a low-Elo LLM is not indistinguishable from an arbitrarily-bad policy (`stickblade/bots.py`).

---

## 1. Motivation and Position

> "Future LLM evaluation practices must … simulate environments where agents must **collaborate, negotiate or compete** to solve tasks."
> — Databricks, *Best Practices and Methods for LLM Evaluation* (2025) [\[1\]](#refs)

Current mainstream LLM benchmarks fall into two families, both of which have known failure modes:

1. **Static Q&A / reasoning benchmarks** (MMLU, HellaSwag, GLUE, ARC, TruthfulQA). Failure mode: **training data contamination**. As datasets age, test items appear in pretraining corpora, and scores decouple from ability. SuperAnnotate flags this as the first-listed evaluation challenge [\[2\]](#refs).
2. **LLM-as-judge arenas** (LMSYS Chatbot Arena, MT-Bench). Failure mode: **judge bias / echo chamber**. LLM judges reward outputs stylistically similar to their own generation, and cannot explain their scores in causal terms [\[2\]](#refs).

Stickblade addresses both:

- **Contamination immunity by construction.** Every match uses a fresh `random.Random(seed)` (`stickblade/bots.py:22`, comment: *"important for the frozen eval pack (Tier-A #4) where we want the… deterministic-per-seed"*). No two matches share a state trajectory, and state transitions are computed at run-time by a physics engine. There is no textual test-set that can leak.
- **Judge-bias avoidance.** The primary rating signal is human, not LLM. LLM-as-judge is not used anywhere in the rating pipeline. This is a deliberate design choice motivated directly by the guide [\[2\]](#refs) [\[1\]](#refs) warnings.

We further argue that *behavioral* eval — where the model must produce actions whose consequences are computed by an independent world model — dominates *textual* eval on the axes that matter for embodied and agentic deployment:
spatial planning, resource management (cooldowns, ammo), decision-making under partial observability (blindfolded mode), and time-pressured reasoning (per-turn deadline).

---

## 2. The Match Loop

### 2.1 World and agents

- **Physics:** `pymunk` (Chipmunk2D bindings), rigid-body dynamics with pin joints and rotary motors driving the sword arm.
- **Body plan:** each agent has 10 rigid bodies in a canonical order (`stickblade/recorder.py:23`, `BODY_ORDER = ["torso", "head", "uarm", "farm", "off_uarm", "off_farm", …]`). The recorder emits the layout in this exact order so the JS replay player can reconstruct scenes from compact JSON.
- **Weapons:** `sword`, `spear`, `flail`, `bow`, `dagger`. Each has distinct reach, cooldown, and damage curves. See `/api/weapons`.
- **Arenas:** planar arena with optional hazard zones ("sharp zones") that damage on contact.
- **Modes:** `normal`, `blindfolded` (opponent position hidden from state JSON, only proximity/sound cues remain).

### 2.2 Per-turn protocol

1. Physics is frozen at a decision boundary.
2. World state serialized to JSON (self-HP, opp-HP, positions, weapon geometry, cooldowns, remaining ammo, damage taken since last decision, arena hazards).
3. State posted to both agents in parallel via `httpx`; each returns a JSON action.
4. Actions are validated against a `json_schema` where the provider supports it (`GPTBrain`, `GeminiBrain` — Tier-A #1, shipped `a98c76c`).
5. Motors and impulses applied; physics steps ~30 frames until next decision.
6. Collision handlers accumulate impulse magnitude per body-part contact and convert to HP damage (see `stickblade/server.py:207`, event schema `{"attacker", "zone", "part", "damage", "sharp"}`).

Match terminates on **KO** (HP ≤ 0), **HP-lead at deadline** (5 min for bow, 3 min otherwise — `stickblade/server.py:309`), or **draw** (equal HP at deadline).

### 2.3 Latency and failover

Per-turn decision timeout is enforced by `decide_with_timeout` (`stickblade/brains.py:718`). Two fast-fail patterns short-circuit retries:
- `reasoning_burnout` (model exhausted its reasoning tokens)
- `"unavailable for free"` (OpenRouter yanked a free-tier slug)

When the primary brain fails or times out, the loop falls back to a **cross-provider buddy pool** (`stickblade/brains.py:420-473`, `_BUDDY_POOLS` keyed on `large / mid / small` capacity tiers). Cross-provider selection means one provider outage does not silently corrupt a tournament.

---

## 3. The Rating Signal

### 3.1 Blind voting

After a match completes, the replay is served with **model identities stripped** (`stickblade/server.py:770`, `/api/match/{mid}` intentionally omits `model_a`/`model_b` until vote resolves). The user sees only "Fighter A" and "Fighter B", watches the replay, and casts one vote. Reveal happens only *after* vote submission, and the reveal is itself a UX reward that materially improved vote-through rate (see §5.2).

This ordering is critical: vote *before* reveal ensures the user's judgment is not polluted by model reputation. This satisfies the human-in-the-loop principle both blogs emphasize: humans catch subtle reasoning quality that automation cannot [\[1\]](#refs) [\[2\]](#refs).

### 3.2 Six-axis Elo primary key

Ratings are indexed on:

```
(model, sharp_zone_on, weapon, mode, arena, blindfolded)
```

not on `model` alone. This is deliberate: different weapon+mode combinations stress different reasoning skills. A model that reasons well about melee spacing may collapse under bow-ammo economy or blindfolded partial observability. Aggregate per-model Elo is a marginalization over these axes, but the per-axis rating is what we study.

Elo updates use `K = 32` on wins/losses; draws count as ½-win per Elo convention. The update is atomic via a Supabase RPC (`stickblade/storage_supabase.py:226`, `apply_elo_vote`) so concurrent votes on the same match do not race.

### 3.3 Wilson confidence intervals

Every leaderboard row publishes a Wilson 95% CI (`stickblade/server.py:842`, `_wilson_ci(wins, losses, draws, z=1.96)`) on the win-share `p_hat = (w + d/2) / (w + l + d)`. This is included because raw win-percentage with `n=3` matches is meaningless, and readers need to see rating uncertainty.

### 3.4 Prompt version pinning

Every match is stamped with `PROMPT_VERSION` (`stickblade/brains.py:36`, currently `1`), exposed via `/api/version` and on every leaderboard row. When the state-JSON schema or the system prompt changes, this integer bumps and downstream dataset consumers can filter for the version they need (`stickblade/brains.py:148-154`, protocol documented in `AGENTS.md §PROMPT_VERSION_LOG`).

This is our answer to Databricks' "offline and online consistency" requirement [\[1\]](#refs): dev-time and prod-time evaluation run the *identical* match loop against the *identical* `PROMPT_VERSION`, and the recorder emits the identical schema. CI regression exercises the same code path (`.github/workflows/ci.yml:170-195`).

---

## 4. The Objective Leaderboard

Parallel to human-vote Elo, `/api/leaderboard/objective` (`stickblade/server.py:1013`) exposes:

| Metric | Definition |
|---|---|
| `wins / losses / draws` | Outcome tally per side |
| `damage_per_turn` | Total damage dealt / turns taken |
| `hit_rate` | Hits landed / hits attempted (can exceed 1.0 for multi-hit weapons like flail — rendered as raw decimal, column labeled "Hits/atk"; see hotfix commit `2beebbc`) |
| `fallback_rate` | Fraction of turns where the primary brain failed and the loop fell back to a buddy pool |
| `avg_distance` | Mean inter-agent distance across the match |

The reason for two leaderboards is that they answer different questions:

- **Perceived Elo** captures what a human considers *smart* play — anticipation, spacing discipline, decision-under-uncertainty.
- **Objective stats** capture what actually happened mechanically.

The gap between them is the benchmark's most interesting signal. For example, in bow matches humans reward "smart waiting for cooldown" that does not show up in raw damage. Formal cross-benchmark correlation analysis is Tier-B work (see `TIMELINE.md` — cross-benchmark correlation study).

### 4.1 Empirical status (2026-08-04)

The cross-benchmark correlation study was first executed on the 2026-08-04 snapshot (467 matches, 106 votes) and is written up in `research/cross_benchmark_correlation_report_2026-08-04.md`. Result: **the study is underpowered at current scale.** Only 2 of the 24 roster models meet the joint threshold of `perceived_n ≥ 5` (rated matches) AND `objective_n ≥ 5` (completed matches), which is the minimum needed for either metric to have moved off its prior. A meaningful Spearman ρ cannot be computed from 2 data points.

Reporting a single-side-filtered ρ from this dataset (e.g. filtering only on `perceived_n ≥ 5` yields ρ = −0.899 for LLMs, p = 0.015) would be dishonest — the striking negative correlation is entirely explained by objective-side small-sample noise, where a model with one lucky win shows as `objective_win_rate = 1.0` against models with dozens of rated matches. The reproducible notebook makes this failure mode explicit.

**What unblocks a defensible number:** the Tier-A #4 frozen 100-matchup eval pack. A 100-match pack across 10 shared models (10 matches per model per axis) would push the joint filter above threshold for enough models to compute a real ρ with a defensible 95% bootstrap CI. This is the next research milestone.

Publishing this null / underpowered finding *before* the eval pack lands is deliberate, per `AGENTS.md §0.5`: reporting negative results is how the anti-sycophancy protocol proves it isn't performative.

---

## 5. Baselines and Roster

### 5.1 Non-LLM baselines (`stickblade/bots.py`)

Following Reviewer #4's suggestion and SuperAnnotate's advice that "generic metrics can make bad models look better than they are" [\[2\]](#refs), we include four scripted policies:

- `bot:random` — uniform action sampling
- `bot:greedy` — always advance and attack
- `bot:distance` — hold optimal weapon range, attack only when opponent is in reach
- `bot:pro` — hand-tuned heuristic combining `greedy` + `distance` with cooldown-aware timing

All are seeded (`random.Random(seed)`) for deterministic reproduction. Their purpose is to define the noise floor: a real LLM should measurably outperform `bot:random`; a *good* LLM should measurably outperform `bot:pro`. Currently `bot:pro` outperforms roughly 30% of the roster on objective metrics — that gap *is* the useful signal.

### 5.2 LLM roster

24 rated entries as of 2026-07-30, spanning OpenAI, Groq, and OpenRouter free-tier providers. Full list in `stickblade/config.py`. Dead-slug hygiene is manual today (see `TIMELINE.md` Tier-B "automated roster liveness cron") and 12 dead slugs have been removed across two commits (`6febb54`, `2beebbc`).

### 5.3 Vote-through rate (2026-07-30)

- Lifetime: 23.9% (106 votes / 443 matches)
- Trailing 7-day: 35.5% (11 / 31)

We report this openly because it's the honest denominator on how many rated matches actually get a human signal. The ~1.5× lift over the pre-`TurnTranscript` baseline (June measurements) is attributed to the *reveal-as-reward* UX pattern (commit `e6092b4`, TurnTranscript component + 2.5s WaitPanel settle).

---

## 6. Reproducibility

- **Full match export** via `/api/export` (JSON and JSONL streaming; `stickblade/server.py:1099`). Every rated match, all frames, all events, all model thoughts, all seeds — downloadable.
- **Deterministic replay off the same seed** is roadmap Tier-B, currently blocked on floating-point non-determinism in the physics step.
- **HF Datasets snapshot cron** is Tier-A #3b, blocked on HF write token / dataset repo creation (user handoff).
- **Frozen 100-matchup eval pack** (Tier-A #4) is designed but not yet run, blocked on ~$1-5 of API budget.

---

## 7. Threats to Validity

Honest limitations, in decreasing order of severity:

1. **Self-selected voter pool.** Site visitors are not a calibrated expert panel. Vote noise is empirically small (Wilson CIs converge fast on high-traffic model pairs) but selection bias remains unmeasurable without a calibration study.
2. **Single-vote-per-match.** We have no inter-rater agreement (Cohen's / Fleiss's κ) because a match can only be voted on once. This is a schema decision, not a technical block; adding a random-sample multi-vote track is planned (`TIMELINE.md` Tier-B, article-driven addition).
3. **Non-determinism.** Physics has RNG in collision resolution; seeds are logged but bit-identical replay is not currently reproducible. Practical determinism (statistical agreement across seed re-runs) is high but not formally measured.
4. **Prompt drift.** `PROMPT_VERSION = 1` currently; when it bumps, historical Elo is not directly comparable across versions. Dataset consumers must filter by `prompt_version`.
5. **Provider heterogeneity.** Fast providers (Groq, Cerebras) win time-pressure fights over slow ones (OpenRouter free-tier, o1-family). We do not currently normalize for this and it likely inflates fast-provider Elo. Splitting `fallback_rate` into `garbage_output_rate` vs `timeout_rate` is planned to at least *measure* the effect.
6. **No adversarial / red-team layer.** Both source guides [\[1\]](#refs) [\[2\]](#refs) flag adversarial testing as necessary; Stickblade does not currently attempt prompt injection or jailbreak eval. Out of scope for competitive-play rating.

---

## 8. Positioning against existing frameworks

None of the ten major LLM evaluation frameworks — DeepEval, TruLens, LangSmith, W&B, NVIDIA NeMo Evaluator, Azure AI Studio, Vertex AI, Prompt Flow, Amazon Bedrock, SuperAnnotate — support **embodied competitive-agent evaluation**. All are text-in / text-out with either reference-based (BLEU / ROUGE / F1 / BERTScore) or reference-free (perplexity / toxicity / coherence) metrics [\[2\]](#refs).

Databricks' own future-work section [\[1\]](#refs) explicitly names competitive multi-agent simulation as the next frontier. Stickblade is a working instance of that frontier that ships today.

---

## <a id="refs"></a>References

[1] Databricks. *Best Practices and Methods for LLM Evaluation.* https://www.databricks.com/blog/best-practices-and-methods-llm-evaluation
[2] SuperAnnotate. *LLM Evaluation: Frameworks, Metrics, and Best Practices.* https://www.superannotate.com/blog/llm-evaluation-guide
[3] Anthropic. *SHADE-Arena: Sabotage Monitoring in Agent Environments.* https://www.anthropic.com/research/shade-arena-sabotage-monitoring (cited in [2] as evidence that behavioral, not textual, eval is necessary for agentic systems.)
[4] Alemohammad et al. *Self-Consuming Generative Models Go MAD.* https://arxiv.org/abs/2307.01850 (cited in [2] as evidence that LLM-graded-by-LLM feedback loops degrade over time; motivates our human-primary rating signal.)

---

## Appendix A. File:line index

Every claim above cross-referenced back to code:

| Section | File:line |
|---|---|
| BODY_ORDER canonical layout | `stickblade/recorder.py:23` |
| Deadline logic (5min bow, 3min other) | `stickblade/server.py:309` |
| `_delayed_clear` LIVE_STATE wipe | `stickblade/server.py:405` |
| Blind-match API endpoint | `stickblade/server.py:770` |
| Wilson CI helper | `stickblade/server.py:842` |
| Objective leaderboard | `stickblade/server.py:1013` |
| Export endpoint (dataset dump) | `stickblade/server.py:1099` |
| Vote-rate stats | `stickblade/server.py:1109` |
| PROMPT_VERSION constant | `stickblade/brains.py:36` |
| Buddy pool definitions | `stickblade/brains.py:420-473` |
| `decide_with_timeout` fast-fail | `stickblade/brains.py:718` |
| Atomic Elo RPC | `stickblade/storage_supabase.py:226` |
| Bots (baseline policies) | `stickblade/bots.py` |
| CI regression | `.github/workflows/ci.yml:170-195` |
| Anti-sycophancy protocol | `AGENTS.md §0.5` |
| Timeline / roadmap | `TIMELINE.md` |

## Appendix B. Change log

- **2026-07-30** — Initial draft. Motivated by industry-guide audit (`research/superannotate_audit_2026-07-30.md`).
