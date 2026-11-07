# Weapon / arena / sharp-zone balance report

Generated: 2026-11-07
Protocol: 8 mirrored bot matches per (weapon, arena) combination, sharp zones rotated per weapon, seeds 5000+, match length `standard`.

Mirrored means the same two scripted bots swap canvas sides on alternating matches — so any deviation from a 50/50 win rate is attributable to the configuration, not to fighter skill.

## How to read this

Side-A win rate is measured on a **mirrored** batch: the same two scripted bots swap canvas sides every other match, so a perfectly neutral configuration trends to 0.5. A deviation is only evidence of imbalance when the 95% Wilson interval excludes 0.5 — otherwise it is noise at this sample size, and the report says so rather than claiming a finding.

**Distinct fights, not rows, are the sample.** Scripted bots are deterministic: the same weapon/arena/zone/flip under a new seed replays the *same* fight, bit for bit. The `rows` column is how many matches were run; `distinct fights` is how many independent observations that produced. Every interval in this report is computed on distinct fights only, because counting a deterministic repeat as a new trial is pseudo-replication and narrows the CI by roughly sqrt(k).

## Balance flags

- bow: 24 rows but only 23 distinct fights — scripted bots are deterministic, so repeated seeds replayed the same fight. The CI uses 23; vary the CONFIG (arena / zone / matchup), not the seed, to add samples.
- ⚠ bow: side bias 0.2174 (95% CI [0.0966, 0.419]) excludes 50/50 on a mirrored bot batch — the configuration, not the model, is deciding matches
- dagger: 24 rows but only 15 distinct fights — scripted bots are deterministic, so repeated seeds replayed the same fight. The CI uses 15; vary the CONFIG (arena / zone / matchup), not the seed, to add samples.
- flail: 24 rows but only 15 distinct fights — scripted bots are deterministic, so repeated seeds replayed the same fight. The CI uses 15; vary the CONFIG (arena / zone / matchup), not the seed, to add samples.
- ⚠ flail: side bias 0.2333 (95% CI [0.0891, 0.4863]) excludes 50/50 on a mirrored bot batch — the configuration, not the model, is deciding matches
- spear: 24 rows but only 18 distinct fights — scripted bots are deterministic, so repeated seeds replayed the same fight. The CI uses 18; vary the CONFIG (arena / zone / matchup), not the seed, to add samples.
- spear: point estimate 0.3889 is off 50/50 but the 95% CI [0.203, 0.6138] still contains it — widen the batch (n=18 distinct fights) before treating this as imbalance
- sword: 24 rows but only 15 distinct fights — scripted bots are deterministic, so repeated seeds replayed the same fight. The CI uses 15; vary the CONFIG (arena / zone / matchup), not the seed, to add samples.

### By weapon

| weapon | rows | distinct fights | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| bow | 24 | 23 | 0.2174 [0.0966, 0.419] | 49.57 | 5.19 | 9.5 | 0.375 |
| dagger | 24 | 15 | 0.5 [0.2742, 0.7258] | 37.88 | 9.42 | 11.8 | 0.083 |
| flail | 24 | 15 | 0.2333 [0.0891, 0.4863] | 73.41 | 13.21 | 9.4 | 0.667 |
| spear | 24 | 18 | 0.3889 [0.203, 0.6138] | 25.71 | 4.79 | 11.8 | 0.042 |
| sword | 24 | 15 | 0.6 [0.3575, 0.8018] | 39.83 | 8.33 | 11.2 | 0.125 |

### By arena

| arena | rows | distinct fights | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| ice | 40 | 29 | 0.4138 [0.2551, 0.5926] | 44.46 | 8.55 | 11.1 | 0.25 |
| low_gravity | 40 | 28 | 0.3036 [0.1658, 0.4887] | 42.34 | 6.91 | 10.3 | 0.25 |
| normal | 40 | 29 | 0.3966 [0.2409, 0.5764] | 49.03 | 9.1 | 10.8 | 0.275 |

### By sharp zone

| sharp | rows | distinct fights | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| arrow_shaft | 9 | 9 | 0.3333 [0.1206, 0.6458] | 41.98 | 7.83 | 12 | 0.0 |
| arrowhead | 9 | 8 | 0.0 [0.0, 0.3244] | 69.64 | 2.61 | 5.2 | 1.0 |
| back_edge | 12 | 6 | 0.5 [0.1876, 0.8124] | 23.82 | 9 | 12 | 0.0 |
| ball | 6 | 3 | 0.0 [0.0, 0.5615] | 47.32 | 15.67 | 12 | 0.0 |
| bow_limb | 6 | 6 | 0.3333 [0.0968, 0.7] | 30.83 | 5.08 | 12 | 0.0 |
| butt | 6 | 6 | 0.3333 [0.0968, 0.7] | 11.95 | 4.33 | 12 | 0.0 |
| chain | 6 | 3 | 0.3333 [0.0615, 0.7923] | 88.55 | 14.83 | 9 | 1.0 |
| edge | 12 | 12 | 0.625 [0.3544, 0.835] | 41.71 | 10.33 | 11.6 | 0.083 |
| handle | 6 | 3 | 0.0 [0.0, 0.5615] | 81.48 | 9.5 | 6.7 | 1.0 |
| pommel | 12 | 6 | 0.5 [0.1876, 0.8124] | 51.27 | 10.75 | 12 | 0.0 |
| shaft | 9 | 6 | 0.5 [0.1876, 0.8124] | 32.91 | 4.67 | 12 | 0.0 |
| spikes | 6 | 6 | 0.4167 [0.1395, 0.7589] | 76.28 | 12.83 | 9.8 | 0.667 |
| tip | 21 | 12 | 0.4167 [0.1933, 0.6805] | 33.94 | 5.33 | 10.9 | 0.238 |
