# DATA_LICENSE

**This file describes the license for Stickblade Arena's match data (not the source code).**

For the source code license, see [`LICENSE`](../LICENSE) at the repo root (Apache 2.0).

---

## Match data license: CC-BY-SA 4.0

All match data exposed via `/api/export`, checked-in snapshots in this `research/` folder, and any HuggingFace Datasets snapshot published under `Pioneer37/stickblade-*` is licensed under the **Creative Commons Attribution-ShareAlike 4.0 International License** (CC-BY-SA 4.0).

Human-readable summary: https://creativecommons.org/licenses/by-sa/4.0/
Full legal text: https://creativecommons.org/licenses/by-sa/4.0/legalcode

## What this means

**You can:**
- ✅ Download the full match log dump
- ✅ Use it for academic research
- ✅ Use it commercially (e.g. train a reward model on it)
- ✅ Republish it, in whole or in part
- ✅ Modify it, aggregate it, build derivative datasets

**You must:**
- 📝 **Attribute the source** — cite Stickblade Arena and link back to `https://github.com/Cometbuster4969/STICKBLADE-ARENA`. See [`CITATION.cff`](../CITATION.cff) for the canonical format.
- 🔗 **Share-alike** — if you publish a derivative dataset (e.g. Stickblade matches + your own filtering/scoring), your derivative must also be under CC-BY-SA 4.0 or a compatible license. You can't wrap it and close it.

**You cannot:**
- ❌ Republish under a more restrictive license (this defeats the point)
- ❌ Strip attribution and claim the data is yours
- ❌ Add DRM or technical restrictions that prevent others from exercising their CC-BY-SA rights

## Why CC-BY-SA and not fully public domain

Two reasons:

1. **Attribution requirement matters for a benchmark.** Uncited use of a benchmark's data is what makes benchmarks decay — you lose track of who's evaluated what, comparisons across papers become impossible. Attribution keeps the citation graph intact.

2. **Share-alike prevents a specific failure mode:** a well-funded org copying the dataset, adding some scoring layer, and republishing under a proprietary license. CC-BY-SA 4.0 makes derivatives also open. This is the same rationale HuggingFace uses for many of their datasets.

## Why CC-BY-SA is compatible with Apache 2.0 (code)

The **code** is Apache 2.0. The **data** is CC-BY-SA 4.0. These are two different types of asset with two different licenses — the standard practice for open-source projects that produce data output. No conflict:

- Apache 2.0 governs the software (runtime, tooling, physics engine integration)
- CC-BY-SA 4.0 governs the outputs (match logs, replay JSONs, aggregate stats)

If you want to build a service on top of Stickblade's code (permissive), you can (Apache 2.0). If you want to publish a dataset derived from Stickblade's matches, you can, but your dataset stays open (CC-BY-SA 4.0).

## What data specifically is covered

All of the following are CC-BY-SA 4.0:

- **Per-match metadata** returned by `/api/export` — model IDs, weapon/mode/arena, winner, method, turn count, damage/hit stats
- **Replay JSON files** — the frame-by-frame physics + events + LLM thoughts per match, accessible via `/api/replay/{match_id}`
- **Anonymous vote records** — vote choice + match ID + timestamp (no user identity, no IPs)
- **Aggregate leaderboard rows** — Elo, wins/losses/draws, Wilson CIs
- **Snapshot dumps** in this `research/` folder — `export_snapshot_*.json`, `lb_perceived_snapshot_*.json`, `lb_objective_snapshot_*.json`, `frozen_pack_v1_results.csv`
- **Any HuggingFace Dataset** published as `Pioneer37/stickblade-*` (once the daily snapshot cron ships)

## What is NOT match data

The following are **NOT** covered by CC-BY-SA 4.0 (they're code):
- The `stickblade/` Python backend
- The `stickblade-web/` Next.js frontend
- The `tools/` runner scripts
- Any file under Apache 2.0 per `LICENSE`

## What is deliberately excluded from public data

To be clear about what we don't expose (for privacy/security reasons, not IP reasons):

- **BYOK API keys** — never logged, never stored, never in exports (see `_KEY_LEAK_RE` scrubber in `stickblade/security.py`)
- **IP addresses** — not stored beyond rate-limiting purposes; not in exports
- **User identity** — there is none to expose (no accounts, no login)
- **Prompt exact texts on future PROMPT_VERSION bumps** — v1 prompt is documented in `stickblade/brains.py`; if v2 changes something for a specific business reason, the delta may be documented in `AGENTS.md §PROMPT_VERSION_LOG` rather than the export

## Rationale for open data (2026-08-13 decision log)

The project owner briefly considered closing the data. The decision to keep it open + declare CC-BY-SA 4.0 is recorded in `TIMELINE.md` under "Data licensing decision (Aug 13, 2026)" with the following reasoning:

1. Every marketing pitch (HN / Reddit / grants / arXiv) hinges on "open + reproducible." Closing data kills those pathways.
2. Current scale (~500 matches, ~$0 revenue) means there is no realistic buyer of closed data — closure loses academic + grant + community reach in exchange for zero cash.
3. The benchmark's moat is methodology + brand + ongoing pipeline, not a historical CSV. Closing yesterday's matches doesn't protect tomorrow's matches.
4. CC-BY-SA 4.0 preserves the attribution + share-alike bargaining chip if someone tries to wrap-and-sell. This is the same license posture that made LMSYS/EleutherAI/HuggingFace fundable.

If circumstances change (paying customers exist, specific enterprise deal requires closure, PII-adjacent risk emerges), this decision can be revisited. Until then: open is the default.

## Citation format

For academic use, prefer citing the [`CITATION.cff`](../CITATION.cff) at repo root. GitHub renders a "Cite this repository" widget from that file. Or use plain text:

```
Kumar, A. (2026). Stickblade Arena: A Physics-Grounded LLM Evaluation
Benchmark. https://github.com/Cometbuster4969/STICKBLADE-ARENA
Data license: CC-BY-SA 4.0.
```

For dataset-specific citation (once HF Datasets snapshot is live):

```
Kumar, A. (2026). Stickblade Arena Match Dataset. HuggingFace Datasets:
Pioneer37/stickblade-matches. https://huggingface.co/datasets/Pioneer37/stickblade-matches
Licensed under CC-BY-SA 4.0.
```
