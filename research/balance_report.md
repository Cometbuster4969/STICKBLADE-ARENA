# Weapon / arena / sharp-zone balance report

Generated: 2026-09-08
Protocol: 8 mirrored bot matches per (weapon, arena) combination, sharp zones rotated per weapon, seeds 5000+, match length `standard`.

Mirrored means the same two scripted bots swap canvas sides on alternating matches — so any deviation from a 50/50 win rate is attributable to the configuration, not to fighter skill.

## How to read this

Side-A win rate is measured on a **mirrored** batch: the same two scripted bots swap canvas sides every other match, so a perfectly neutral configuration trends to 0.5. A deviation is only evidence of imbalance when the 95% Wilson interval excludes 0.5 — otherwise it is noise at this sample size, and the report says so rather than claiming a finding.

## Balance flags

- • bow: point estimate 0.3125 is off 50/50 but the 95% CI [0.1643, 0.5125] still contains it — widen the batch (n=24) before treating this as imbalance
- ⚠ flail: side bias 0.1875 (95% CI [0.0794, 0.3819]) excludes 50/50 on a mirrored bot batch — the configuration, not the model, is deciding matches

### By weapon

| weapon | matches | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|
| bow | 24 | 0.3125 [0.1643, 0.5125] | 45.31 | 4.62 | 9.0 | 0.375 |
| dagger | 24 | 0.4792 [0.2965, 0.6676] | 37.88 | 9.42 | 11.8 | 0.083 |
| flail | 24 | 0.1875 [0.0794, 0.3819] | 73.41 | 13.21 | 9.4 | 0.667 |
| spear | 24 | 0.4375 [0.2617, 0.6306] | 25.71 | 4.79 | 11.8 | 0.042 |
| sword | 24 | 0.5833 [0.3883, 0.7553] | 39.83 | 8.33 | 11.2 | 0.125 |

### By arena

| arena | matches | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|
| ice | 40 | 0.4375 [0.296, 0.5899] | 43.81 | 8.51 | 11 | 0.25 |
| low_gravity | 40 | 0.375 [0.2422, 0.5297] | 42.15 | 6.76 | 10.2 | 0.25 |
| normal | 40 | 0.3875 [0.2528, 0.5419] | 47.32 | 8.95 | 10.8 | 0.275 |

### By sharp zone

| sharp | matches | side-A win rate (95% CI) | avg damage | avg hits | avg turns | lethal rate |
|---|---:|---:|---:|---:|---:|---:|
| arrow_shaft | 9 | 0.4444 [0.1888, 0.7334] | 43.01 | 8.44 | 12 | 0.0 |
| arrowhead | 9 | 0.1111 [0.0199, 0.435] | 68.42 | 2.22 | 4.1 | 1.0 |
| back_edge | 12 | 0.5 [0.2538, 0.7462] | 23.82 | 9 | 12 | 0.0 |
| ball | 6 | 0.0 [0.0, 0.3903] | 47.32 | 15.67 | 12 | 0.0 |
| bow_limb | 6 | 0.4167 [0.1395, 0.7589] | 14.09 | 2.5 | 12 | 0.0 |
| butt | 6 | 0.3333 [0.0968, 0.7] | 11.95 | 4.33 | 12 | 0.0 |
| chain | 6 | 0.3333 [0.0968, 0.7] | 88.55 | 14.83 | 9 | 1.0 |
| edge | 12 | 0.625 [0.3544, 0.835] | 41.71 | 10.33 | 11.6 | 0.083 |
| handle | 6 | 0.0 [0.0, 0.3903] | 81.48 | 9.5 | 6.7 | 1.0 |
| pommel | 12 | 0.5 [0.2538, 0.7462] | 51.27 | 10.75 | 12 | 0.0 |
| shaft | 9 | 0.5556 [0.2666, 0.8112] | 32.91 | 4.67 | 12 | 0.0 |
| spikes | 6 | 0.4167 [0.1395, 0.7589] | 76.28 | 12.83 | 9.8 | 0.667 |
| tip | 21 | 0.4524 [0.2639, 0.6556] | 33.94 | 5.33 | 10.9 | 0.238 |
