"""tools/export_dataset.py — versioned release, whitelist, hashes, verify.

The exporter is the boundary between the database and the public. Tests
pin the three things that matter there: nothing leaves that is not in the
data dictionary, the side convention survives the flatten, and a release
verifies against its own manifest (and fails when tampered with).
"""
import json
import pathlib

import pytest

import export_dataset as X


def _export_row(mid="m1", flip=0, votes=None, **kw):
    r = {
        "id": mid, "created": 1_788_950_000.0 + hash(mid) % 100,
        "model_a": "bot:pro", "model_b": "mock:duelist", "flip": flip,
        "sharp": "tip", "weapon": "sword", "mode": "macro", "arena": "normal",
        "blindfolded": 0, "blind": 1, "status": "done", "winner_side": "a",
        "method": "points", "turns": 4, "voted": 1 if votes else 0,
        "benchmark_version": "1.0", "physics_version": "1.0",
        "prompt_version": 2, "spec_fingerprint": "09de66effd02",
        "seed": 7, "match_length": "sprint", "max_turns": 4,
        "fallback_policy": "strict",
        "model_used_a": "bot:pro", "model_used_b": "mock:duelist",
        "provider_used_a": "scripted", "provider_used_b": "scripted",
        "fallback_used": 0, "ranking_eligible": 1,
        "latency_ms_a": 0.3, "latency_ms_b": 0.2,
        "prompt_tokens_a": 0, "completion_tokens_a": 0,
        "prompt_tokens_b": 0, "completion_tokens_b": 0,
        "api_calls_a": 0, "api_calls_b": 0,
        "invalid_actions_a": 0, "invalid_actions_b": 0,
        "fallback_turns_a": 0, "fallback_turns_b": 0,
        "damage_dealt_a": 10.0, "damage_dealt_b": 2.0,
        "hits_landed_a": 2, "hits_landed_b": 1,
        "hits_attempted_a": 3, "hits_attempted_b": 3, "avg_distance": 80.0,
        # things that must NOT appear in a release
        "commentary": "trash talk", "error": None, "cancelled": 0,
        "api_key": "sk-or-SHOULD-NEVER-LEAK", "ip": "203.0.113.9",
        "models_used_a": '{"bot:pro": 4}',
        "votes": votes or [],
    }
    r.update(kw)
    return r


def _replay():
    return {
        "meta": {"p1": {"name": "Fighter A"}, "p2": {"name": "Fighter B"},
                 "action_log": [{"turn": 1, "a": {"action": "thrust", "footwork": "advance"},
                                 "b": {"action": "guard", "footwork": "hold"}}],
                 "telemetry": {"turns": [{"turn": 1,
                                          "a": {"latency_ms": 0.3, "fallback": False,
                                                "invalid": False, "model": "bot:pro",
                                                "provider": "scripted"},
                                          "b": {"latency_ms": 0.2, "fallback": True,
                                                "invalid": True, "model": "mock:duelist",
                                                "provider": "scripted"}}]}},
        "events": [{"f": 10, "k": "hit", "x": 1.0, "y": 2.0, "d": 5.0, "s": 1,
                    "l": 0, "part": "torso", "by": "Fighter B"},
                   {"f": 12, "k": "clash", "x": 1.0, "y": 2.0, "d": 0, "s": 0,
                    "l": 0, "part": ""}],
        "thoughts": [{"f": 0, "turn": 1, "a": "close in", "b": "hold"}],
    }


# ---------------------------------------------------------------- tables
def test_whitelist_blocks_everything_not_in_the_dictionary():
    tables = X.build_tables([_export_row()], {}, "vtest")
    m = tables["matches"][0]
    for banned in ("api_key", "ip", "commentary", "error", "cancelled",
                   "models_used_a", "votes", "id"):
        assert banned not in m
    assert set(m) == {c for c, _, _ in X.TABLES["matches"]}
    # and the serialisers only emit dictionary columns even if a row has extras
    m["sneaky"] = "x"
    assert "sneaky" not in X.to_jsonl("matches", [m])
    assert "sneaky" not in X.to_csv("matches", [m])


def test_secret_never_reaches_any_file(tmp_path):
    tables = X.build_tables([_export_row(votes=[{"id": "v1", "created": 1.0,
                                                 "choice": "a",
                                                 "voter_tier": "expert"}])],
                            {"m1": _replay()}, "vtest")
    out, _ = X.write_release(tables, tmp_path, "vtest", {"source": "test"},
                             bootstraps=10)
    for p in out.rglob("*"):
        if p.is_file() and p.suffix != ".parquet":
            assert "SHOULD-NEVER-LEAK" not in p.read_text()
            assert "203.0.113.9" not in p.read_text()


def test_vote_counts_split_by_tier_and_has_replay_flag():
    votes = [{"id": "v1", "created": 1.0, "choice": "a", "voter_tier": "expert"},
             {"id": "v2", "created": 2.0, "choice": "b"},
             {"id": "v3", "created": 3.0, "choice": "draw", "voter_tier": "casual"}]
    tables = X.build_tables([_export_row(votes=votes), _export_row(mid="m2")],
                            {"m1": _replay()}, "vtest")
    m1, m2 = tables["matches"]
    assert (m1["votes_total"], m1["votes_a"], m1["votes_b"], m1["votes_draw"]) == (3, 1, 1, 1)
    assert (m1["votes_expert"], m1["votes_casual"]) == (1, 2)
    assert m1["has_replay"] == 1 and m2["has_replay"] == 0
    assert len(tables["votes"]) == 3
    assert tables["votes"][1]["voter_tier"] == "casual"     # default filled


def test_events_and_actions_flatten_with_canvas_sides():
    tables = X.build_tables([_export_row()], {"m1": _replay()}, "vtest")
    ev = tables["events"]
    assert [e["kind"] for e in ev] == ["hit", "clash"]
    assert ev[0]["by"] == "b" and ev[1]["by"] is None
    assert ev[0]["part"] == "torso" and ev[0]["lethal"] == 0
    ac = {(a["turn"], a["side"]): a for a in tables["actions"]}
    assert ac[(1, "a")]["action"] == "thrust"
    assert ac[(1, "a")]["thought"] == "close in"
    assert ac[(1, "b")]["fallback"] == 1 and ac[(1, "b")]["invalid"] == 1
    assert ac[(1, "b")]["provider"] == "scripted"
    assert ac[(1, "a")]["joints"] is None


def test_ratings_snapshot_credits_votes_through_flip():
    # flip=1: model_a fought as canvas B. A vote for canvas 'a' is for model_b.
    votes = [{"id": "v", "created": 1.0, "choice": "a"}]
    rows = [_export_row(mid=f"m{i}", flip=1, votes=votes) for i in range(4)]
    tables = X.build_tables(rows, {}, "vtest")
    snap = X.ratings_snapshot(tables, bootstraps=10)
    top = snap["rows"][0]
    assert top["model"] == "mock:duelist"       # model_b, via flip
    assert top["wins"] == 4
    assert snap["comparisons"] == 4


def test_ineligible_matches_are_excluded_from_the_refit():
    votes = [{"id": "v", "created": 1.0, "choice": "a"}]
    rows = [_export_row(mid="ok", votes=votes),
            _export_row(mid="bad", votes=votes, ranking_eligible=0)]
    snap = X.ratings_snapshot(X.build_tables(rows, {}, "vtest"), bootstraps=10)
    assert snap["comparisons"] == 1


# --------------------------------------------------------------- release
def test_release_layout_manifest_schema_and_hashes(tmp_path):
    rows = [_export_row(mid=f"m{i}", votes=[{"id": f"v{i}", "created": 1.0,
                                             "choice": "a"}]) for i in range(3)]
    tables = X.build_tables(rows, {"m0": _replay()}, "v2026.09.09")
    out, man = X.write_release(tables, tmp_path, "v2026.09.09",
                               {"source": "test"}, bootstraps=10)
    assert out == tmp_path / "v2026.09.09"
    for t in X.TABLES:
        assert (out / t / f"{t}.jsonl").exists()
        assert (out / t / f"{t}.csv").exists()
    for f in ("README.md", "MANIFEST.json", "SCHEMA.json", "SHA256SUMS"):
        assert (out / f).exists()
    assert man["counts"] == {"matches": 3, "votes": 3, "events": 2, "actions": 2}
    assert man["dataset_version"] == "v2026.09.09"
    assert man["benchmark_versions"] == ["1.0"]
    assert man["prompt_versions"] == ["2"]
    assert man["data_quality"]["evidence_level"] == "scripted_only"
    assert man["license"] == "CC-BY-SA-4.0"
    # every listed hash is correct and covers every data file
    for name, h in man["hashes"].items():
        assert X.sha256_file(out / name) == h
    assert "matches/matches.jsonl" in man["hashes"]
    assert "MANIFEST.json" not in man["hashes"]
    sums = (out / "SHA256SUMS").read_text()
    assert sums.count("\n") == len(man["hashes"])
    schema = json.loads((out / "SCHEMA.json").read_text())
    assert set(schema["tables"]) == set(X.TABLES)
    assert "side_convention" in schema
    readme = (out / "README.md").read_text()
    assert readme.startswith("---\nlicense: cc-by-sa-4.0")
    assert "scripted_only" in readme
    assert "say nothing about any language model" in readme


def test_verify_passes_on_a_fresh_release_and_fails_when_tampered(tmp_path):
    rows = [_export_row(mid=f"m{i}", votes=[{"id": f"v{i}", "created": 1.0,
                                             "choice": "a" if i % 2 else "b"}])
            for i in range(6)]
    tables = X.build_tables(rows, {}, "vtest")
    out, _ = X.write_release(tables, tmp_path, "vtest", {"source": "test"},
                             bootstraps=10)
    ok, info = X.verify_release(out, bootstraps=10, verbose=False)
    assert ok, info
    assert info["ratings_match"] and info["counts_ok"]
    # flip one vote → hash mismatch AND a different refit
    p = out / "votes" / "votes.jsonl"
    lines = p.read_text().splitlines()
    v = json.loads(lines[0]); v["choice"] = "a" if v["choice"] == "b" else "b"
    lines[0] = json.dumps(v)
    p.write_text("\n".join(lines) + "\n")
    ok2, info2 = X.verify_release(out, bootstraps=10, verbose=False)
    assert not ok2
    assert info2["hash_mismatches"] == ["votes/votes.jsonl"]


def test_empty_release_is_valid(tmp_path):
    tables = X.build_tables([], {}, "vempty")
    out, man = X.write_release(tables, tmp_path, "vempty", {"source": "test"},
                               bootstraps=5)
    assert man["counts"]["matches"] == 0
    assert man["ratings_snapshot"]["rows"] == []
    ok, _ = X.verify_release(out, bootstraps=5, verbose=False)
    assert ok
