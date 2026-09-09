# Calibration batch — acceptance audit

**Run:** `cal-dryrun-2026-09-09`  
**Models:** `bot:pro` , `mock:duelist` , `bot:greedy` , `bot:distance`   
**Design:** 6 pairs × 16 · cells: sword/normal/macro, sword/normal/joint, sword/ice/macro, sword/ice/joint, bow/normal/macro, bow/normal/joint, bow/ice/macro, bow/ice/joint · sprint · strict · seeds from 20260909

**Generated:** 2026-09-09T10:50:07Z  
**Matches:** 96 (96 completed, 0 failed)  
**Evidence:** 0 real-provider · 0 mixed · 96 scripted  
**Token coverage:** n/a (no real-provider sides)  
**Decision latency:** p50 0.2 ms · p95 0.3 ms · max 1.4 ms

## Acceptance criteria

| criterion | result | detail |
|---|:---:|---|
| all matches identify provider and model | ✅ | 96/96 |
| all matches record eligibility status | ✅ | 96/96 |
| no silent fallback in strict mode | ✅ | 0 ranked strict matches fell back |
| token coverage at least 95pct or reported | ✅ | no real-provider sides |
| failed matches retained not ranked | ✅ | 0 failed, all flagged |
| real provider evidence present | ❌ | 0 real / 0 mixed / 96 scripted |

**Overall: NOT ACCEPTED**

## Per pair

| pair | n | eligible | A wins | B wins | draws | A on left |
|---|---:|---:|---:|---:|---:|---:|
| `bot:pro|mock:duelist` | 16 | 16 | 9 | 7 | 0 | 8/16 |
| `bot:pro|bot:greedy` | 16 | 16 | 9 | 7 | 0 | 8/16 |
| `bot:pro|bot:distance` | 16 | 16 | 8 | 2 | 6 | 8/16 |
| `mock:duelist|bot:greedy` | 16 | 16 | 10 | 6 | 0 | 8/16 |
| `mock:duelist|bot:distance` | 16 | 16 | 13 | 2 | 1 | 8/16 |
| `bot:greedy|bot:distance` | 16 | 16 | 12 | 4 | 0 | 8/16 |

A passing audit validates the MEASUREMENT PIPELINE. It says nothing about which model is better — that needs the Bradley–Terry separability test on voted data.
