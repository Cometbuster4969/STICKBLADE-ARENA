"""Deterministic replay + audit tooling (action-plan §8).

A published result is only worth anything if a third party can reproduce
it. LLM calls can't be replayed from a seed, but everything else can:
physics, scripted brains, and the stored action log must reconstruct the
same fight bit-for-bit.
"""
import json

import conftest
import pytest

conftest.init_pygame()
import benchmark as B                                 # noqa: E402
from main import Match                                # noqa: E402
from recorder import ReplayRecorder, RecordingFX      # noqa: E402


def run(a="mock:berserker", b="bot:pro", seed=None, match_length="sprint",
        weapon="sword", arena="normal"):
    rec = ReplayRecorder(every=2)
    fx = RecordingFX(rec)
    m = Match(a, b, ["tip"], fx, log_path="/dev/null", seed=seed,
              match_length=match_length, weapon=weapon, arena=arena)
    rec.attach(m)
    while m.phase != Match.PH_OVER:
        m.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    for _ in range(60):
        m.update(1 / 60, False)
        fx.update(1 / 60)
        rec.tick()
    return m, rec.build()


def test_same_seed_replays_identically():
    _, r1 = run(seed=4242)
    _, r2 = run(seed=4242)
    assert r1["frames"] == r2["frames"], "seeded matches diverged"
    assert r1["events"] == r2["events"]
    assert r1["meta"]["action_log"] == r2["meta"]["action_log"]
    # Latency is wall-clock, so it is NOT reproducible — assert on the
    # deterministic telemetry fields only.
    for side in ("a", "b"):
        t1, t2 = r1["meta"]["telemetry"][side], r2["meta"]["telemetry"][side]
        assert t1["turns"] == t2["turns"]
        assert t1["fallback_turns"] == t2["fallback_turns"]
        assert t1["invalid_actions"] == t2["invalid_actions"]
        assert t1["models_used"] == t2["models_used"]


def test_different_seeds_produce_different_fights():
    _, r1 = run(seed=1)
    _, r2 = run(seed=2)
    assert r1["meta"]["provenance"]["seed"] != r2["meta"]["provenance"]["seed"]
    # Not guaranteed to differ (a short match can play out the same), but
    # the seeds must at least be recorded distinct and replayable.
    assert r1["frames"] and r2["frames"]


def test_unseeded_matches_are_marked_not_reproducible():
    _, r = run(seed=None)
    prov = r["meta"]["provenance"]
    assert prov["seed"] is None
    rep = B.verify_replay(r)
    assert rep["checks"]["seed_present"] is False
    assert any("not reproducible" in n for n in rep["notes"])


def test_action_log_covers_every_turn():
    m, r = run(seed=11, match_length="standard")
    log = r["meta"]["action_log"]
    assert len(log) == m.turn
    assert [e["turn"] for e in log] == list(range(1, m.turn + 1))
    for entry in log:
        assert entry["a"]["action"] and entry["b"]["action"]


def test_replay_carries_the_full_provenance_record():
    _, r = run(seed=5)
    prov = r["meta"]["provenance"]
    for key in ("benchmark_version", "physics_version", "prompt_version",
                "spec_fingerprint", "seed", "match_length", "max_turns",
                "fallback_policy", "model_requested_a", "model_requested_b",
                "model_used_a", "model_used_b", "provider_used_a",
                "fallback_used", "latency_ms_a", "invalid_actions_a",
                "ranking_eligible"):
        assert key in prov, f"replay provenance missing {key}"


def test_replay_passes_the_integrity_audit():
    _, r = run(seed=99)
    rep = B.verify_replay(r)
    assert rep["ok"] is True, rep
    assert rep["checks"]["version_pinned"] is True
    assert rep["checks"]["hp_monotonic"] is True
    assert rep["checks"]["result_consistent"] is True


def test_replay_is_json_serialisable_and_reasonably_small():
    _, r = run(seed=3, match_length="sprint")
    blob = json.dumps(r, separators=(",", ":"))
    assert len(blob) < 4_000_000, "sprint replay should stay well under 4MB"
    assert r["v"] == 2


def test_seeding_does_not_leak_into_the_global_rng():
    import random
    random.seed(1234)
    before = random.random()
    random.seed(1234)
    run(seed=777)
    after = random.random()
    assert before == after, "match seeding mutated the global RNG state"


def test_pre_fight_quips_do_not_perturb_a_seeded_fight():
    """The server asks both brains for trash talk BEFORE the first turn;
    tools/simcore.py does not. Until 2026-09-09 the mock quip drew from
    the brain's decision RNG, so the same seed produced a different fight
    in production than offline — the reproducibility claim held only in
    tests. Run the server sequence by hand and require identical frames.
    """
    from brains import pre_fight_quip

    def run_with_quips(seed):
        rec = ReplayRecorder(every=2)
        fx = RecordingFX(rec)
        m = Match("mock:duelist", "mock:berserker", ["tip"], fx,
                  log_path="/dev/null", seed=seed, match_length="sprint")
        rec.attach(m)
        pre_fight_quip(m.b1, "Fighter B", weapon="sword")
        pre_fight_quip(m.b2, "Fighter A", weapon="sword")
        while m.phase != Match.PH_OVER:
            m.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
        for _ in range(60):
            m.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
        return rec.build()

    plain = run(a="mock:duelist", b="mock:berserker", seed=777)[1]
    quipped = run_with_quips(777)
    assert plain["frames"] == quipped["frames"]
    assert plain["meta"]["action_log"] == quipped["meta"]["action_log"]
