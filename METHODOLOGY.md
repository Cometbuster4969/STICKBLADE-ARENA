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

### 3.3b Bradley–Terry with confidence intervals (`stickblade/ratings.py`)

Elo is a good live scoreboard and a weak scientific claim: it updates
sequentially, so two models with identical records can end up with
different ratings depending on the order their matches happened to arrive
in, and it carries no interval. Neither is fixable inside Elo, because both
are properties of the update rule, not of the data.

So the benchmark publishes a second rating alongside it. `/api/leaderboard/
bradley_terry` fits all voted comparisons in a cell at once by maximum
likelihood:

- **Model.** Bradley–Terry with a Davidson tie term (`stickblade/ratings.py`,
  `bradley_terry()`). For models *i*, *j*: `P(i ≻ j) = p_i / (p_i + p_j +
  ν√(p_i p_j))` — ν > 0 puts mass on the draw outcome rather than deleting
  it, which matters for us because draws are a real and frequent outcome.
- **ν is estimated, not assumed.** Holding ν at a constant silently
  compresses the whole field: with ν ≡ 0.5 a 90/10 record fitted to 1.213
  logits instead of the analytic `ln 9 = 2.197`. The fitter solves the score
  equation for ν and forces ν = 0 when there are no draws.
- **Ridge shrinkage (`DEFAULT_RIDGE = 1.0`).** A model that is 3–0 has an
  infinite MLE. The ridge keeps every estimate finite, which is exactly the
  sparse-data failure mode that makes small-sample leaderboards lie.
- **Identifiability.** Ratings are centred per fit, and only within a
  connected component of the comparison graph are they comparable at all.
  Components are reported (`component`, `component_size`) and anything
  outside the main one is flagged `provisional`, rather than being placed
  in a ranking it has no claim to.
- **Intervals.** `fit_with_ci()` bootstrap-resamples the comparison set and
  reports the 2.5/97.5 percentiles. Intervals must widen as n falls — that
  property is pinned by a test, not asserted in prose
  (`tests/test_ratings.py::test_more_data_gives_a_tighter_interval`).
- **Scale.** Ratings are reported as `1000 + (400/ln 10)·θ` purely for
  readability. This is **not** Elo, and the numbers are not comparable to
  the Elo column.

The UI shows tie letters: models whose intervals overlap share a letter and
are described as *not separable*, because publishing a sorted list invites
readers to read rank order as a result even when the data does not support
one.

### 3.3c Expert and casual evaluators are not mixed (§6)

A viewer may prefer the dramatic fighter even when it made the worse
decisions, and an experienced evaluator may systematically disagree with
the crowd. Both facts are only measurable if the two populations are
separable after the fact.

Every vote therefore carries a **self-declared** `voter_tier`
(`casual` | `expert`, `stickblade/storage.py` migration +
`record_vote(..., voter_tier=...)`), and:

- the tier is **recorded, never weighted** — an expert vote does not count
  more, and there is no identity verification behind it, which is precisely
  why it is published as a label rather than used to override anyone;
- ratings can be computed per tier (`/api/leaderboard/bradley_terry?tier=
  expert`), so "do experienced evaluators disagree with the crowd?" is a
  question the dataset can answer later;
- the export carries `votes_expert` / `votes_casual` as separate columns,
  so a downstream analyst can reproduce either tier's leaderboard instead
  of having to trust ours.

### 3.3d The physics is inspectable (§10)

A benchmark result the reader cannot check is an assertion, not a
measurement. The replay player therefore ships a **research debug
overlay** (`stickblade-web/public/player.js`, `drawDebug()`; toggle with
the ⚙ Debug button or the `d` key) that draws, per frame:

| Layer | Source |
|---|---|
| Hitboxes | the same per-body `HALF`/`WIDTHS` capsule table the renderer uses — not an approximation of it |
| Weapon segments | per-weapon blade geometry, with the sharp zone the match was played under highlighted in red |
| Velocity vectors | finite-difference torso velocity (px/s), labelled, so a lunge is visible and stalling is obvious |
| Contact points | `hit`/`clash` events at their recorded coordinates, labelled with damage, body part and attacker |
| Frame / turn / action | frame index, elapsed time, HP, weapon, sharp list, arena, and both fighters' thoughts in force |

Everything is replayed from the stored frame array; **nothing is
re-simulated**, so an audit cannot diverge from the match it audits. The
overlay is off by default (it is noise for a casual viewer) and is
covered by a headless smoke test (`stickblade-web/scripts/check-player.mjs`)
because the player is a vanilla script the Next build never executes.

### 3.3e Cost is measured, not estimated (§33)

Every provider tells us what it billed; the brains accumulate those counts
across retries and buddy fallbacks (`stickblade/brains.py`,
`Brain._record_usage`) and they are persisted on the match row, so
`/api/costs` reports **actual** token spend rather than a guess based on
prompt length. Three rules keep the number honest:

- **Unreported is not free.** A billable match whose provider omitted usage
  is counted in `matches_without_usage` and sets `complete: false`, making
  every total a lower bound until it is filled in.
- **Offline is not missing.** Scripted-versus-scripted matches genuinely
  cost \$0 and are counted as `matches_offline`, so they can never mask a
  real reporting gap.
- **Prices are data.** The price table carries an as-of date and is
  overridable via `STICKBLADE_PRICES_JSON`; the unknown-model fallback is
  deliberately the *most expensive* row, because an under-estimated budget
  fails silently while an over-estimated one just leaves headroom.

Budgets (`BUDGET_DAILY_USD` / `BUDGET_MONTHLY_USD`) report `unset` when
unconfigured — an unconfigured limit is not a healthy one. The access model
(§34, `stickblade/costs.py`, `ACCESS_TIERS`) is published through the same
endpoint: public quick matches, BYOK and research mode are free, and the
only priced tiers are volume/hosting and are marked not implemented.

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

### 4.1 Empirical status (updated 2026-08-13)

The cross-benchmark correlation study was first executed on the 2026-08-04 snapshot and re-executed on 2026-08-13 after the [Tier-A #4 frozen 100-matchup eval pack](../research/frozen_pack_v1.yaml) completed. Full report in `research/cross_benchmark_correlation_report_2026-08-04.md`.

**Post-pack result: 14 models cross the joint filter of `perceived_n ≥ 5 AND matches ≥ 5`** (up from 2 pre-pack). No correlation reaches p < 0.05:

| Population | ρ (Elo vs win-rate) | ρ (Elo vs dmg/turn) | ρ (Elo vs hit-rate) |
|---|---|---|---|
| All (n=14) | +0.099 (p=.74) | −0.285 (p=.32) | −0.372 (p=.19) |
| LLMs only (n=13) | +0.148 (p=.63) | −0.219 (p=.47) | −0.263 (p=.39) |

All 95% bootstrap CIs span zero. This is a null result — but a *scientifically informative* null. What it tells us:

1. **Perceived-Elo and objective win-rate are NOT tightly correlated** (ρ near zero, wide CI). If they were (ρ > 0.85), the two leaderboards would be redundant and one should be collapsed. They aren't — publishing both is empirically justified.

2. **A weakly negative trend on damage_per_turn is worth flagging as a hypothesis** (ρ=−0.29, LLMs-only ρ=−0.22, not significant): consistent with the reading that humans reward tactical patience over aggression. Not a finding — the CI includes zero.

3. **The bottleneck is not matches, it's votes.** The frozen pack fattened `objective_n` (median 2 → 36) but `perceived_n` remained the limiting factor. 11 of 14 filtered models still have `perceived_n < 20`, so Elo hasn't converged past the 1000-baseline prior enough to produce signal above noise.

**What unblocks a defensible ρ:** more human votes. Ranked by ROI: (a) marketing push to drive site traffic, (b) opt-in multi-vote per match (Tier-B roadmap — also unlocks inter-rater κ as a separate publishable finding), (c) NOT a bigger frozen pack (would strengthen per-weapon analysis but doesn't help ρ).

**What we deliberately did NOT do:** loosen the joint filter to `perceived_n ≥ 3` (would pump n=14 to n=25 but trade rigor for headline number — an AGENTS.md §0.5 anti-sycophancy trap). Cherry-picking the most positive of the twelve reported correlations to headline (same trap). Bumping Elo K-factor retroactively (breaks Elo comparability across `prompt_version`).

Publishing this refined null finding openly is consistent with §0.5: the frozen pack was hypothesized to move Research 8.2 → 8.4 conditional on a defensible headline ρ; the ρ isn't there, so the grade doesn't move. What the pack DID deliver: (a) killed the fabricated "ρ ≈ 0.71" claim permanently, (b) established the exact statistical threshold that must be crossed to publish a real number, (c) shipped reproducible tooling (`tools/run_frozen_pack.py` + `research/cross_benchmark_correlation.py`) that will produce the right answer when the vote-count bottleneck resolves.

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
