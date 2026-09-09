"""Adversarial / anti-gaming detectors (action-plan §7).

A model can win a Stickblade match without demonstrating useful tactical
reasoning — by stalling out the clock, spamming one action, camping a
boundary the physics can't punish, or (worst case) finding a simulator
exploit. Every one of those is a *valid* strategy inside the rules and an
*invalid* measurement, so we detect them explicitly and label the result
instead of pretending the win was earned.

Each detector returns a normalised rate plus a `fired` boolean against a
documented threshold. `scan_replay()` runs them all over a finished replay
and produces a report that is:

  * attached to the replay-integrity endpoint (/api/integrity/{mid})
  * recomputable offline by `tools/run_match.py verify <replay.json>`
  * exported per match so a dataset consumer can filter gaming out

Deliberately conservative: detectors describe *behaviour*, not intent, and
the report always includes the raw rate so a reviewer can disagree with
our threshold.

Thresholds live in THRESHOLDS and are part of the benchmark spec — changing
one is a methodology change that must be noted in the monthly report.
"""
from __future__ import annotations

GUARD_ACTIONS = {"guard_high", "guard_low"}
RETREAT_FOOTWORK = {"retreat", "hop_back"}
ATTACK_ACTIONS = {
    "thrust", "overhead_slash", "horizontal_slash", "rising_slash",
    "pommel_strike", "spin_up", "overhead_smash", "wide_swing", "yank_back",
    "handle_jab", "draw_shot", "quick_shot", "high_arc_shot", "bow_bash",
}
# Crude but effective: phrases that show up in prompt-injection probes.
_INJECTION_PATTERNS = (
    "ignore previous", "ignore all previous", "disregard the above",
    "system prompt", "you are now", "new instructions", "override",
    "jailbreak", "reveal your instructions", "api key", "reveal your prompt",
)

THRESHOLDS = {
    "invalid_action_rate": 0.30,     # >30% of turns malformed
    "identical_action_run": 0.60,    # >60% of turns one repeated action
    "guard_rate": 0.60,              # >60% of turns spent guarding
    "retreat_rate": 0.60,            # >60% of turns retreating
    "no_attack_rate": 0.50,          # >50% of turns without any attack
    "edge_camping_rate": 0.80,       # >80% of frames pinned to a wall
    "injection_rate": 0.0,           # any injection-shaped output is flagged
    "truncated_thought_rate": 0.50,  # >50% of thoughts hit the 160-char cap
    "fallback_rate": 0.50,           # >50% of turns played by a script
}


def _frames_fighter_x(frames, fighter_idx):
    """Torso x for fighter 0/1 across frames (replay row layout).

    Row layout: [hp1, hp2, turn, over] then, per fighter, 11 bodies ×
    (x, y, angle) — torso is the first body of each fighter. Extra flail
    bodies are appended AFTER both fighters, so the offsets hold.
    """
    base = 4 + fighter_idx * 11 * 3
    out = []
    for row in frames or []:
        try:
            out.append(float(row[base]))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _actions_for_side(action_log, side):
    acts = []
    for entry in action_log or []:
        entry = entry if isinstance(entry, dict) else {}
        d = entry.get(side) or {}
        if isinstance(d, dict) and d.get("action"):
            acts.append((d.get("action"), d.get("footwork")))
    return acts


def _longest_run(values):
    best = cur = 0
    prev = None
    for v in values:
        if v == prev:
            cur += 1
        else:
            cur = 1
            prev = v
        best = max(best, cur)
    return best


def scan_replay(replay: dict, thresholds: dict | None = None) -> dict:
    """Run every detector over a finished replay.

    Returns {"clean": bool, "flags": [...], "checks": {rate: value}} plus a
    per-side breakdown. Never raises — a malformed replay yields an
    "insufficient data" report, not a crash.
    """
    th = dict(THRESHOLDS)
    th.update(thresholds or {})
    doc = replay if isinstance(replay, dict) else {}
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
    action_log = meta.get("action_log") or []
    frames = doc.get("frames") or []
    thoughts = doc.get("thoughts") or []
    width = meta.get("width") or 1280
    turns = int(meta.get("total_turns") or len(action_log) or 0) or 1

    report = {"clean": True, "flags": [], "checks": {}, "per_side": {},
              "thresholds": th, "turns": turns, "data_sufficient": bool(action_log)}

    if not action_log:
        report["flags"].append(
            "insufficient data: replay has no action log — anti-gaming "
            "behaviours cannot be assessed (replay predates spec v1.0)")
        report["clean"] = False
        return report

    # ---- global checks -------------------------------------------------
    invalid = int(prov.get("invalid_actions_a") or 0) + \
        int(prov.get("invalid_actions_b") or 0)
    invalid_rate = round(invalid / (2.0 * turns), 4)
    report["checks"]["invalid_action_rate"] = invalid_rate

    trunc = sum(1 for t in thoughts
                for side in ("a", "b")
                if len(str((t or {}).get(side) or "")) >= 159)
    trunc_rate = round(trunc / max(1, 2 * len(thoughts)), 4) if thoughts else 0.0
    report["checks"]["truncated_thought_rate"] = trunc_rate

    fb_rate = 0.0
    if isinstance(meta.get("evaluation_integrity"), dict):
        ei = meta["evaluation_integrity"]
        fb_rate = round((int(ei.get("fallback_turns_a") or 0) +
                         int(ei.get("fallback_turns_b") or 0)) /
                        (2.0 * turns), 4)
    report["checks"]["fallback_rate"] = fb_rate

    injections = 0
    for t in thoughts:
        for side in ("a", "b"):
            txt = str((t or {}).get(side) or "").lower()
            if any(p in txt for p in _INJECTION_PATTERNS):
                injections += 1
    inj_rate = round(injections / max(1, 2 * len(thoughts)), 4) if thoughts else 0.0
    report["checks"]["injection_rate"] = inj_rate

    # ---- per-side behavioural checks ----------------------------------
    edge = max(60.0, width * 0.06)          # within 6% of an arena wall
    for side, idx in (("a", 0), ("b", 1)):
        acts = _actions_for_side(action_log, side)
        if not acts:
            continue
        n = len(acts)
        actions = [a for a, _ in acts]
        footwork = [f for _, f in acts]
        guard_rate = round(sum(1 for a in actions if a in GUARD_ACTIONS) / n, 4)
        retreat_rate = round(sum(1 for f in footwork
                                 if f in RETREAT_FOOTWORK) / n, 4)
        no_attack = round(sum(1 for a in actions
                              if a not in ATTACK_ACTIONS) / n, 4)
        run = _longest_run(actions)
        run_rate = round(run / n, 4)
        xs = _frames_fighter_x(frames, idx)
        camp = (sum(1 for x in xs if x < edge or x > width - edge) / len(xs)
                if xs else 0.0)
        side_report = {
            "turns": n, "guard_rate": guard_rate,
            "retreat_rate": retreat_rate, "no_attack_rate": no_attack,
            "identical_action_run": run, "identical_action_rate": run_rate,
            "edge_camping_rate": round(camp, 4),
        }
        report["per_side"][side] = side_report

        def _flag(name, value, threshold, desc):
            if value > threshold:
                report["flags"].append(
                    f"{side.upper()}: {desc} ({value} > {threshold})")

        _flag("guard_rate", guard_rate, th["guard_rate"], "excessive guarding")
        _flag("retreat_rate", retreat_rate, th["retreat_rate"], "stalling / kiting")
        _flag("no_attack_rate", no_attack, th["no_attack_rate"],
              "passive play (no attacks)")
        _flag("identical_action_rate", run_rate, th["identical_action_run"],
              f"repeated identical action (run of {run})")
        _flag("edge_camping_rate", side_report["edge_camping_rate"],
              th["edge_camping_rate"], "boundary camping")

    def _gflag(name, value, desc):
        if value > th[name]:
            report["flags"].append(f"{desc} ({value} > {th[name]})")

    _gflag("invalid_action_rate", invalid_rate, "high invalid-action rate")
    _gflag("truncated_thought_rate", trunc_rate, "most thoughts hit the "
                                                 "length cap")
    _gflag("fallback_rate", fb_rate, "majority of turns played by a scripted "
                                     "fallback")
    _gflag("injection_rate", inj_rate, "prompt-injection-shaped output detected")

    report["clean"] = not report["flags"]
    # A flagged match is not automatically excluded — but it IS labelled,
    # and the monthly report aggregates these.
    report["verdict"] = ("no adversarial behaviour detected"
                         if report["clean"] else
                         "labelled — review before using this match as "
                         "evidence of tactical skill")
    return report


__all__ = ["scan_replay", "THRESHOLDS"]
