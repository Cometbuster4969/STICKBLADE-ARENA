#!/usr/bin/env python3
"""Shared bootstrap + headless match runner for the Stickblade CLI tools.

The engine lives in `stickblade/` as flat modules that import each other by
bare name (`import config as C`), so anything outside that directory has to
put it on sys.path first. This module does that once, plus pygame dummy-video
setup, and exposes a single `run_headless_match()` used by every tool
(batch runner, weapon balance sweep, demo generator).

No network, no database, no API keys required — which is the whole point of
action-plan §25: "a researcher should be able to clone the core repository
and run a local match without needing Vercel, Hugging Face, OpenRouter, or
a database."
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
ENGINE_DIR = REPO_ROOT / "stickblade"

# Windows-safe stdout (the frozen-pack runner does the same): force UTF-8 so
# we can print ✓ / ρ / ≥ without a cp1252 crash.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def bootstrap(quiet: bool = False):
    """Put the engine on sys.path and initialise headless pygame."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    if not quiet:
        import pygame
        if not pygame.get_init():
            pygame.init()
        try:
            pygame.display.set_mode((10, 10))
        except Exception:
            pass
    return ENGINE_DIR


def run_headless_match(model_a: str, model_b: str, sharp=None, weapon="sword",
                       arena="normal", mode="macro", blindfolded=False,
                       seed=None, match_length="full", max_turns=None,
                       fallback_policy="operational",
                       max_frames=60 * 60 * 8, log_path=os.devnull,
                       every=2):
    """Run one complete match offline. Returns (match, replay_dict).

    Deterministic when `seed` is given: same seed + same models + same
    config => identical replay frames (verified in tests).
    """
    bootstrap()
    import config as C                                   # noqa: F401
    from main import Match
    from recorder import ReplayRecorder, RecordingFX

    sharp = list(sharp or ["tip"])
    # `every` = record 1 frame in N. The default (2) is the fidelity the
    # physics audit expects; the landing-page demo uses 4 to keep the
    # committed asset under ~500 KiB without changing the fight.
    rec = ReplayRecorder(every=every)
    fx = RecordingFX(rec)
    # log_path defaults to /dev/null: a batch of 30 matches must not litter
    # the working tree with 30 battle_log_*.json files.
    match = Match(model_a, model_b, sharp, fx, log_path=log_path, mode=mode,
                  weapon=weapon, arena=arena, blindfolded=blindfolded,
                  seed=seed, match_length=match_length, max_turns=max_turns,
                  fallback_policy=fallback_policy)
    rec.attach(match)
    frames = 0
    while match.phase != Match.PH_OVER and frames < max_frames:
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
        frames += 1
    if match.result is None:
        match._finish()
    # Record the terminal frames (killcam / "OVER" flag). The loop above
    # exits the instant the match ends, so without this the replay's last
    # frame never carries over=1 and benchmark.verify_replay() reports
    # "result_consistent: false" — a false alarm on a perfectly good replay.
    for _ in range(90):
        match.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    return match, rec.build()


def summarize(match, replay) -> dict:
    """Flat one-row summary of a finished match (CSV/JSON friendly)."""
    prov = replay.get("meta", {}).get("provenance", {}) or {}
    res = match.result or {}
    tel = replay.get("meta", {}).get("telemetry", {}) or {}
    metrics = replay.get("meta", {}).get("metrics", {}) or {}
    winner = res.get("winner")
    if winner == match.f1.name:
        winner_side, winner_model = "a", prov.get("model_requested_a")
    elif winner == match.f2.name:
        winner_side, winner_model = "b", prov.get("model_requested_b")
    else:
        winner_side, winner_model = "draw", None
    return {
        "model_a": prov.get("model_requested_a"),
        "model_b": prov.get("model_requested_b"),
        "winner_side": winner_side,
        "winner_model": winner_model,
        "method": res.get("method"),
        "turns": res.get("turns"),
        "hp_a": (res.get("final_hp") or {}).get(match.f1.name),
        "hp_b": (res.get("final_hp") or {}).get(match.f2.name),
        "damage_a": metrics.get("damage_dealt_a"),
        "damage_b": metrics.get("damage_dealt_b"),
        "hits_a": metrics.get("hits_landed_a"),
        "hits_b": metrics.get("hits_landed_b"),
        "fallback_a": metrics.get("fallback_turns_a"),
        "fallback_b": metrics.get("fallback_turns_b"),
        "latency_ms_a": prov.get("latency_ms_a"),
        "latency_ms_b": prov.get("latency_ms_b"),
        "invalid_a": prov.get("invalid_actions_a"),
        "invalid_b": prov.get("invalid_actions_b"),
        "seed": prov.get("seed"),
        "weapon": weapon_of(prov, match),
        "sharp": prov.get("sharp"),
        "arena": prov.get("arena"),
        "mode": prov.get("mode"),
        "match_length": prov.get("match_length"),
        "fallback_policy": prov.get("fallback_policy"),
        "ranking_eligible": prov.get("ranking_eligible"),
        "spec_fingerprint": prov.get("spec_fingerprint"),
        "latency_a_telemetry": (tel.get("a") or {}).get("latency_ms_avg"),
        "latency_b_telemetry": (tel.get("b") or {}).get("latency_ms_avg"),
    }


def weapon_of(prov, match):
    return prov.get("weapon") or getattr(match, "weapon", "sword")


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def write_csv(path, rows, fields=None):
    """Write rows (list of dicts) as CSV with a stable union-of-keys header.

    `fields` pins the column order (and writes a header even for an empty
    batch) so a schema-bearing CSV never depends on which row came first.
    """
    import csv
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fields:
        path.write_text("")
        return path
    cols = list(fields) if fields else []
    seen = set(cols)
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path
