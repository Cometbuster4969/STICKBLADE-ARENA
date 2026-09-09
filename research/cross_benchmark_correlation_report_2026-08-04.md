# Cross-benchmark correlation study — report

**Snapshot:** 2026-08-04 (original) + frozen pack v1 (2026-08-13)
**Script:** [`research/cross_benchmark_correlation.py`](./cross_benchmark_correlation.py)
**Data files (checked in for full reproduction):**
- `research/export_snapshot_2026-08-04.json` — 467 organic rated matches
- `research/lb_perceived_snapshot_2026-08-04.json` — 36 perceived-Elo rows
- `research/lb_objective_snapshot_2026-08-04.json` — 22 objective-stats rows
- `research/frozen_pack_v1_results.csv` — 100 reproducible matches (Tier-A #4)

---

## 2026-08-13 update — post-frozen-pack results

The [Tier-A #4 frozen 100-matchup eval pack](./frozen_pack_v1.yaml) completed on 2026-08-13. Runner: [`tools/run_frozen_pack.py`](../tools/run_frozen_pack.py). Runtime: 199 minutes (matches ~2.5h ETA + throttle). Cost: ~$0.05.

**Re-running the correlation script against the merged export (467 organic + 100 frozen = 567 total matches) produced the following:**

### Headline (n=14 shared models meeting `perceived_n ≥ 5 AND matches ≥ 5`)

| Objective metric | Spearman ρ | Kendall τ | 95% bootstrap CI on ρ | p-value |
|---|---|---|---|---|
| objective_win_rate | +0.099 | +0.099 | [−0.434, +0.631] | 0.737 |
| damage_per_turn | −0.285 | −0.198 | [−0.685, +0.247] | 0.324 |
| hit_rate | −0.372 | −0.251 | [−0.728, +0.170] | 0.190 |

### Same filter, LLMs only (excluding bots+mocks) — n=13

| Objective metric | Spearman ρ | Kendall τ | 95% bootstrap CI on ρ | p-value |
|---|---|---|---|---|
| objective_win_rate | +0.148 | +0.128 | [−0.450, +0.712] | 0.629 |
| damage_per_turn | −0.219 | −0.160 | [−0.690, +0.343] | 0.472 |
| hit_rate | −0.263 | −0.192 | [−0.732, +0.319] | 0.385 |

### Verdict: still underpowered, but for a different reason

**No correlation crosses p < 0.05.** All twelve correlations reported above have p-values in the range 0.19–0.74, and every 95% CI spans zero.

The frozen pack DID solve the objective-side sample-size problem — median `objective_n` jumped from 2 to 36, and 48 models now have objective stats (up from 22). But it **did not** solve the perceived-Elo sample-size problem: 11 of 14 filtered models still have `perceived_n < 20`, meaning their Elo hasn't converged past the 1000-baseline prior enough to produce a signal above the noise floor.

**The real bottleneck is human votes, not matches.** Frozen-pack matches don't generate votes by design (`blind=True, voted=False`) — they exist to fatten objective-side data. Fixing perceived_n requires driving site traffic (marketing) or restructuring the vote pipeline (multi-vote per match — see Tier-B roadmap).

### What we CAN report honestly

Three observations survive the small-n caveat:

1. **The two leaderboards measure different things.** If perceived-Elo and objective win-rate were tightly correlated (ρ > 0.85), we'd have redundant leaderboards. They clearly aren't — ρ hovers near zero. This is *weak* empirical support for METHODOLOGY.md §4's core claim that publishing both leaderboards is justified.

2. **A weakly negative trend on damage_per_turn (ρ=−0.29, LLMs-only ρ=−0.22) is worth flagging as a hypothesis.** *Consistent with* the reading: "humans reward tactical patience; damage/turn rewards aggression." **Not a finding** — the CI includes zero. Would need n≥30 shared models with `perceived_n ≥ 20` each to test rigorously.

3. **Bot ordering is intact.** In the shared frame preview, `bot:pro` sits at Elo 984 and `mock:duelist/berserker` at 985–1007, in the middle-lower half of the roster. LLMs cluster around and above them but with significant overlap. Consistent with the null hypothesis that current-generation LLMs are marginally-to-significantly better than scripted heuristics at Stickblade — but only marginally.

### What we CANNOT report

- ~~"Spearman ρ ≈ 0.71"~~ — this number was fabricated in the r/ML post draft and does not appear in any pipeline output. **Killed.**
- ~~"Perceived Elo and objective win-rate are strongly correlated"~~ — data does not support this.
- ~~"Perceived Elo and objective win-rate are strongly *anti*-correlated"~~ — data does not support this either (the negative trends have p > 0.19 and CIs including zero).
- ~~"Cross-benchmark validation shows the benchmark is sound"~~ — the answer is *"we don't know at this scale."*

### What unblocks a defensible ρ

Ranked by realistic ROI:

1. **Drive more human votes** (marketing push: HN/Reddit posts drafted but not yet posted). Every 30 new votes moves ~1 model past `perceived_n ≥ 20`. Aim: get to n=25+ shared models. Fastest legitimate path.
2. **Ship multi-vote per match** (Tier-B roadmap item, ~4-6 hours). Each shipped vote counts 3× toward perceived_n if 3 people vote on the same match. Also unlocks inter-rater κ, a separate publishable finding.
3. **Frozen pack v2 with 300-500 matches** — would NOT help this study (perceived_n unchanged) but would strengthen per-weapon stratification for future work.
4. **Bump Elo K-factor** from 32 to 64 for future votes — controversial, breaks Elo-across-versions comparability, don't do without prompt_version bump.

## Original 2026-08-04 findings (pre-frozen-pack, for context)

## Question

Does the human-perceived Elo (blind crowd-vote rating) rank models the same way as the objective win-rate leaderboard (mechanical damage / win / loss)?

If ρ is very high: leaderboards are redundant and one of them should be collapsed. If ρ is low: the gap between them *is* the benchmark's signal and both should be reported.

This is METHODOLOGY.md § 4's core empirical claim. Until this report, that section shipped without a number.

## Headline result

**The study is underpowered at the current traffic scale.** Once both perceived-Elo AND objective-win-rate are filtered to `n ≥ 5` matches per model (the minimum needed for either metric to have moved off its prior), **only 2 LLMs survive the joint filter** — insufficient for any meaningful correlation.

Do not publish or cite a Spearman ρ number from this snapshot. Any single-number ρ from the current dataset is a small-sample artifact, not a signal about the two leaderboards.

## Full result table

### Unfiltered (n = 18 shared models)

Median perceived_n = 3 matches/model · median objective_n = 2 matches/model.

| Population | n | ρ (perceived_elo vs objective_win_rate) | 95% bootstrap CI | p |
|---|---|---|---|---|
| All (LLMs + bots + mocks) | 18 | −0.323 | [−0.763, +0.263] | 0.191 |
| bots + mocks only | 4 | +1.000 | [+1.000, +1.000] | <0.001 |
| LLMs only | 14 | **−0.599** | **[−0.929, −0.034]** | **0.024** |

The **LLMs-only ρ = −0.599 (p = 0.024)** looks striking — humans appear to systematically vote *against* mechanically-winning models. But the CI floor at −0.929 and the tiny sample size are red flags. Filtering exposes the problem.

### Filtered — perceived_n ≥ 5 only (n = 7 models)

Applying the single-side filter that only requires converged perceived-Elo:

| Population | n | ρ (perceived_elo vs objective_win_rate) | 95% bootstrap CI | p |
|---|---|---|---|---|
| CONVERGED (all) | 7 | −0.764 | ~[−0.95, +0.1] | 0.046 |
| CONVERGED LLMs only | 6 | **−0.899** | ~[−0.99, +0.1] | 0.015 |

**Why this "−0.899" is a false headline:** perceived_n filters only fix the perceived-Elo side. The objective side still contains models with `matches ∈ {1, 2, 3}` where a single fluke win produces `win_rate = 1.0`. Specifically:

| Model | perceived_n | perceived_elo | objective_n | objective_win_rate |
|---|---|---|---|---|
| `meta-llama/llama-3.2-3b-instruct:free` | 19 | 972.2 (worst) | **1** | **1.000** ⚠️ |
| `nvidia/nemotron-3-super-120b-a12b:free` | 7 | 995.5 | 4 | 1.000 |
| `openai/gpt-oss-120b:free` | 26 | 1014.5 (best) | 2 | 0.250 |

The 3B llama has one objective match, which it happened to win — treating that as a 100% win rate against gpt-oss-120b's 2 matches at 25% produces a massive spurious negative correlation. This is not a real finding.

### Filtered — both sides `n ≥ 5` (n = 2 models)

This is the correct filter. **The joint filter leaves only 2 shared models. Correlation is not defined.**

## Interpretation for METHODOLOGY.md § 4

**What we can honestly say today:**

> As of 2026-08-04 (n = 467 matches, 106 votes), the cross-benchmark correlation between perceived-Elo and objective win-rate is not yet statistically resolvable at the model level. Only 2 models have accumulated both ≥ 5 rated matches AND ≥ 5 completed matches, which is the minimum for either metric to be independent of its prior. Reporting Spearman ρ on smaller samples produces a striking-looking negative correlation (ρ ≈ −0.6 to −0.9) that is entirely explained by objective-side small-sample noise, not by any real disagreement between the two leaderboards.

**What we cannot say today:**

- ~~"Perceived Elo and objective win-rate correlate at ρ ≈ 0.71"~~ **DELETE FROM ALL DRAFTS** — this number was fabricated in the r/ML post draft and does not appear anywhere in the actual data.
- ~~"Humans systematically vote against mechanical winners"~~ — the negative unfiltered correlation is a small-sample artifact.

**What to do next (in order):**

1. **This week:** Delete the fabricated `ρ ≈ 0.71` line from `marketing/reddit_posts_2026-07-30.md` §3 (r/ML draft).
2. **Update METHODOLOGY.md § 4** to include the honest paragraph above under a new "§ 4.1 Empirical status" subsection. Don't hide the underpower — publishing negative / null / underpowered findings *is* the anti-sycophancy protocol working.
3. **Run the Tier-A #4 frozen 100-matchup eval pack.** That's what unblocks this study. A 100-match pack across 10 shared models (10 matches each) would push both perceived_n and objective_n above the joint threshold for enough models to compute a real ρ.
4. **Re-run this notebook after the frozen eval pack lands.** Expected finish state: n ≥ 10 shared models each with ≥ 10 matches per axis. At that scale, a Spearman ρ of any magnitude with a p < 0.05 is publishable.

## Per-weapon slice — also underpowered

None of the per-weapon slices had enough shared models to compute stable correlations. This is the same underpowering, just visible sooner in the weapon-stratified data. Expected to unblock at the same milestone.

## Grade move under AGENTS.md § 0.5

**Do not move Research 8.2** based on this report.

The claim on the roadmap was that shipping this study would push Research 8.2 → 8.4. That was conditional on the study producing a defensible headline number. It didn't — because the data isn't there yet — so the grade doesn't move.

What the report *does* deliver:
- Kills the fabricated `ρ ≈ 0.71` claim across every draft.
- Establishes the exact statistical threshold (both sides `n ≥ 5`) that must be crossed before the study is meaningful.
- Ships a reproducible script that will automatically re-produce the right answer when the data catches up.
- Sets the expectation that publishing null/underpowered findings is the correct behavior under § 0.5, not a failure.

That's arguably a **Codebase +0.0 Security +0.0 Research +0.0** delivery, but a Research **rigor** win that doesn't show up in the number.

## Reproduction

```bash
cd research
python3 cross_benchmark_correlation.py
```

Uses the pinned 2026-08-04 snapshots by default. To re-run against live prod:

```bash
# Refresh snapshots from live prod
curl -s "https://pioneer37-stickman-arena.hf.space/api/export?fmt=json&limit=1000" \
     > research/export_snapshot_$(date +%Y-%m-%d).json
curl -s "https://pioneer37-stickman-arena.hf.space/api/leaderboard" \
     > research/lb_perceived_snapshot_$(date +%Y-%m-%d).json
curl -s "https://pioneer37-stickman-arena.hf.space/api/leaderboard/objective" \
     > research/lb_objective_snapshot_$(date +%Y-%m-%d).json
# Edit SNAP_DATE at the top of cross_benchmark_correlation.py, re-run.
```
