"""Process-wide runtime state shared by the HTTP layer and the workers.

Server.py used to own all of this inline. It is split out because the state
outlives any single request and is touched from three places — the async
request handlers, the single-match worker thread, and the tournament worker
thread — and because `store` + the live-state dicts are the only things the
two workers need from the "server" at all.

Ordering matters: `store` is created at import time from the environment
(`SUPABASE_URL`/`SUPABASE_KEY`, else `STICKBLADE_DATA_DIR`), so anything that
imports this module inherits that choice. Tests set `STICKBLADE_DATA_DIR`
before importing `server`, which imports this.
"""
from __future__ import annotations

import os
import queue
import re as _re_top
import threading
import time

from storage import LocalStorage


def _safe_err(e) -> str:
    """Sanitize an exception message before it reaches the user.

    Real exception text often embeds full URLs (with `?api_key=...` or
    `Bearer ...` tokens), filesystem paths, and stack frames. We replace
    those with a friendly category label and keep it short."""
    s = str(e) if not isinstance(e, str) else e
    # strip URLs
    s = _re_top.sub(r"https?://\S+", "<url>", s)
    # strip bearer-ish tokens / api keys
    s = _re_top.sub(r"(?i)(api[_-]?key|bearer|token)[=:\s]+\S+", r"\1 <hidden>", s)
    # strip bare sk-* / sk-or-* tokens (BYOK keys might appear raw in
    # upstream error bodies without a bearer/api_key prefix)
    s = _re_top.sub(r"sk-[a-zA-Z0-9_-]{16,}", "<hidden-key>", s)
    # strip absolute paths
    s = _re_top.sub(r"/[a-zA-Z0-9_/.-]{12,}", "<path>", s)
    # collapse whitespace, clamp
    s = _re_top.sub(r"\s+", " ", s).strip()
    if len(s) > 160:
        s = s[:160].rstrip() + "…"
    # bucket by category if it's a known shape, more useful than the verbatim text
    if "404" in s or "not found" in s.lower():
        return "model not available (404)"
    if "429" in s or "too many" in s.lower() or "rate" in s.lower():
        return "rate limited by upstream (429)"
    if "401" in s or "403" in s or "unauthor" in s.lower():
        return "upstream auth failed (check API key)"
    if "timeout" in s.lower() or "timed out" in s.lower():
        return "model timed out"
    return s or "internal error"



OBS = {
    "started_at": time.time(),
    "matches_created": 0, "matches_done": 0, "matches_error": 0,
    "matches_cancelled": 0, "votes_recorded": 0, "vote_errors": 0,
    "replays_served": 0, "replay_errors": 0, "export_rows": 0,
    "turn_latency_ms": [],          # bounded ring of recent decision latencies
    "provider_errors": {},          # provider -> count
    "last_error": None, "last_error_at": None,
}
OBS_LOCK = threading.Lock()
_OBS_RING_MAX = 500


def _obs_bump(key, n=1):
    with OBS_LOCK:
        OBS[key] = OBS.get(key, 0) + n


def _obs_error(err, where="", provider=None):
    with OBS_LOCK:
        OBS["last_error"] = f"{where}: {str(err)[:180]}"
        OBS["last_error_at"] = time.time()
        if provider:
            OBS["provider_errors"][provider] = \
                OBS["provider_errors"].get(provider, 0) + 1


def _obs_latency(samples):
    """Record per-turn decision latencies (bounded ring buffer)."""
    if not samples:
        return
    with OBS_LOCK:
        OBS["turn_latency_ms"].extend(float(x) for x in samples)
        if len(OBS["turn_latency_ms"]) > _OBS_RING_MAX:
            OBS["turn_latency_ms"] = OBS["turn_latency_ms"][-_OBS_RING_MAX:]

if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
    from storage_supabase import SupabaseStorage
    store = SupabaseStorage()
    print("[server] storage: Supabase (persistent)")
else:
    # STICKBLADE_DATA_DIR lets tests / local runs keep match data out of the
    # repo tree (the committed arena_data/ is a seed artifact).
    store = LocalStorage(root=os.environ.get("STICKBLADE_DATA_DIR", "arena_data"))
    print(f"[server] storage: local SQLite at {store.root} (set "
          "SUPABASE_URL + SUPABASE_KEY for persistence)")

try:
    store.cleanup_stale_matches()
except Exception as e:
    print(f"[server] cleanup_stale_matches notice: {e}")

jobs: "queue.Queue[str]" = queue.Queue()
# Tournaments get their own queue + worker so a bracket can't starve the
# single-match queue (a bracket runs 3-7 matches back to back).
tournament_jobs: "queue.Queue[str]" = queue.Queue()
MATCH_MODES: dict = {}   # match_id -> "macro" | "joint" (in-memory; default macro)

BLIND_NAMES = {"a": "Fighter A", "b": "Fighter B"}
BLIND_COLORS = {"a": ("#56dc82", 1), "b": ("#5aa0ff", 2)}

# Per-match A↔green / B↔blue assignment, picked at queue time and consumed
# by the worker when the simulation kicks off. Keeps the user from knowing
# which colored ragdoll is the model they personally picked.
MATCH_FLIP = {}     # mid -> bool   True = (model_a -> Fighter B, model_b -> Fighter A)

# BYOK — per-match OpenRouter API keys. Never persisted to DB, never
# echoed back in any API response, popped when the sim finishes. Only
# lives here for the ~30s window between /api/match POST and the worker
# picking up the job. Access is single-threaded (worker consumes, request
# handler produces) so no lock is needed — but be careful if that changes.
MATCH_API_KEYS: dict = {}

# ----------------------------------------------------------------------
# Live in-progress state exposed to the wait screen (spoiler-safe).
# Populated by the worker as the sim runs; wiped in the finally clause
# alongside MATCH_MODES/MATCH_FLIP. Contents are BLIND — canvas-side
# labels ("Fighter A"/"Fighter B") only, no model names, so the wait
# screen can show them without leaking who's who before the vote.
#   LIVE_STATE[mid] = {
#       "quips":       {"a": "...", "b": "..."} | None,
#       "turn":        int,          # current turn number (0 before quips resolve)
#       "log":         [ {turn, action_a, action_b, hits:[...]} , ... ],
#       "queue_pos":   int | None,   # positions ahead when queued (0 = running)
#   }
# Bounded: log capped at MAX_LOG_TICKS entries per match; ~40 KB worst case.
# ----------------------------------------------------------------------
LIVE_STATE: dict = {}
LIVE_STATE_LOCK = threading.Lock()
MAX_LOG_TICKS = 30   # ticker only shows last 5-8; keep a small tail for late joiners


def _row_get(row, key, default=None):
    """Safe accessor for match rows (dict-like; key may be absent)."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def _live_init(mid):
    with LIVE_STATE_LOCK:
        LIVE_STATE[mid] = {"quips": None, "turn": 0, "log": [],
                           "queue_pos": None, "phase": "queued",
                           "total_turns": None, "match_length": None,
                           "seed": None, "started_at": None,
                           "cancelled": False}


def _live_set(mid, **fields):
    with LIVE_STATE_LOCK:
        if mid in LIVE_STATE:
            LIVE_STATE[mid].update(fields)


def _live_append_turn(mid, entry):
    """Append one turn's blind summary (no model names)."""
    with LIVE_STATE_LOCK:
        st = LIVE_STATE.get(mid)
        if st is None:
            return
        st["log"].append(entry)
        if len(st["log"]) > MAX_LOG_TICKS:
            st["log"] = st["log"][-MAX_LOG_TICKS:]
        st["turn"] = entry.get("turn", st["turn"])


def _live_clear(mid):
    with LIVE_STATE_LOCK:
        LIVE_STATE.pop(mid, None)


def _live_snapshot(mid):
    with LIVE_STATE_LOCK:
        st = LIVE_STATE.get(mid)
        if st is None:
            return None
        # return a shallow copy so caller can serialize without lock
        return {"quips": st["quips"], "turn": st["turn"],
                "log": list(st["log"]), "queue_pos": st["queue_pos"],
                "phase": st.get("phase", "queued"),
                "total_turns": st.get("total_turns"),
                "match_length": st.get("match_length"), "seed": st.get("seed"),
                "started_at": st.get("started_at"),
                "cancelled": st.get("cancelled", False)}


def _live_publish_turn(mid, log_entry, f1, f2, flip):
    """Translate one Match.log entry into a spoiler-safe wait-screen tick.

    Blind rules:
      - Use canvas-side keys ("a"/"b"), never model names.
      - Post-flip: fighter1 is always canvas "a" (green), fighter2 canvas "b".
        (Because run_simulation assigns slot_left->fighter1 already, and the
        flip already remapped model->slot. So we don't re-flip here.)
      - Include: turn #, both actions, hits (with damage + zone + sharp bool).
      - Include: current HP snapshot AFTER this turn (visible in the canvas
        HUD anyway, no new info).
      - Exclude: raw thoughts (already shown as speech bubbles later; also
        thoughts can leak model style / self-identification).
    """
    turn = log_entry.get("turn", 0)
    # The log dict is keyed by fighter name (Match._start_thinking builds
    # {self.f1.name: r1, self.f2.name: r2}). In blind mode both names are
    # "Fighter A" / "Fighter B" already, matching canvas sides.
    def _pick_action(fname):
        d = log_entry.get(fname)
        if not isinstance(d, dict):
            return None
        return {"action": d.get("action"), "footwork": d.get("footwork")}
    hits = []
    for e in log_entry.get("hits", []):
        # e = {"attacker": fighter_id (1|2), "zone", "part", "damage", "sharp"}
        # Translate attacker fighter-id to canvas side.
        attacker_side = "a" if e.get("attacker") == 1 else "b"
        hits.append({
            "by":     attacker_side,
            "zone":   e.get("zone"),
            "part":   e.get("part"),
            "damage": round(float(e.get("damage", 0)), 1),
            "sharp":  bool(e.get("sharp")),
        })
    # Degraded-turn disclosure, live. The decision context that Match writes
    # per turn carries the `_fallback` flag, so the wait screen can say
    # "Fighter B used a scripted fallback on turn 4" WHILE the match is still
    # running instead of only in the post-vote integrity banner. Benchmark
    # integrity is the whole product; hiding it until the end isn't.
    dec = log_entry.get("decision") or {}
    tick = {
        "turn":   turn,
        "action_a": _pick_action(f1.name),
        "action_b": _pick_action(f2.name),
        "hits":   hits,
        "hp_a":   round(float(f1.hp), 1),
        "hp_b":   round(float(f2.hp), 1),
        "distance": (dec.get("a") or {}).get("distance"),
        "fallback_a": bool((dec.get("a") or {}).get("fallback")),
        "fallback_b": bool((dec.get("b") or {}).get("fallback")),
    }
    _live_append_turn(mid, tick)


