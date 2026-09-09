#!/usr/bin/env python3
"""
Audit tool for the frozen eval pack.

Verifies:
  1. Exactly 100 matches
  2. Distribution: 20 per weapon x 5 weapons
  3. No self-play (model_a != model_b)
  4. Per-model matchup counts (should be balanced, min >= 4)
  5. Every model appears >= 4 times (well above n>=5 joint-filter threshold
     if paired with the existing organic 471 matches)
  6. All seeds are unique
  7. All model IDs reference the current live roster

Run:
    python3 tools/audit_frozen_pack.py
"""
from __future__ import annotations
import collections
import json
import pathlib
import sys
import urllib.request

# Windows-safe stdout: force UTF-8 for ρ, τ, —, ≥, ✅ etc. See
# research/cross_benchmark_correlation.py for the rationale.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = pathlib.Path(__file__).parent.parent
PACK_PATH = HERE / "research" / "frozen_pack_v1.yaml"


def load_pack():
    """Parse the YAML manually (avoids pyyaml dep). This is a strict flow-
    style file: each match is on one line, keys are simple identifiers.
    """
    matches = []
    header = {}
    in_matches = False
    # encoding="utf-8" required — the YAML contains em-dashes and other
    # non-ASCII characters that Windows cp1252 default can't decode.
    for raw in PACK_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("matches:"):
            in_matches = True
            continue
        if in_matches and line.startswith("- {"):
            # Parse the flow-style dict
            inner = line[3:-1]  # strip "- {" and "}"
            d = {}
            for part in _split_flow(inner):
                k, _, v = part.partition(":")
                d[k.strip()] = v.strip()
            matches.append(d)
        elif not in_matches and ":" in line:
            k, _, v = line.partition(":")
            v = v.split("#", 1)[0]  # strip inline comments
            header[k.strip()] = v.strip().strip('"')
    return header, matches


def _split_flow(s):
    """Split a comma-separated flow-dict body, respecting nested commas
    inside strings (none present here, so simple split is fine)."""
    return [p for p in s.split(",")]


def audit(header, matches, roster):
    errs = []
    warns = []

    # 1. exactly 100 matches
    if len(matches) != 100:
        errs.append(f"expected 100 matches, got {len(matches)}")

    # 2. weapon distribution
    by_weapon = collections.Counter(m["weapon"] for m in matches)
    for w, expected in [("sword", 20), ("dagger", 20), ("spear", 20),
                        ("flail", 20), ("bow", 20)]:
        if by_weapon[w] != expected:
            errs.append(f"weapon={w}: expected {expected} matches, got {by_weapon[w]}")

    # 3. no self-play
    for m in matches:
        if m["model_a"] == m["model_b"]:
            errs.append(f"self-play in match i={m['i']}: {m['model_a']}")

    # 4. per-model matchup counts
    per_model = collections.Counter()
    for m in matches:
        per_model[m["model_a"]] += 1
        per_model[m["model_b"]] += 1

    # 5. every model appears >= 4 times
    for model, count in per_model.items():
        if count < 4:
            warns.append(f"model {model} appears only {count} times "
                         f"(min recommended: 4)")

    # 6. unique seeds
    seeds = [int(m["seed"]) for m in matches]
    if len(seeds) != len(set(seeds)):
        dupes = [s for s in seeds if seeds.count(s) > 1]
        errs.append(f"duplicate seeds: {sorted(set(dupes))}")

    # 7. all models in current live roster
    roster_ids = {m["id"] for m in roster}
    referenced = set(per_model.keys())
    unknown = referenced - roster_ids
    if unknown:
        warns.append(f"models NOT in current live roster: {sorted(unknown)}")

    # print report
    print("=" * 72)
    print(f"FROZEN PACK v{header.get('pack_version', '?')} AUDIT")
    print("=" * 72)
    print(f"Header: {header.get('created')} · author {header.get('author')}")
    print(f"Backend: {header.get('backend_base_url')}")
    print(f"Total matches: {len(matches)}")
    print()
    print("Per-weapon distribution:")
    for w, n in by_weapon.most_common():
        print(f"  {w:8s}: {n}")
    print()
    print(f"Per-model matchup counts ({len(per_model)} distinct models):")
    for model, count in per_model.most_common():
        flag = "  " if count >= 4 else "⚠ "
        print(f"  {flag}{model:60s} {count}")
    total_slots = sum(per_model.values())
    print(f"Total slots (matches x 2): {total_slots}")
    print()

    if errs:
        print("❌ ERRORS:")
        for e in errs:
            print(f"  - {e}")
    if warns:
        print("⚠  WARNINGS:")
        for w in warns:
            print(f"  - {w}")
    if not errs and not warns:
        print("✅ Pack passes all audits.")
    return len(errs) == 0


def load_live_roster():
    try:
        url = "https://pioneer37-stickman-arena.hf.space/api/models"
        req = urllib.request.Request(url, headers={"User-Agent": "audit/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        print(f"WARN: could not fetch live roster ({e}); roster audit skipped")
        return []


def main():
    if not PACK_PATH.exists():
        print(f"ERROR: pack file not found: {PACK_PATH}")
        sys.exit(1)
    header, matches = load_pack()
    roster = load_live_roster()
    ok = audit(header, matches, roster)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
