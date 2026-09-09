"""BYOK handling: the privacy claim, tested (action-plan §21).

The site tells users their key is stored in localStorage only, used for one
match, and never logged or persisted. A claim like that should be verified
by tests, not trust. These tests fire a fake key through the whole stack
and then hunt for it in every place it could possibly leak.
"""
import os
import tempfile
import time

import conftest
import pytest

conftest.init_pygame()
os.environ["STICKBLADE_DATA_DIR"] = tempfile.mkdtemp(prefix="sba_byok_")
from fastapi.testclient import TestClient     # noqa: E402
import server                                 # noqa: E402

CLIENT = TestClient(server.app)
# Shape of a real OpenRouter key; generated here, valid nowhere.
FAKE_KEY = "sk-or-v1-" + "f" * 40
SHORT_KEY = "sk-short"


def _finish(**body):
    payload = {"model_a": "mock:duelist", "model_b": "mock:berserker",
               "sharp": ["tip"], "match_length": "sprint"}
    payload.update(body)
    mid = CLIENT.post("/api/match", json=payload).json()["match_id"]
    for _ in range(300):
        st = CLIENT.get(f"/api/match/{mid}").json()
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    return mid, st


def test_key_is_accepted_and_never_echoed_back():
    r = CLIENT.post("/api/match", json={
        "model_a": "mock:duelist", "model_b": "mock:berserker",
        "sharp": ["tip"], "match_length": "sprint", "api_key": FAKE_KEY})
    assert r.status_code == 200
    assert FAKE_KEY not in r.text
    assert "api_key" not in r.json()


def test_key_never_reaches_the_database_or_replay():
    mid, st = _finish(api_key=FAKE_KEY)
    assert st["status"] == "done", st
    row = server.store.get_match(mid)
    assert FAKE_KEY not in repr(row), "key persisted in the match row"
    replay = CLIENT.get(f"/api/replay/{mid}").json()
    assert FAKE_KEY not in repr(replay), "key embedded in the replay JSON"
    log_path = os.path.join(server.store.root, f"log_{mid}.json")
    if os.path.exists(log_path):
        with open(log_path) as f:
            assert FAKE_KEY not in f.read(), "key written to the match log"


def test_key_is_dropped_from_memory_after_the_match():
    mid, st = _finish(api_key=FAKE_KEY)
    assert st["status"] == "done", st
    assert mid not in server.MATCH_API_KEYS, "key survived the simulation"
    # ...and the in-memory map is empty of any secret
    for v in server.MATCH_API_KEYS.values():
        assert FAKE_KEY != v


def test_malformed_keys_are_ignored_not_stored():
    r = CLIENT.post("/api/match", json={
        "model_a": "mock:duelist", "model_b": "mock:berserker",
        "sharp": ["tip"], "match_length": "sprint", "api_key": SHORT_KEY})
    assert r.status_code == 200
    mid = r.json()["match_id"]
    assert mid not in server.MATCH_API_KEYS, "too-short key was accepted"
    server.store.cancel_match(mid)


def test_error_messages_are_scrubbed():
    from server import _safe_err
    dirty = ("httpx.HTTPStatusError: Client error '401 Unauthorized' for url "
             "https://openrouter.ai/api/v1/chat/completions?api_key="
             f"{FAKE_KEY} Bearer {FAKE_KEY} at /srv/app/brains.py")
    clean = _safe_err(dirty)
    assert FAKE_KEY not in clean
    assert "sk-" not in clean
    assert "openrouter.ai" not in clean
    assert len(clean) <= 200


def test_error_messages_are_categorised():
    from server import _safe_err
    assert _safe_err("HTTP 404 not found") == "model not available (404)"
    assert _safe_err("429 too many requests") == "rate limited by upstream (429)"
    assert _safe_err("401 unauthorized") == "upstream auth failed (check API key)"
    assert _safe_err("read timed out") == "model timed out"


def test_byok_key_is_not_logged_to_stdout(caplog):
    import logging
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    level = root.level
    root.setLevel(logging.DEBUG)
    try:
        _finish(api_key=FAKE_KEY)
    finally:
        root.removeHandler(handler)
        root.setLevel(level)
    assert FAKE_KEY not in stream.getvalue()


@pytest.mark.parametrize("path", ["/api/export?fmt=json&limit=20",
                                  "/api/export?fmt=csv&limit=20",
                                  "/api/recent", "/api/leaderboard",
                                  "/api/metrics", "/api/status"])
def test_exports_carry_no_key_material(path):
    _finish(api_key=FAKE_KEY)
    body = CLIENT.get(path).text
    assert FAKE_KEY not in body
    assert "sk-or-v1" not in body


def test_admin_token_is_not_reflected_in_responses():
    os.environ.setdefault("ADMIN_TOKEN", "unit-test-admin-token")
    r = CLIENT.get("/api/version")
    assert "unit-test-admin-token" not in r.text
