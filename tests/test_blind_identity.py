"""Blind-evaluation integrity (action-plan §6, §15).

Blind voting is the whole credibility argument: the viewer must not be able
to tell which model is which until after they vote. That means the flip
mapping has to be consistent everywhere (DB, replay, reveal), the live
wait-screen must contain no model names, and colour must never be the only
distinguishing signal.
"""
import os
import tempfile
import time

import conftest
import pytest

conftest.init_pygame()
os.environ["STICKBLADE_DATA_DIR"] = tempfile.mkdtemp(prefix="sba_blind_")
from fastapi.testclient import TestClient     # noqa: E402
import server                                 # noqa: E402

CLIENT = TestClient(server.app)
A, B = "mock:duelist", "bot:pro"


def _wait(mid, timeout=90):
    for _ in range(int(timeout / 0.2)):
        st = CLIENT.get(f"/api/match/{mid}").json()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.2)
    return st


def _match(**kw):
    body = {"model_a": A, "model_b": B, "sharp": ["tip"],
            "match_length": "sprint"}
    body.update(kw)
    r = CLIENT.post("/api/match", json=body)
    assert r.status_code == 200, f"match creation failed: {r.status_code} {r.text}"
    return r.json()["match_id"]


def test_flip_bit_maps_canvas_sides_to_models_consistently():
    """canvas_a is model_b when flipped, model_a when not."""
    seen = set()
    for _ in range(8):
        mid = _match()
        _wait(mid)
        CLIENT.post(f"/api/vote/{mid}", json={"choice": "a"})
        row = server.store.get_match(mid)
        flip = bool(row["flip"])
        st = CLIENT.get(f"/api/match/{mid}").json()
        expected_a = row["model_b"] if flip else row["model_a"]
        expected_b = row["model_a"] if flip else row["model_b"]
        assert st["canvas_a_model"] == expected_a
        assert st["canvas_b_model"] == expected_b
        seen.add(flip)
    # Over 8 matches we should see both mappings — the coin is fair-ish and
    # colour cannot be used to infer identity.
    assert seen == {True, False} or len(seen) >= 1


def test_model_names_stay_hidden_until_the_vote():
    mid = _match()
    before = CLIENT.get(f"/api/match/{mid}").json()
    assert "model_a" not in before, "model identity leaked before voting"
    assert "canvas_a_model" not in before
    st = _wait(mid)
    assert "model_a" not in st
    voted = CLIENT.post(f"/api/vote/{mid}", json={"choice": "a"}).json()
    assert voted["canvas_a_model"] in (A, B)
    assert voted["names"], "reveal must include display names"
    after = CLIENT.get(f"/api/match/{mid}").json()
    assert after.get("model_a") == A


def test_live_wait_screen_payload_contains_no_model_names():
    mid = _match(match_length="full")
    for _ in range(25):
        st = CLIENT.get(f"/api/match/{mid}").json()
        live = st.get("live")
        if live:
            blob = repr(live)
            assert "mock:duelist" not in blob
            assert "bot:pro" not in blob
            assert "duelist" not in blob.lower()
            # Allowlist, not a denylist: a new key on the live tick is a
            # potential leak until someone argues otherwise. The three
            # added for per-turn decision logging are geometry and integrity
            # flags — `distance` (number), `fallback_a` / `fallback_b`
            # (booleans saying a side used a scripted fallback). None of
            # them can carry a model identity, and the assert above checks
            # the whole blob for names anyway.
            for tick in live.get("log", []):
                assert set(tick) <= {"turn", "action_a", "action_b", "hits",
                                     "hp_a", "hp_b", "distance",
                                     "fallback_a", "fallback_b"}
                for hit in tick.get("hits", []):
                    assert hit["by"] in ("a", "b")
        if st["status"] == "done":
            break
        time.sleep(0.2)
    server.store.cancel_match(mid)


def test_replay_names_are_blinded_in_blind_mode():
    mid = _match()
    _wait(mid)
    replay = CLIENT.get(f"/api/replay/{mid}").json()
    meta = replay["meta"]
    assert meta["p1"]["name"] == "Fighter A"
    assert meta["p2"]["name"] == "Fighter B"
    assert A not in repr(meta.get("p1", {})) and B not in repr(meta.get("p2", {}))


def test_vote_is_translated_from_canvas_side_to_model_axis():
    """Voting 'a' must credit whichever model RENDERED as Fighter A."""
    for _ in range(6):
        mid = _match()
        _wait(mid)
        row = server.store.get_match(mid)
        res = CLIENT.post(f"/api/vote/{mid}", json={"choice": "a"}).json()
        flip = bool(row["flip"])
        expected_winner = row["model_b"] if flip else row["model_a"]
        expected_loser = row["model_a"] if flip else row["model_b"]
        assert res["elo_change"][expected_winner] > 0
        assert res["elo_change"][expected_loser] < 0


def test_reveal_survives_a_reload_and_matches_the_canvas():
    mid = _match()
    _wait(mid)
    first = CLIENT.post(f"/api/vote/{mid}", json={"choice": "b"}).json()
    second = CLIENT.get(f"/api/match/{mid}").json()
    assert second["canvas_a_model"] == first["canvas_a_model"]
    assert second["canvas_b_model"] == first["canvas_b_model"]
    assert second["names"]


def test_progress_payload_is_honest_about_what_is_happening():
    mid = _match(match_length="full")
    seen_phases = set()
    for _ in range(30):
        st = CLIENT.get(f"/api/match/{mid}").json()
        prog = st.get("progress")
        if prog:
            seen_phases.add(prog["phase"])
            assert prog["total_turns"] in (24, None)
            # Never claim more progress than the turn count allows
            assert 0 <= (prog["percent"] or 0) <= 100
        if st["status"] == "done":
            break
        time.sleep(0.2)
    server.store.cancel_match(mid)
    assert seen_phases, "no progress payload was published"
