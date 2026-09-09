# Stickblade Arena — Benchmark Specification v1.0

> This is the prose version of the frozen spec. The machine-readable
> authority is [`stickblade/benchmark.py`](../stickblade/benchmark.py), which
> derives most values *from the live code* so the spec cannot silently drift
> from the implementation. `GET /api/benchmark/spec` serves the same document
> as JSON.

| | |
|---|---|
| **Benchmark version** | `1.0` |
| **Physics version** | `1.0` |
| **Prompt version** | `2` (v1 → v2 on 2026-09-08, additive/soft cutover — AGENTS.md §10.5) |
| **Spec fingerprint** | `09de66effd02` — rows with `prompt_version = 1` carry `029281ed627a`; the fingerprint hashes the prompt version, so the two are the same physics + rules under two prompts |
| **Data licence** | CC-BY-SA-4.0 |
| **Code licence** | Apache-2.0 |

---

## 0. What is being measured

**Claim:** model *A* fights more intelligently than model *B* in a
constrained, real-time, physically-grounded adversarial setting, as judged by
a human who cannot tell which is which.

Three properties make that claim checkable:

1. **Blindness.** The voter never sees model names before voting.
2. **Determinism of everything except the model.** Physics, damage, and
   scripted baselines are reproducible bit-for-bit from a seed; LLM outputs
   are not, so every decision is recorded in an action log and the fight can
   be re-simulated exactly.
3. **Provenance.** Every match row carries the version triple, the seed, and
   the fallback/invalid-action counters needed to decide whether it should
   count at all.

---

## 1. The task

Each turn, both fighters simultaneously receive a numeric state description
and return a JSON decision. Their decisions are animated through the physics
engine for 3 simulated seconds, then the next turn begins.

```
BANNER (1.2 s) → THINK (both brains decide) → SIM (3.0 s of physics) → repeat
                                                                    → OVER
```

- **Control modes.** `macro` — the model picks a named move plus footwork.
  `joint` — the model sets a target state per joint (Toribash-style).
- **Action vocabulary** is per-weapon; see §4.
- **Response format:** `{"action": …, "footwork": …, "thought": …}`.
- **Prompt-injection policy:** an opponent's `thought` text is never shown to
  a fighter. Only engine-generated numeric state is transmitted; custom
  free-text fields are filtered before sending.

### State given to a fighter

Absolute torso/head/weapon-tip coordinates, velocities, facing, HP,
last-turn hits, relative geometry, and ranged hints. The **blindfolded**
variant strips the derived categorical hints (an ablation axis, not a
difficulty setting).

---

## 2. Physics

| Parameter | Value |
|---|---|
| Engine | pymunk (Chipmunk 2D) |
| Arena | 1280 × 720, floor at y=64, spawns at x=430 / x=850 |
| Timestep | 1/120 s, 2 substeps per rendered frame, 60 fps render |
| Gravity | (0, −1150) |
| Damping | 0.99 normal · 0.996 ice |
| Arena modifiers | `normal`, `ice` (friction × 0.1), `low_gravity` (gravity × 0.35) |
| Turn length | 3.0 s of simulated time |

### Damage

| Rule | Value |
|---|---|
| Start HP | 100 |
| Sharp hit | `min(38, (rel_speed − 150) × 0.055 + 4) × part_multiplier` |
| Part multipliers | head 1.9 · torso 1.25 · leg 0.8 · arm 0.7 |
| Blunt hit | `min(6, (rel_speed − 260) × 0.012 + 1.0)` |
| Instant kill | head contact above 660 units/s |
| Cooldowns | 0.35 s between hits on the same pair, 0.55 s between swings |

`rel_speed` is the magnitude of the difference between the striking body's
velocity and the victim part's velocity, both evaluated at the contact point.

---

## 3. Match lengths and termination

| Length | Turns |
|---|---|
| `sprint` | 4 |
| `standard` | 12 |
| `full` (research default, and the historical default) | 24 |

A match ends on a kill, on mutual destruction (draw), at the turn cap
(decided on remaining HP), or at a wall-clock ceiling (180 s melee, 300 s
bow — decided on points and flagged). An HP gap under 0.5 at the cap is a
draw.

---

## 4. Weapons, zones, sharp zones

| Weapon | Sharp zones | Actions |
|---|---|---|
| sword | tip, edge, back_edge, pommel | thrust, overhead_slash, horizontal_slash, rising_slash, pommel_strike, guard_high, guard_low, ready |
| dagger | tip, edge, back_edge, pommel | same vocabulary; shorter, faster blade |
| spear | tip, shaft, butt | same vocabulary; long shaft favours thrusts |
| flail | ball, spikes, chain, handle | spin_up, overhead_smash, wide_swing, yank_back, handle_jab, guards |
| bow | arrowhead, arrow_shaft, bow_limb | draw_shot, quick_shot, high_arc_shot, bow_bash, guards |

The **sharp zone** the user selects is the part of the weapon the fighter is
told to optimise for. It is one of the six rating axes — a model that fences
well with the tip is not necessarily a model that brawls well with the
pommel, and the leaderboard keeps those rows apart.

---

## 5. Invalid actions, timeouts, fallbacks

- An action outside the weapon's vocabulary is coerced to `ready` and
  **counted as an invalid action**; unknown footwork becomes `hold`. Neither
  ends the match. The invalid-action rate is published per fighter.
- Every decision runs a retry ladder: original model → original model with
  +50 % timeout → buddy model #1 → buddy model #2 → scripted mock.
- Any rung below the first is a **fallback turn** and is recorded.

### Fallback policies

| Policy | Meaning |
|---|---|
| `strict` | any fallback turn makes the match **ranking-ineligible** (controlled research runs) |
| `operational` *(default)* | fallback continues, is recorded, match stays eligible |
| `demo` | scripted/demo match, **never ranked** |

---

## 6. Voting

One vote per match. The voter sees the fight with identities hidden — hatch
patterns and "Fighter A / Fighter B" — and the green/blue ↔ model mapping is
randomised per match (a stored `flip` bit) so colour cannot leak identity
either.

| Axis | Ranked? | Question |
|---|---|---|
| **tactical** | ✅ yes | who made the better tactical decisions |
| execution | no | who executed their intent more cleanly |
| entertainment | no | who was more fun to watch |
| deserved | no | who the physics says deserved it |
| confidence (1–5) | no | self-reported |

Only the **tactical** axis moves Elo. The others are research signal for
measuring the gap between "fought well" and "was entertaining".

---

## 7. Rating

- **Elo**, K = 32, start 1000, draw = 0.5.
- Cell key: `model × sharp × weapon × mode × arena × blindfolded`. A rating
  only ever moves inside one cell, so "best sword fencer on tip" and "best
  brawler with the pommel" are different questions with different answers.
- **Uncertainty:** Wilson score 95 % interval on win rate (draws count 0.5).
- **Provisional:** fewer than 10 matches in a cell. **Unranked:** fewer than 5.
- **Excluded from ranking:** strict-policy fallback matches, `demo` matches,
  self-play mirrors (recorded as draws, 0 delta), and errored/timeout matches.
- **Objective axis** (independent of human votes): damage per turn, hit rate,
  fallback rate, average distance.

### Evaluation axes

`sharp` · `weapon` · `mode` · `arena` · `blindfolded` — five configuration
axes plus the model identity itself. Coverage is published on
[`/dashboard`](https://stickblade-arena.vercel.app/dashboard) so a reader can
see how thin any given cell is before believing it.

---

## 8. Reproducibility and integrity

Every match stores a **provenance record**:

```
benchmark_version · physics_version · prompt_version · spec_fingerprint
seed · match_length · max_turns · fallback_policy
model_requested_a/b · model_used_a/b · provider_used_a/b
fallback_used · latency_ms_a/b (mean + max) · invalid_actions_a/b
ranking_eligible · cancelled
```

Every replay stores, in addition, the **action log** — the exact decision each
fighter made on each turn. `benchmark.verify_replay()` audits a replay for:

| Check | What it catches |
|---|---|
| `provenance_present` | a replay with no version stamp |
| `version_pinned` | a replay recorded under a different spec |
| `seed_present` | an unreproducible run presented as reproducible |
| `action_log_complete` | a truncated or edited log |
| `frames_present` / `hp_monotonic` | doctored frames |
| `result_consistent` | a claimed winner that the log does not produce |

`stickblade/anti_gaming.py` additionally scans finished replays for
degenerate and exploitative play: repeated identical actions, excessive
guarding, permanent retreat, never attacking, edge camping, prompt-injection
markers, truncated thoughts, and high fallback rates. Thresholds are
published in the module and surfaced through `GET /api/integrity/{match_id}`.

---

## 9. Seeding and determinism

When a seed is supplied, Python's global RNG **and every scripted brain's own
RNG** are seeded from it, so physics replays bit-for-bit. Two guards make that
hold in practice:

- Scripted brains draw from a **per-instance** RNG. The two fighters decide
  concurrently, and a shared global RNG would make which fighter consumed
  which draw depend on thread scheduling.
- When **both** fighters are scripted, decisions are resolved inline rather
  than in threads. The think phase steps the world forward once per frame
  while it waits, so a scheduling delay would otherwise change how far apart
  the fighters are when the turn starts.

LLM decisions are **not** reproducible from a seed. Reproducibility is
achieved by replaying the recorded action log, not by re-calling models.

---

## 10. What this benchmark does *not* claim

- It does not measure general intelligence. It measures tactical decision
  making in one narrow, physics-bound, turn-based combat domain.
- Ratings are **not comparable across prompt versions, physics versions, or
  benchmark versions.** Consumers must segment by the version triple.
- Sample sizes are small. Rows carry confidence intervals and a provisional
  flag for exactly this reason.
- Configuration is not neutral in every cell: on a mirrored bot batch the
  **flail** is measurably asymmetric (see
  [research/balance_report.md](../research/balance_report.md)) and is labelled
  as such in `/api/weapons`.

---

## Regenerating this document

```bash
cd stickblade && python3 benchmark.py                 # full JSON spec
cd stickblade && python3 benchmark.py --fingerprint   # just the fingerprint
./tools/run_match.py spec --json                      # same, via the CLI entry point
```

The fingerprint is a SHA-256 (first 12 hex chars) over the spec document. If
it changes, every previously published replay is now on a different
specification and its numbers must not be pooled with new ones.
