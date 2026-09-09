"""STICKBLADE ARENA — web backend (FastAPI).

Endpoints:
    GET  /api/models                 available fighters
    POST /api/match                  {model_a, model_b, sharp[], blind} -> {match_id}
    GET  /api/match/{id}             status (queued/running/done) + result when done
    GET  /api/replay/{id}            full replay JSON for the canvas player
    POST /api/vote/{id}              {choice: "a"|"b"|"draw"} -> reveal + Elo deltas
    GET  /api/leaderboard?sharp=tip  Elo table (per sharpness or overall)
    GET  /api/recent                 recent finished matches
    GET  /                           the arena web page (viewer + controls)

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import queue
import re as _re_top
import threading
import time


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

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal

import config as C
import security
from benchmark import max_turns_for
from storage import LocalStorage
from benchmark import (BENCHMARK_VERSION,
                       BENCHMARK_VERSION as BENCH_SPEC_VERSION,
                       PHYSICS_VERSION as PHYSICS_SPEC_VERSION,
                       SPEC_FINGERPRINT)

VERSION = "1.4.0"   # benchmark spec v1.0: provenance, match lengths,
                    # fallback policies, multi-axis votes, integrity audit

# ----------------------------------------------------------------------
# Observability (action-plan §19). In-process counters, cheap enough to
# read on every status-page poll. Backed by SQLite aggregates in
# storage.metrics_snapshot() for anything that must survive a restart.
# ----------------------------------------------------------------------
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

app = FastAPI(title="Stickblade Arena", docs_url=None, redoc_url=None,
              openapi_url=None)
# Allow the standalone Next.js frontend (Vercel) to call this API.
# Default to the production frontend + localhost dev; override with the
# CORS_ORIGINS env var (comma-separated). '*' is no longer the fallback so
# security scanners (and zealous redditors) don't ding us for it.
_DEFAULT_CORS = (
    "https://stickblade-arena.vercel.app,"
    "http://localhost:3000,"
    "http://127.0.0.1:3000"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", _DEFAULT_CORS).split(","),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # global per-IP request throttle + security headers on every response
    if request.url.path.startswith("/api"):
        try:
            security.check_request(request)
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
    response = await call_next(request)
    for k, v in security.SECURITY_HEADERS.items():
        response.headers[k] = v
    return response

print(f"[server] STICKBLADE ARENA v{VERSION} — weapons: sword/flail/bow, "
      f"modes: macro/joint, benchmark spec "
      f"{BENCH_SPEC_VERSION}/{SPEC_FINGERPRINT}")
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


# ------------------------------------------------------------- simulation
def run_simulation(mid):
    """Worker: run one headless match and store the replay (names hidden)."""
    import time as _t
    import pygame
    from main import Match
    from recorder import ReplayRecorder, RecordingFX

    m = store.get_match(mid)
    if m is None:
        raise RuntimeError(f"match row {mid} not found in storage")
    store.set_status(mid, "running")
    _live_init(mid)          # wait-screen listeners start seeing turn/quip updates
    _live_set(mid, queue_pos=0)  # by definition — we just dequeued this one
    try:
        if not pygame.get_init():
            pygame.init()
            pygame.display.set_mode((C.WIDTH, C.HEIGHT))
        sharp = m["sharp"].split(",")
        rec = ReplayRecorder(every=2)
        fx = RecordingFX(rec)

        # Random A↔green/B↔blue assignment for true blind voting. If the
        # caller didn't pre-pick (legacy match rows), pick now.
        import random as _r
        flip = MATCH_FLIP.pop(mid, None)
        if flip is None:
            flip = _r.random() < 0.5
        # Persist so the worker, reveal endpoint and replay all agree.
        store.set_flip(mid, flip)

        # If flipped, swap which model the engine assigns to fighter1 vs fighter2
        # (fighter1 is rendered GREEN on the left, fighter2 BLUE on the right).
        if flip:
            slot_left, slot_right = m["model_b"], m["model_a"]
        else:
            slot_left, slot_right = m["model_a"], m["model_b"]
        mm = MATCH_MODES.get(mid, {})
        # BYOK: consume the per-match key (if any) and pass into Match.
        # Popping here (not in finally) means we never re-read the key
        # even if the sim somehow got restarted for the same mid.
        byok = MATCH_API_KEYS.pop(mid, None)
        mode = mm.get("mode") or m.get("mode") or "macro"
        weapon = mm.get("weapon") or m.get("weapon") or "sword"
        arena = mm.get("arena") or m.get("arena") or "normal"
        blindfolded = mm.get("blindfolded") if "blindfolded" in mm else m.get("blindfolded", False)
        # ---- benchmark spec v1.0 knobs (recorded at request time) ----
        seed = mm.get("seed", None)
        if seed is None:
            seed = _row_get(m, "seed")
        match_length = mm.get("match_length") or _row_get(m, "match_length") or "full"
        fallback_policy = (mm.get("fallback_policy")
                           or _row_get(m, "fallback_policy") or "operational")
        match = Match(slot_left, slot_right, sharp, fx,
                      log_path=os.path.join(store.root, f"log_{mid}.json"),
                      mode=mode,
                      weapon=weapon,
                      arena=arena,
                      blindfolded=blindfolded,
                      api_key=byok,
                      seed=seed,
                      match_length=match_length,
                      fallback_policy=fallback_policy)
        # blind mode: hide model identity in the replay itself
        if m["blind"]:
            match.f1.name = match.b1.label = BLIND_NAMES["a"]
            match.f2.name = match.b2.label = BLIND_NAMES["b"]
        rec.attach(match)

        # ---------- pre-fight trash talk -----------------------------------
        # Each brain gets to throw one line at the OTHER model's display name.
        # Mocks return canned lines instantly; real models go through
        # chat_with_timeout (≤15s budget). Captured server-side, in canvas
        # coordinates, so the blind/flip stays consistent.
        try:
            from brains import pre_fight_quip
            name_left  = C.ARENA_MODELS.get(slot_left,  slot_left)
            name_right = C.ARENA_MODELS.get(slot_right, slot_right)
            weap = MATCH_MODES.get(mid, {}).get("weapon", "sword")
            quip_a = pre_fight_quip(match.b1, name_right, weapon=weap)
            quip_b = pre_fight_quip(match.b2, name_left,  weapon=weap)
            rec.set_quips(quip_a, quip_b)
            # Publish to the wait-screen the instant they're ready — these
            # generate BEFORE the physics loop starts, so users see the
            # trash-talk within ~5-15s instead of waiting the full 30-90s
            # for the replay JSON. Canvas-side keys (a/b), no model names.
            _live_set(mid, quips={"a": quip_a, "b": quip_b})
        except Exception as e:
            print(f"[quip] failed: {e}")
        # Budget SIM frames only — LLM thinking time must not eat the match.
        # Hard wall-clock ceiling protects against a hung brain.
        # Per-weapon deadline. Melee (sword/dagger/spear/flail) completes
        # in 60-120s for a normal 24-turn match with two real LLMs.
        # Bow matches are structurally slower: fighters fight at
        # ~450px distance (kite range), arrows miss more than melee
        # swings, and gravity + wind lead to more turns before a hit
        # lands. Live data: a 5-turn bow match hit the 3-min cap at
        # 74 vs 59 HP and got decided "on points" — user perceives
        # this as "match stopped mid-way" (see replay 1d0a73faf1d6,
        # 2026-07-28). Bumping bow to 5 min buys enough headroom for
        # a full 24-turn ranged exchange without breaking the queue-
        # DoS protection that 3-min was designed to prevent.
        # Was flat 3*60 (leftover debug value was 45*60, fixed in
        # 561a8ba).
        deadline_seconds = 5 * 60 if match.weapon == "bow" else 3 * 60
        deadline = _t.time() + deadline_seconds
        sim_frames = 0
        # Live wait-screen ticker: publish each turn to LIVE_STATE the moment
        # it finalizes (hits appended). Rule: match.log[i] is finalized once
        # match.log has grown past i (i.e. the NEXT turn started) OR the
        # match is over. Watching len() avoids racing with the PH_SIM ->
        # PH_THINK phase transition.
        last_published = 0
        _live_set(mid, total_turns=match.max_turns,
                  match_length=match.match_length,
                  seed=match.seed, started_at=_t.time())
        def _publish_finalized():
            nonlocal last_published
            # Everything before the last entry is guaranteed finalized.
            target = len(match.log) - 1
            if match.phase == Match.PH_OVER:
                target = len(match.log)   # include the very last entry too
            while last_published < target:
                _live_publish_turn(mid, match.log[last_published],
                                   match.f1, match.f2, flip)
                last_published += 1
        last_phase = None
        while match.phase != Match.PH_OVER and _t.time() < deadline \
                and sim_frames < 60 * 60 * 10:
            # User-initiated cancel (action-plan §13). Checked every frame
            # while we're waiting on inference; we can't interrupt an
            # in-flight HTTP call, but we never start the next turn.
            if store.is_cancelled(mid):
                store.set_status(mid, "error", "cancelled by user")
                _obs_bump("matches_cancelled")
                _live_set(mid, cancelled=True)
                return
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
            _publish_finalized()
            if match.phase != last_phase:
                # Progress-timeline signal for the wait screen: THINKING =
                # "models are deciding", SIM = "physics resolving". Cheap
                # (only writes on transition) and it's the difference between
                # a progress bar the user trusts and a spinner they don't.
                last_phase = match.phase
                _live_set(mid, phase=match.phase)
            if match.phase == Match.PH_THINK:
                # Publish what the user is actually waiting for: "prompting
                # the models", not a fake progress bar (action-plan §13).
                _live_set(mid, phase="prompting",
                          thinking_s=round(_t.time() - match._turn_started_at["1"], 1))
                _t.sleep(0.02)      # don't burn CPU while LLMs think
            else:
                _live_set(mid, phase="simulating")
                sim_frames += 1
        _publish_finalized()   # flush the final turn(s)
        for _ in range(90):
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
        if match.result is None:    # timeout/ceiling hit mid-match:
            match._finish()         # decide on points from current HP
        res = match.result
        if res["winner"] is None:
            side = "draw"
        else:
            side = "a" if res["winner"] == match.f1.name else "b"

        # ---------- post-fight commentary / roast --------------------------
        # We use whichever brain is more available (winner's by default). The
        # commentator gets the REAL model names; the public reveal only shows
        # it after the voter has cast their vote (handled by /api/vote/{id}).
        commentary = ""
        try:
            from brains import commentator_roast
            wname_real = (C.ARENA_MODELS.get(slot_left, slot_left)
                          if side == "a" else
                          C.ARENA_MODELS.get(slot_right, slot_right))
            lname_real = (C.ARENA_MODELS.get(slot_right, slot_right)
                          if side == "a" else
                          C.ARENA_MODELS.get(slot_left, slot_left))
            if side == "draw":
                wname_real = "Fighter A"; lname_real = "Fighter B"
            # Commentator = the WINNING brain (loser roasting themselves reads weird).
            commentator = match.b1 if side == "a" else match.b2
            commentary = commentator_roast(
                commentator, wname_real, lname_real, res["method"],
                res["turns"], match.weapon, sharp,
                final_hp=res.get("final_hp", {}))
        except Exception as e:
            print(f"[commentary] failed: {e}")

        replay = rec.build()
        prov = match.build_provenance()
        store.finish_match(mid, side, res["method"], res["turns"],
                           replay, commentary=commentary, provenance=prov)
        _obs_bump("matches_done")
        _obs_latency([prov.get("latency_ms_a"), prov.get("latency_ms_b")])
        if prov.get("fallback_used"):
            _obs_bump("matches_with_fallback")
    except Exception as e:
        import traceback
        traceback.print_exc()
        _obs_bump("matches_error")
        _obs_error(e, "run_simulation")
        store.set_status(mid, "error", _safe_err(e))
    finally:
        # Free the per-match config dict now that the sim is done. Without
        # this, MATCH_MODES grew unbounded for the life of the process
        # (~300 bytes/match, small but real on a long-running instance).
        # MATCH_FLIP already pops itself on line 139 above; this closes
        # the matching leak on the mode/weapon/arena side.
        MATCH_MODES.pop(mid, None)
        # Defensive: normally MATCH_API_KEYS[mid] is popped BEFORE Match()
        # is constructed. If an exception fired between the request handler
        # stashing the key and the worker consuming it, the entry would
        # linger — this keeps the map bounded regardless of failure path.
        MATCH_API_KEYS.pop(mid, None)
        # Give clients a beat to fetch the final tick before the state
        # disappears (their poll is every 1.5s; a 3s window covers it).
        # Then wipe LIVE_STATE so long-running processes don't accumulate.
        def _delayed_clear(_mid=mid):
            _t.sleep(3.0)
            _live_clear(_mid)
        threading.Thread(target=_delayed_clear, daemon=True).start()


def worker_loop():
    while True:
        mid = jobs.get()
        try:
            run_simulation(mid)
        except Exception as e:          # never let the worker die
            import traceback
            traceback.print_exc()
            try:
                store.set_status(mid, "error", _safe_err(e))
            except Exception:
                pass


threading.Thread(target=worker_loop, daemon=True).start()


# ===========================================================================
# Tournaments — single-elim brackets of 4 or 8 models.
# Each round runs every match SYNCHRONOUSLY through run_simulation so the
# bracket state machine is dead simple. Tournaments live in their own queue
# / worker so they don't starve the single-match queue.
# ===========================================================================
tournament_jobs: "queue.Queue[str]" = queue.Queue()


def _adjust_round_seeding(round_models):
    """Standard tournament bracket order so 1 vs N, 2 vs N-1, etc.
    For an 8-tournament: [s1,s2,s3,s4,s5,s6,s7,s8] -> [s1,s8,s4,s5,s3,s6,s2,s7].
    For a 4-tournament:  [s1,s2,s3,s4]            -> [s1,s4,s2,s3]."""
    n = len(round_models)
    if n == 8:
        order = [0, 7, 3, 4, 2, 5, 1, 6]
    elif n == 4:
        order = [0, 3, 1, 2]
    else:                                         # arbitrary even N
        order = []
        for i in range(n // 2):
            order += [i, n - 1 - i]
    return [round_models[i] for i in order]


def _run_one_tournament_match(t, round_n, slot, model_a, model_b):
    """Queue a single tournament fight via the normal storage/sim path,
    wait for it, then return the WINNER MODEL ID (or model_a on draw — by
    seed order)."""
    sharp = t["sharp"].split(",") if isinstance(t["sharp"], str) else list(t["sharp"])
    weapon = t.get("weapon") or "sword"
    t_mode = t.get("mode", "macro")
    t_arena = t.get("arena", "normal")
    mid = store.create_match(model_a, model_b, sharp, blind=True,
                             weapon=weapon, mode=t_mode, arena=t_arena)
    # Same arena / mode for the whole tournament — MATCH_MODES is the
    # in-memory routing dict for the sim worker; the persistent match
    # row now also carries mode/arena for correct elo cell attribution.
    MATCH_MODES[mid] = {"mode": t_mode, "weapon": weapon, "arena":  t_arena}
    # Tournaments are not user-voted, so we always use flip=False — the
    # bracket viewer cares about model identity, not blind canvas slots.
    MATCH_FLIP[mid] = False
    store.bind_tournament_match(t["id"], round_n, slot, mid)
    # Run the simulation INLINE in this worker thread (not via the single-
    # match queue) so we don't deadlock if the queue is busy.
    run_simulation(mid)
    m = store.get_match(mid)
    if m["status"] != "done":
        # error / timeout — seed-1 (higher seed) advances by default
        return model_a
    winner_side = m["winner_side"]
    if winner_side == "a":  return model_a
    if winner_side == "b":  return model_b
    return model_a   # draw → higher seed advances


def run_tournament(tid):
    """Play out a single-elim bracket. Updates progress after every match."""
    t = store.get_tournament(tid)
    if not t:
        return
    store.set_tournament_status(tid, "running")
    try:
        round_models = _adjust_round_seeding(t["models"])
        round_n = 1
        max_rounds = (t["size"]).bit_length() - 1  # 4 -> 2, 8 -> 3

        # Seed all R1 matches into the bracket table up-front so the UI can
        # render the empty bracket immediately.
        for slot in range(len(round_models) // 2):
            a = round_models[slot * 2]
            b = round_models[slot * 2 + 1]
            store.add_tournament_match(tid, round_n, slot, a, b)
        store.set_tournament_round(tid, round_n)

        while round_n <= max_rounds:
            winners = []
            for slot in range(len(round_models) // 2):
                a = round_models[slot * 2]
                b = round_models[slot * 2 + 1]
                print(f"[tournament {tid}] R{round_n} slot {slot}: {a} vs {b}")
                w = _run_one_tournament_match(t, round_n, slot, a, b)
                store.set_tournament_match_winner(tid, round_n, slot, w)
                winners.append(w)
            round_n += 1
            round_models = winners
            if round_n <= max_rounds:
                store.set_tournament_round(tid, round_n)
                # Seed the next round's pending matches into the table.
                for slot in range(len(round_models) // 2):
                    a = round_models[slot * 2]
                    b = round_models[slot * 2 + 1]
                    store.add_tournament_match(tid, round_n, slot, a, b)
        # round_models now has 1 entry — the champion
        champion = round_models[0]
        store.finish_tournament(tid, champion)
        print(f"[tournament {tid}] CHAMPION: {champion}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.set_tournament_status(tid, "error", _safe_err(e))


def tournament_worker_loop():
    while True:
        tid = tournament_jobs.get()
        try:
            run_tournament(tid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                store.set_tournament_status(tid, "error", _safe_err(e))
            except Exception:
                pass


threading.Thread(target=tournament_worker_loop, daemon=True).start()


# ------------------------------------------------------------- API
class MatchReq(BaseModel):
    model_a: str = Field(min_length=1, max_length=120)
    model_b: str = Field(min_length=1, max_length=120)
    sharp: list[str] = Field(default=["tip"], max_length=4)
    blind: bool = True
    mode: Literal["macro", "joint"] = "macro"
    weapon: Literal["sword", "dagger", "spear", "flail", "bow"] = "sword"
    arena: Literal["normal", "ice", "low_gravity"] = "normal"
    # Tier S #3: blindfolded variant. When true, build_state() strips
    # derived spatial hints (categorical enemy_is/enemy_height_relative/
    # facing_enemy + my_height/enemy_height/distance) so the model must
    # reason from raw torso/head coordinates. Separate elo cell — never
    # averaged with normal ratings.
    blindfolded: bool = False
    # BYOK — optional per-match OpenRouter API key. Sent from the user's
    # localStorage only when they've opted in via the "🔑 Use my key"
    # toggle. Server behavior:
    #   * NEVER logged, printed, or stored in the DB / replay JSON
    #   * lives only in-memory in MATCH_API_KEYS[mid] until the sim wraps
    #   * threaded into the Brain HTTP client headers, nowhere else
    #   * request body containing this field is not echoed back
    # Length cap is generous — OpenRouter keys are ~48 chars but we allow
    # up to 200 for BYOK from other proxies with longer prefixes.
    api_key: str | None = Field(default=None, max_length=200)
    # ---- benchmark spec v1.0 ----
    # sprint=4 / standard=12 / full=24 turns. Sprint exists so a first-time
    # user can watch a whole fight in ~20s instead of 60-90s.
    match_length: Literal["sprint", "standard", "full"] = "full"
    # Seed the RNG + scripted brains so the match is reproducible from the
    # stored action log. NULL = unseeded.
    seed: int | None = Field(default=None, ge=0, le=2 ** 31 - 1)
    # strict = any provider fallback makes the match ranking-ineligible
    # operational = fallback continues and is recorded (default)
    # demo = scripted/demo match, never ranked
    fallback_policy: Literal["strict", "operational", "demo"] = "operational"
    # Research batches (tools/run_calibration_batch.py) pin the canvas side
    # assignment so a seeded match is reproducible AND sides are balanced
    # by design. None (default) = random coin flip at queue time, as
    # before. False = model_a is green/left; True = model_a is blue/right.
    # This leaks nothing the requester did not already have: they chose
    # both models, and `blind=false` already reveals the sides.
    flip: bool | None = None


class VoteReq(BaseModel):
    """Multi-axis vote (action-plan §6).

    Only `choice` (the tactical vote) moves a rating. The other axes are
    collected so the dataset can separate "fought intelligently" from
    "was fun to watch" — a viewer may prefer a dramatic fighter who made
    worse decisions, and today that signal is silently discarded.
    """
    choice: Literal["a", "b", "draw"]
    execution: Literal["a", "b", "draw"] | None = None
    entertainment: Literal["a", "b", "draw"] | None = None
    deserved: Literal["a", "b", "draw"] | None = None
    confidence: int | None = Field(default=None, ge=1, le=5)
    # §6 expert track: self-declared evaluator tier. Not verified (there is
    # no identity here), which is exactly why it is *recorded and separable*
    # rather than used to weight or override anyone's vote.
    voter_tier: Literal["casual", "expert"] = "casual"


@app.get("/api/version")
def version():
    from weapons import WEAPONS
    from brains import PROMPT_VERSION
    # `prompt_version` is the evaluation-prompt schema version. Any semantic
    # change to build_state() / SYSTEM_PROMPT / ACTIONS / response format
    # bumps it. External dataset consumers, correlation studies, and paper
    # citations should pin their analysis to a specific prompt_version
    # because ratings across prompt versions are NOT comparable. See
    # AGENTS.md §PROMPT_VERSION_LOG for the change ledger.
    return {"version": VERSION, "prompt_version": PROMPT_VERSION,
            "weapons": WEAPONS,
            "modes": ["macro", "joint"], "replay_format": 2,
            "admin_bypass": bool(os.environ.get("ADMIN_TOKEN"))}


@app.get("/api/health")
def health():
    """Cheap liveness check — used by the frontend to distinguish between
    'backend asleep / down' vs 'backend up but a specific endpoint failed'.

    Reports:
      * up                — always true if this responds at all
      * has_openrouter    — OPENROUTER_API_KEY is configured
      * has_supabase      — Supabase storage configured (false = local SQLite)
      * queue             — pending match sims (helps users know to wait)
      * tournament_queue  — pending bracket runs
      * uptime_s          — process uptime in seconds (rough)
    """
    return {
        "up": True,
        "version": VERSION,
        "has_openrouter": bool(C.OPENROUTER_API_KEY),
        "has_groq":       bool(C.GROQ_API_KEY),
        "has_openai":     bool(C.OPENAI_API_KEY),
        "has_gemini":     bool(C.GEMINI_API_KEY),
        "has_supabase":   bool(os.environ.get("SUPABASE_URL")
                              and os.environ.get("SUPABASE_KEY")),
        "queue":            jobs.qsize(),
        "tournament_queue": tournament_jobs.qsize(),
    }


def _provider_of(mid: str) -> str:
    """Best-effort upstream provider for a roster id.

    Order: explicit host table in brains._PROVIDER_HOST (hand-curated from
    OpenRouter's per-model host attribution) -> the id's own prefix. Used by
    /api/models so the setup UI can say WHERE a turn is actually served from
    instead of making the user guess why one model is slow.
    """
    from brains import _PROVIDER_HOST
    if mid.startswith(("mock:", "bot:")):
        return "scripted"
    if mid.startswith("groq:"):
        return "groq"
    host = _PROVIDER_HOST.get(mid)
    if host:
        return host
    return "openrouter"


def _model_meta(mid: str, name: str) -> dict:
    """The setup-screen metadata the UI needs to set expectations.

    Every field is derived from something the backend already knows — no
    hand-maintained copy that can drift:
      provider     brains._PROVIDER_HOST / id prefix
      tier         ':free' suffix -> free, mock:/bot: -> no-api, else paid
      est_turn_s   brains._timeout_for(): the adaptive per-turn budget this
                   model actually gets (10s tiny / 18s mid / 25s reasoning).
                   Labelled in the UI as an upper bound per turn, not a
                   promise, because that is exactly what it is.
      reasoning    the same signal _timeout_for uses to widen the budget
      cooldown_s   seconds left on the 429 circuit breaker (0 = not throttled)
    """
    import time as _t
    from brains import _COOLDOWN, _timeout_for
    no_api = mid.startswith(("mock:", "bot:"))
    # The scripted baselines only speak macro: bots.py has no joint support,
    # so in a joint match they get driven by the macro executor. Say so at
    # the point of choice instead of letting the user find out mid-fight.
    # mock:* brains DO have a joint form (joint_mode.MockJointBrain).
    modes = ["macro"] if mid.startswith("bot:") else ["macro", "joint"]
    low = mid.lower()
    reasoning = any(t in low for t in ("reasoning", "thinking", "r1", "-pro"))
    return {
        "id": mid,
        "name": name,
        "provider": _provider_of(mid),
        "tier": "no-api" if no_api else ("free" if mid.endswith(":free") else "paid"),
        "est_turn_s": 0 if no_api else int(round(_timeout_for(mid))),
        "reasoning": bool(reasoning and not no_api),
        "no_api": no_api,
        "modes": modes,
        "cooldown_s": int(max(0.0, _COOLDOWN.get(mid, 0) - _t.time())),
    }


@app.get("/api/models")
def models():
    """Roster with per-model provider / latency / availability metadata.

    The frontend renders `provider · up to Ns per turn · available` next to
    each picker so a 60-90s match doesn't read as a hang, and so a model
    currently in 429 cooldown is visibly marked before the user picks it.
    """
    return [_model_meta(k, v) for k, v in C.ARENA_MODELS.items()]


# ----------------------------------------------------------------------
# Debug: recent brain errors + live OpenRouter self-test
# ----------------------------------------------------------------------
# Read-only diagnostics. No PII or secrets. Useful for live debugging the
# 'why does every match fall back?' class of bug without HF Spaces log
# access. The brain logger appends every retry/buddy failure into a tiny
# ring buffer so we can see WHAT actually went wrong server-side.
@app.get("/api/debug/brain_errors")
def debug_brain_errors():
    try:
        from brains import _RECENT_ERRORS  # ring buffer (deque)
        return {"count": len(_RECENT_ERRORS),
                "errors": list(_RECENT_ERRORS)}
    except Exception as e:
        return {"count": 0, "errors": [], "init_err": str(e)[:120]}


@app.get("/api/debug/cooldowns")
def debug_cooldowns():
    """Which models are currently in 429 cooldown, and for how many more
    seconds. Useful to see the circuit-breaker doing its thing live."""
    import time as _t
    try:
        from brains import _COOLDOWN
        now = _t.time()
        active = {m: round(ts - now, 1)
                  for m, ts in _COOLDOWN.items() if ts > now}
        return {"count": len(active), "cooldown_s_remaining": active}
    except Exception as e:
        return {"count": 0, "cooldown_s_remaining": {}, "init_err": str(e)[:120]}


@app.get("/api/debug/openrouter_ping")
def debug_openrouter_ping(model: str = "meta-llama/llama-3.3-70b-instruct:free"):
    """One-shot OpenRouter call with the simplest possible payload.
    Returns the raw status code + first 400 chars of response body so we
    can confirm: (a) the key works, (b) the model is reachable, (c) what
    error OR gives if it isn't. Bypasses every wrapper in brains.py.
    """
    if not C.OPENROUTER_API_KEY:
        return {"ok": False, "reason": "OPENROUTER_API_KEY not set"}
    if not _valid_model(model):
        return {"ok": False, "reason": "invalid model id"}
    import httpx
    try:
        r = httpx.post(
            f"{C.OPENROUTER_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {C.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://stickblade.arena",
                "X-Title": "Stickblade Arena debug",
            },
            json={
                "model": model,
                "messages": [{"role": "user",
                              "content": "Reply with exactly: PONG"}],
                "max_tokens": 16,
            },
            timeout=20,
        )
        body = r.text[:400]
        try:
            j = r.json()
            content = ((j.get("choices") or [{}])[0]
                       .get("message", {})
                       .get("content") or "")[:80]
        except Exception:
            content = ""
        return {"ok": r.status_code == 200 and bool(content),
                "status": r.status_code, "content": content,
                "body_preview": body}
    except Exception as e:
        return {"ok": False, "exception": str(e)[:200]}


@app.get("/api/benchmark/spec")
def benchmark_spec():
    """The frozen benchmark specification (action-plan §1).

    Returns the full ruleset plus a `fingerprint`. Two matches with
    different fingerprints are NOT comparable — dataset consumers should
    segment on it.
    """
    from benchmark import spec, fingerprint, MATCH_LENGTHS, FALLBACK_POLICIES
    doc = spec()
    return {**doc, "fingerprint": fingerprint(doc)}


@app.get("/api/integrity/{mid}")
def match_integrity(mid: str):
    """Replay Integrity audit for one match (action-plan §8).

    Verifies the replay is version-pinned, seeded, has a complete action
    log, and that recorded HP never increases. Returns per-check booleans
    so the UI can show exactly what passed.
    """
    _validate_id(mid)
    from benchmark import verify_replay
    r = store.get_replay(mid)
    if not r:
        raise HTTPException(404, "replay not ready")
    rep = verify_replay(r)
    # Adversarial / anti-gaming scan (action-plan §7): label matches won
    # through stalling, spamming, boundary camping or injected output
    # instead of treating a win as evidence of tactical skill.
    try:
        from anti_gaming import scan_replay
        rep["anti_gaming"] = scan_replay(r)
    except Exception as e:
        rep["anti_gaming"] = {"error": str(e)[:160]}
    m = store.get_match(mid) or {}
    rep["match_id"] = mid
    rep["ranking_eligible"] = bool(_row_get(m, "ranking_eligible", 1))
    rep["fallback_policy"] = _row_get(m, "fallback_policy")
    return rep


@app.get("/api/metrics")
def metrics():
    """Operational metrics (action-plan §19) — status page + alerting.

    Combines the durable SQLite rollup (storage.metrics_snapshot) with
    in-process counters (queue depth, uptime, recent latency ring).
    """
    try:
        snap = store.metrics_snapshot()
    except Exception as e:
        _obs_error(e, "metrics_snapshot")
        snap = {}
    with OBS_LOCK:
        lats = sorted(OBS["turn_latency_ms"])
        obs = {k: v for k, v in OBS.items() if k != "turn_latency_ms"}
        obs["provider_errors"] = dict(OBS["provider_errors"])
    if lats:
        obs["turn_latency_ms"] = {
            "n": len(lats),
            "p50": round(lats[len(lats) // 2], 1),
            "p95": round(lats[min(len(lats) - 1, int(0.95 * len(lats)))], 1),
            "max": round(lats[-1], 1),
        }
    return {
        "uptime_s": round(time.time() - OBS["started_at"], 1),
        "version": VERSION,
        "queue": {"matches": jobs.qsize(), "tournaments": tournament_jobs.qsize()},
        "storage": snap,
        "process": obs,
        # Thresholds the action plan asks us to alert on (§19). Surfaced
        # here so a status page can render green/amber/red without
        # hard-coding them client-side.
        "alert_thresholds": {
            "match_failure_rate": 0.05,
            "vote_failure_rate": 0.01,
            "fallback_rate": 0.25,
        },
    }


@app.get("/api/status")
def status_page_data():
    """Public status payload (action-plan §35): are we actually up?"""
    from benchmark import BENCHMARK_VERSION, PHYSICS_VERSION, SPEC_FINGERPRINT
    from brains import PROMPT_VERSION
    providers = {
        "openrouter": bool(C.OPENROUTER_API_KEY),
        "groq": bool(C.GROQ_API_KEY),
        "openai": bool(C.OPENAI_API_KEY),
        "gemini": bool(C.GEMINI_API_KEY),
    }
    try:
        snap = store.metrics_snapshot()
        rates = snap.get("rates", {})
    except Exception:
        rates = {}
    # Evidence level of the whole dataset, so a status page can show the
    # "rankings are scripted / insufficient" banner from a single call.
    try:
        _, dq = _quality_cell(None, None, None, None, None)
    except Exception:
        dq = None
    def _level(rate, warn, bad):
        if rate is None:
            return "unknown"
        return "down" if rate >= bad else ("degraded" if rate >= warn else "ok")
    # Replay storage: can the most recent finished match actually be
    # replayed? A database that says "done" while the replay blob is gone
    # is the failure mode users hit as "replay stuck loading".
    replay_state = "unknown"
    try:
        recent = store.recent_matches(limit=1)
        if not recent:
            replay_state = "ok (no matches yet)"
        else:
            replay_state = "ok" if store.get_replay(recent[0]["id"]) \
                else "degraded (latest replay missing)"
    except Exception as e:                       # noqa: BLE001
        replay_state = f"down ({_safe_err(e)[:60]})"
    # Degraded modes the operator should know about, in plain words.
    degraded = []
    if not any(providers.values()):
        degraded.append("no provider key configured — only scripted "
                        "(mock:/bot:) fighters can run; every match is a "
                        "scripted baseline")
    if dq and dq.get("evidence_level") == "scripted_only":
        degraded.append("rankings rest on scripted baselines only")
    elif dq and dq.get("evidence_level") == "insufficient_real":
        degraded.append("fewer than the board minimum of real-provider "
                        "ranked matches — rankings are exploratory")
    fb = rates.get("fallback")
    if fb is not None and fb >= 0.25:
        degraded.append(f"fallback rate {fb:.0%} (threshold 25%)")
    fr = rates.get("failure_24h")
    if fr is not None and fr >= 0.05:
        degraded.append(f"match failure rate {fr:.0%} in the last 24 h")
    if jobs.qsize() >= 5:
        degraded.append(f"queue depth {jobs.qsize()}")
    if not replay_state.startswith("ok"):
        degraded.append(f"replay storage: {replay_state}")
    with OBS_LOCK:
        last_error = OBS.get("last_error")
        last_error_at = OBS.get("last_error_at")
        provider_errors = dict(OBS.get("provider_errors") or {})
    overall = "ok"
    if any(v.startswith("down") for v in (replay_state,)) or \
            _level(fr, 0.05, 0.20) == "down":
        overall = "down"
    elif degraded:
        overall = "degraded"
    return {
        "status": overall,
        "version": VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "physics_version": PHYSICS_VERSION,
        "prompt_version": PROMPT_VERSION,
        "spec_fingerprint": SPEC_FINGERPRINT,
        "components": {
            "frontend": "ok",          # this response came through the API
            "backend": "ok",
            "providers": ("ok" if any(providers.values())
                          else "degraded (no provider key configured)"),
            "queue": ("ok" if jobs.qsize() < 5 else "degraded"),
            "database": "ok",
            "replays": replay_state,
        },
        "providers_configured": providers,
        "provider_errors": provider_errors,
        "queue_depth": jobs.qsize(),
        # Last incident = last recorded backend error (bounded text, URLs
        # and tokens scrubbed by _safe_err at the source). None = clean
        # since process start.
        "last_incident": ({"at": last_error_at, "what": last_error}
                          if last_error else None),
        "degraded_modes": degraded,
        "failure_rate_24h": rates.get("failure_24h"),
        "completion_rate": rates.get("completion"),
        "health": {
            "match_failures": _level(rates.get("failure_24h"), 0.05, 0.20),
            "fallbacks": _level(rates.get("fallback"), 0.25, 0.60),
        },
        "data_quality": ({"evidence_level": dq["evidence_level"],
                          "matches": dq["matches"],
                          "real_provider_matches": dq["real_provider_matches"],
                          "real_ranked_matches": dq["real_ranked_matches"],
                          "scripted_matches": dq["scripted_matches"],
                          "token_coverage": dq["token_coverage"],
                          "last_match_at": dq["last_match_at"],
                          "note": dq["note"]} if dq else None),
        "uptime_s": round(time.time() - OBS["started_at"], 1),
    }


@app.get("/api/weapons")
def weapons_list():
    """Weapon catalogue with empirical balance status (action-plan §9).

    `balance.status` is:
      * "balanced"    — mirrored bot batch is statistically indistinguishable
                        from a 50/50 split
      * "provisional" — point estimate is off 50/50 but the 95% CI still
                        contains it; widen the batch before claiming anything
      * "asymmetric"  — 95% CI excludes 50/50: the configuration itself
                        decides matches, so results are NOT a like-for-like
                        model comparison
    """
    from weapons import WEAPONS, WEAPON_ZONES, WEAPON_BALANCE
    return [{"id": w, "zones": WEAPON_ZONES[w],
             "balance": WEAPON_BALANCE.get(w, {"status": "unmeasured"})}
            for w in WEAPONS]


import re

_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$", re.I)

# Match / tournament ids are uuid.uuid4().hex[:12] — exactly 12 hex chars.
# Strictly validating the URL path param prevents path-traversal attacks
# (e.g. /api/replay/..%2F..%2Fetc%2Fpasswd) from ever reaching the storage
# layer that builds filesystem paths from the id.
_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _valid_model(mdl: str) -> bool:
    """Roster models, mock:* personalities, or a well-formed OpenRouter id."""
    if mdl in C.ARENA_MODELS or mdl in ("mock:duelist", "mock:berserker"):
        return True
    return bool(_MODEL_ID_RE.match(mdl)) and len(mdl) < 120


def _validate_id(id_: str) -> None:
    """Guard URL path params before they touch storage / filesystem."""
    if not _ID_RE.match(id_ or ""):
        raise HTTPException(400, "invalid id")


@app.post("/api/match")
def create_match(req: MatchReq, request: Request):
    # validate first so rejected requests don't consume the rate budget
    for mdl in (req.model_a, req.model_b):
        if not _valid_model(mdl):
            raise HTTPException(400, f"unknown model: {mdl}")
        security.check_model_spend_policy(mdl, C.ARENA_MODELS)
    security.check_match_allowed(request, jobs.qsize())
    from weapons import WEAPONS, WEAPON_ZONES
    if req.weapon not in WEAPONS:
        raise HTTPException(400, f"invalid weapon '{req.weapon}'. Valid weapons: {WEAPONS}")
    valid_zones = WEAPON_ZONES[req.weapon]
    if not req.sharp or not all(z in valid_zones for z in req.sharp):
        raise HTTPException(400, f"invalid sharp zones {req.sharp} for weapon '{req.weapon}'. Valid zones: {valid_zones}")
    weapon = req.weapon
    sharp = req.sharp
    mode = req.mode
    arena = req.arena
    blindfolded = bool(req.blindfolded)
    mid = store.create_match(req.model_a, req.model_b, sharp, req.blind,
                             weapon, mode=mode, arena=arena,
                             blindfolded=blindfolded,
                             seed=req.seed, match_length=req.match_length,
                             fallback_policy=req.fallback_policy)
    MATCH_MODES[mid] = {"mode": mode, "weapon": weapon, "arena": arena,
                        "blindfolded": blindfolded, "seed": req.seed,
                        "match_length": req.match_length,
                        "fallback_policy": req.fallback_policy}
    _obs_bump("matches_created")
    # BYOK: stash the user-supplied key in-memory for the worker to
    # consume. Basic sanity check (OR keys start with 'sk-or-') so we
    # don't accept obvious garbage; anything else with the sk- prefix
    # is passed through (OR occasionally accepts alt formats).
    if req.api_key:
        k = req.api_key.strip()
        if len(k) >= 20 and k.startswith("sk-"):
            MATCH_API_KEYS[mid] = k
    # Lock in the A↔green/B↔blue random assignment at queue time so even
    # the worker that picks up the job can't pre-leak which colored
    # ragdoll the user's picks correspond to.
    import random as _r
    MATCH_FLIP[mid] = bool(req.flip) if req.flip is not None \
        else _r.random() < 0.5
    jobs.put(mid)
    return {"match_id": mid, "status": "queued", "mode": mode,
            "weapon": weapon, "arena": arena,
            "match_length": req.match_length, "seed": req.seed,
            "fallback_policy": req.fallback_policy,
            "flip_pinned": req.flip is not None,
            "max_turns": max_turns_for(req.match_length)}


@app.get("/api/match/{mid}")
def match_status(mid: str):
    _validate_id(mid)
    m = store.get_match(mid)
    if not m:
        raise HTTPException(404, "no such match")
    out = {"match_id": mid, "status": m["status"], "sharp": m["sharp"],
           "voted": bool(m["voted"]), "error": m["error"]}
    # Live wait-screen data while queued/running: pre-fight quips (visible
    # ~5-15s in), queue position, and a spoiler-safe combat ticker. All
    # blind — canvas-side keys only, no model names — so we can safely
    # show these to the user BEFORE they cast their vote.
    # Benchmark provenance (spec v1.0) — always exposed, so a viewer can
    # see whether this match is a ranked, seeded, fully-LLM-controlled run.
    out["benchmark"] = {
        "benchmark_version": _row_get(m, "benchmark_version"),
        "physics_version": _row_get(m, "physics_version"),
        "prompt_version": _row_get(m, "prompt_version"),
        "spec_fingerprint": _row_get(m, "spec_fingerprint"),
        "seed": _row_get(m, "seed"),
        "match_length": _row_get(m, "match_length"),
        "max_turns": _row_get(m, "max_turns"),
        "fallback_policy": _row_get(m, "fallback_policy"),
        "ranking_eligible": bool(_row_get(m, "ranking_eligible", 1)),
        "fallback_used": bool(_row_get(m, "fallback_used", 0)),
    }
    if m["status"] in ("queued", "running"):
        snap = _live_snapshot(mid)
        if snap is None and m["status"] == "queued":
            # Queued but the worker hasn't dequeued us yet: compute
            # position from the FIFO's current size. Not exact under
            # concurrent enqueues, but plenty good enough for the UI's
            # "N ahead of you" text.
            snap = {"quips": None, "turn": 0, "log": [], "phase": "QUEUED",
                    "queue_pos": max(0, jobs.qsize() - 1)}
        if snap is not None:
            # Honest progress: what phase we're in, how far through the
            # turn budget we are, and how long we've been at it. No fake
            # percentage — an LLM call has no progress bar (§13).
            total = snap.get("total_turns") or max_turns_for(
                _row_get(m, "match_length"))
            turn = snap.get("turn") or 0
            started = snap.get("started_at")
            out["live"] = snap
            out["progress"] = {
                "phase": snap.get("phase") or ("queued"
                                               if m["status"] == "queued"
                                               else "starting"),
                "turn": turn,
                "total_turns": total,
                "percent": (round(100.0 * turn / total, 1)
                            if total else None),
                "elapsed_s": (round(time.time() - started, 1)
                              if started else None),
                "eta_s": None,
                "queue_pos": snap.get("queue_pos"),
                "cancelled": snap.get("cancelled", False),
            }
            # Rough ETA: measured per-turn cost so far x turns remaining.
            # Only shown once at least one turn has landed — an estimate
            # before that is a guess dressed up as data.
            if started and turn > 0:
                per_turn = (time.time() - started) / turn
                out["progress"]["eta_s"] = round(max(0.0, per_turn
                                                     * (total - turn)), 1)
    if m["status"] == "done":
        out.update({"engine_winner_side": m["winner_side"],
                    "method": m["method"], "turns": m["turns"]})
        fb_a = int(m.get("fallback_turns_a") or 0)
        fb_b = int(m.get("fallback_turns_b") or 0)
        t_turns = int(m.get("turns") or 0)
        out["evaluation_integrity"] = {
            "fully_llm_controlled": (fb_a == 0 and fb_b == 0),
            "fallback_turns_a": fb_a,
            "fallback_turns_b": fb_b,
            "total_turns": t_turns,
        }
        out["integrity"] = {
            "fallback_turns_a": int(_row_get(m, "fallback_turns_a") or 0),
            "fallback_turns_b": int(_row_get(m, "fallback_turns_b") or 0),
            "invalid_actions_a": int(_row_get(m, "invalid_actions_a") or 0),
            "invalid_actions_b": int(_row_get(m, "invalid_actions_b") or 0),
            "latency_ms_a": _row_get(m, "latency_ms_a"),
            "latency_ms_b": _row_get(m, "latency_ms_b"),
            "model_used_a": _row_get(m, "model_used_a"),
            "model_used_b": _row_get(m, "model_used_b"),
            "provider_used_a": _row_get(m, "provider_used_a"),
            "provider_used_b": _row_get(m, "provider_used_b"),
            "completed_turns": int(_row_get(m, "turns") or 0),
        }
        if not m["blind"] or m["voted"]:
            # Expose BOTH axes:
            #   * model_a / model_b        = user's original pick order (Slot 1/2)
            #   * canvas_a_model / canvas_b_model = who actually rendered as
            #     green (Fighter A) vs blue (Fighter B) after the coinflip
            # The shared /replay?id=... page reads canvas_* first because the
            # user is watching the canvas, not the original pick order. Without
            # this, ~50%% of shared reveals show the wrong model as the winner.
            flip = bool(m.get("flip"))
            canvas_a = m["model_b"] if flip else m["model_a"]
            canvas_b = m["model_a"] if flip else m["model_b"]
            names = {mm: C.ARENA_MODELS.get(mm, mm)
                     for mm in {m["model_a"], m["model_b"], canvas_a, canvas_b}}
            out.update({"model_a": m["model_a"], "model_b": m["model_b"],
                        "canvas_a_model": canvas_a,
                        "canvas_b_model": canvas_b,
                        "names": names, "flip": flip})
    return out


@app.post("/api/match/{mid}/cancel")
def cancel_match(mid: str):
    """Cancel a queued/running match (action-plan §13).

    Sets a flag the worker polls between turns; we can't abort an API call
    that's already in flight, so the match stops at the next turn
    boundary. Finished matches are immutable — they're published data.
    """
    _validate_id(mid)
    m = store.get_match(mid)
    if not m:
        raise HTTPException(404, "no such match")
    if m["status"] in ("done", "error"):
        return {"cancelled": False, "reason": f"match already {m['status']}"}
    try:
        ok = store.cancel_match(mid)
    except AttributeError:      # storage backend without cancel support
        raise HTTPException(501, "cancel not supported by this backend")
    return {"cancelled": bool(ok), "status": "error",
            "detail": "stopping at the next turn boundary"}


@app.get("/api/replay/{mid}")
def replay(mid: str):
    _validate_id(mid)
    r = store.get_replay(mid)
    if not r:
        _obs_bump("replay_errors")
        raise HTTPException(404, "replay not ready")
    _obs_bump("replays_served")
    return JSONResponse(r)


@app.post("/api/vote/{mid}")
def vote(mid: str, req: VoteReq, request: Request):
    """Cast a vote. `choice` is the TACTICAL vote and is the only axis
    that moves a rating; execution / entertainment / deserved are stored
    alongside it for research use (action-plan §6)."""
    _validate_id(mid)
    security.check_vote_allowed(request)
    if req.choice not in ("a", "b", "draw"):
        raise HTTPException(400, "choice must be a|b|draw")
    axes = {"execution": req.execution,
            "entertainment": req.entertainment,
            "deserved": req.deserved}
    try:
        res = store.record_vote(mid, req.choice, axes=axes,
                                confidence=req.confidence,
                                voter_tier=req.voter_tier)
    except TypeError:
        # Drop-in storage backends that haven't implemented multi-axis
        # votes yet: fall back to the tactical vote only rather than
        # losing the vote entirely.
        res = store.record_vote(mid, req.choice)
    if res is None:
        _obs_bump("vote_errors")
        raise HTTPException(400, "match not finished or not found")
    _obs_bump("votes_recorded")
    # add display names — for both the user's original pick axis AND the
    # canvas (green/blue) axis so the UI can say "Fighter A (green) was X".
    all_models = {res["model_a"], res["model_b"],
                  res.get("canvas_a_model"), res.get("canvas_b_model")}
    res["names"] = {m: C.ARENA_MODELS.get(m, m) for m in all_models if m}
    return res


def _wilson_ci(wins: int, losses: int, draws: int, z: float = 1.96):
    """95% Wilson score confidence interval for the true win-rate.

    Why Wilson (not bootstrap) for leaderboard uncertainty:
      * Closed-form, O(1) per row — cheap on every leaderboard load.
      * Handles small N gracefully (Wald normal-approx implodes at N<30).
      * Statistically defensible; standard in eval papers (e.g. LMSys
        Arena's leaderboard error bars).

    Draws are counted as half-wins per Elo convention (a draw between
    equally-rated opponents contributes 0.5 to each). This matches the
    K-factor update in storage._get_elo(): sa = 0.5 for draws.

    Returns:
        (rate, lo, hi) — point estimate + Wilson [lo, hi] on true rate,
        all in [0, 1]. When N==0 returns (None, None, None).

    Elo uncertainty from win-rate uncertainty: for a fixed opponent-pool
    average rating R_opp, Elo(p) = R_opp + 400 * log10(p/(1-p)). So the
    [lo, hi] on p maps to [Elo(lo), Elo(hi)] on rating. We don't do this
    mapping here — instead we expose the raw win-rate CI in the payload
    and let the frontend format it as ±X on Elo using its own choice of
    R_opp (usually the leaderboard median).
    """
    n = wins + losses + draws
    if n == 0:
        return None, None, None
    # Draws count as half-wins for both sides (Elo convention).
    effective_wins = wins + 0.5 * draws
    p_hat = effective_wins / n
    denom = 1.0 + (z * z) / n
    center = (p_hat + (z * z) / (2 * n)) / denom
    half = (z / denom) * ((p_hat * (1 - p_hat) / n
                           + (z * z) / (4 * n * n)) ** 0.5)
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return p_hat, lo, hi


# ----------------------------------------------------------------------
# Data-quality labels (next-step priority 2). Every ranking row states
# what kind of evidence produced it — scripted baseline, mixed provider,
# or real provider — plus fallback / missing-token counts, last-updated
# date and benchmark version. A rating without that context reads as a
# model result even when nothing but scripted brains ever played.
# ----------------------------------------------------------------------
# Keys copied from the per-model rollup onto each ranking row. The full
# record stays available at /api/data_quality.
_DQ_ROW_KEYS = (
    "evidence", "evidence_label", "status", "status_label",
    "real_provider_matches", "mixed_provider_matches", "scripted_matches",
    "ranking_eligible_matches", "real_ranked_matches", "fallback_matches",
    "token_missing_matches", "last_match_at", "benchmark_versions",
)


def _quality_cell(sharp, weapon, mode, arena, blindfolded):
    """(per-model rollup, board summary) for one leaderboard cell.

    Never raises: a storage backend without quality_rows() (or a failed
    query) yields empty labels rather than a 500 on the leaderboard.
    """
    import data_quality as DQ
    try:
        rows = store.quality_rows(sharp, weapon, mode, arena, blindfolded)
    except Exception as e:                      # noqa: BLE001
        print(f"[data_quality] unavailable: {e}")
        rows = []
    return DQ.rollup_models(rows), DQ.summary(rows)


def _label_rows(rows, rollup):
    import data_quality as DQ
    for r in rows:
        rec = DQ.model_record(rollup, r.get("model"))
        r["data_quality"] = {k: rec.get(k) for k in _DQ_ROW_KEYS}
    return rows


@app.get("/api/data_quality")
def data_quality(sharp: str | None = None, weapon: str | None = None,
                 mode: str | None = None, arena: str | None = None,
                 blindfolded: bool | None = None):
    """Data-quality report for a leaderboard cell (next-step priority 2).

    Distinguishes *infrastructure validated* from *model conclusions
    validated*. `summary.evidence_level` is what the UI banner reads:

        scripted_only      no real-provider match exists in this cell
        insufficient_real  some exist, but too few are ranking-eligible
        real               enough real-provider ranked matches to discuss
                           model behaviour (pairs still need to separate)

    `models` carries, per model: matches by evidence class, ranking-
    eligible count, fallback count, missing-token count, last match date
    and the benchmark versions it played under. Declared bots are labelled
    `reference_baseline`; a requested model whose slot was served by a
    scripted stand-in counts as scripted here, because the label describes
    the decisions the data actually contains.
    """
    from weapons import WEAPONS
    if weapon is not None and weapon not in WEAPONS:
        raise HTTPException(400, f"weapon must be one of {WEAPONS}")
    if mode is not None and mode not in ("macro", "joint"):
        raise HTTPException(400, "mode must be 'macro' or 'joint'")
    if arena is not None and arena not in ("normal", "ice", "low_gravity"):
        raise HTTPException(400, "arena must be 'normal', 'ice' or 'low_gravity'")
    import data_quality as DQ
    rollup, summ = _quality_cell(sharp, weapon, mode, arena, blindfolded)
    models = []
    for rec in sorted(rollup.values(), key=lambda m: -m["matches"]):
        rec = dict(rec)
        rec["name"] = C.ARENA_MODELS.get(rec["model"], rec["model"])
        models.append(rec)
    from brains import PROMPT_VERSION
    return {"benchmark_version": BENCHMARK_VERSION,
            "physics_version": PHYSICS_SPEC_VERSION,
            "prompt_version": PROMPT_VERSION,
            "spec_fingerprint": SPEC_FINGERPRINT,
            "generated_at": time.time(),
            "labels": {"evidence": DQ.EVIDENCE_LABELS,
                       "status": DQ.STATUS_LABELS},
            "summary": summ,
            "models": models}


@app.get("/api/leaderboard")
def leaderboard(sharp: str | None = None, weapon: str | None = None,
                mode: str | None = None, arena: str | None = None,
                blindfolded: bool | None = None):
    """Leaderboard rows with Wilson-score 95%% CI on win-rate + prompt
    version pinning. See _wilson_ci() for statistical rationale.

    Filterable by sharp / weapon / mode / arena / blindfolded. Ratings
    segment per (model, sharp, weapon, mode, arena, blindfolded) —
    Tier-S #3 added blindfolded as the 5th eval axis. Blindfolded
    matches strip derived spatial hints from the state, forcing raw-
    coord reasoning — they're literally a different question and
    averaging with normal-mode Elo would be dishonest.

    Each row includes:
      * rating         — current Elo (K=32, start=1000)
      * wins/losses/draws — vote counts per cell
      * n              — total matches (convenience: w+l+d)
      * win_rate       — point estimate, in [0, 1]  (None when N=0)
      * win_rate_lo    — 95%% Wilson lower bound    (None when N=0)
      * win_rate_hi    — 95%% Wilson upper bound    (None when N=0)
      * prompt_version — the eval prompt schema that produced this Elo
    """
    from brains import PROMPT_VERSION
    from weapons import WEAPONS
    # Validate the enum-ish filters — no need to hit the storage layer
    # with a garbage value, and 400ing bad input is cheaper than a wide
    # empty result set later.
    if weapon is not None and weapon not in WEAPONS:
        raise HTTPException(400, f"weapon must be one of {WEAPONS}")
    if mode is not None and mode not in ("macro", "joint"):
        raise HTTPException(400, "mode must be 'macro' or 'joint'")
    if arena is not None and arena not in ("normal", "ice", "low_gravity"):
        raise HTTPException(400, "arena must be 'normal', 'ice', or 'low_gravity'")
    rows = store.leaderboard(sharp, weapon, mode, arena, blindfolded)
    for r in rows:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
        r["rating"] = round(r["rating"], 1)
        w, l, d = int(r.get("wins", 0)), int(r.get("losses", 0)), int(r.get("draws", 0))
        n = w + l + d
        p_hat, lo, hi = _wilson_ci(w, l, d)
        r["n"] = n
        r["win_rate"]    = round(p_hat, 4) if p_hat is not None else None
        r["win_rate_lo"] = round(lo, 4)    if lo    is not None else None
        r["win_rate_hi"] = round(hi, 4)    if hi    is not None else None
        # Pin every row to the current prompt schema. When we bump
        # PROMPT_VERSION in future the leaderboard will need a soft
        # cutover (annotate old rows) or a hard reset — but at that
        # point every row here was earned under the CURRENT version,
        # so tagging with today's version is truthful.
        r["prompt_version"] = PROMPT_VERSION
        # benchmark spec v1.0: every rating row states which ruleset it
        # was earned under and whether it has enough data to be ranked.
        # `provisional` is what the UI greys out; `eligible` is the hard
        # floor below which we refuse to call it a ranking at all.
        r["benchmark_version"] = BENCH_SPEC_VERSION
        r["physics_version"] = PHYSICS_SPEC_VERSION
        r["provisional"] = n < 10
        r["eligible"] = n >= 5
    # Data-quality labels: who actually made the decisions behind this
    # rating (scripted / mixed / real provider), fallback and missing-token
    # counts, last match date. See /api/data_quality.
    rollup, _ = _quality_cell(sharp, weapon, mode, arena, blindfolded)
    return _label_rows(rows, rollup)


@app.get("/api/head_to_head")
def head_to_head(a: str, b: str):
    """Order-insensitive H2H record between two model ids.
    Powers the wait-screen 'previous duels' card. Only shows VOTED matches
    (the storage layer filters status=done — Elo isn't touched until vote,
    but we still count both winner and unvoted; the frontend just hides
    the card when total==0). No PII, no blind leakage — the user picked
    these two models themselves so their identities are already known."""
    for mdl in (a, b):
        if not _valid_model(mdl):
            raise HTTPException(400, f"unknown model: {mdl}")
    h2h = store.head_to_head(a, b)
    h2h["a_model"] = a
    h2h["b_model"] = b
    h2h["a_name"]  = C.ARENA_MODELS.get(a, a)
    h2h["b_name"]  = C.ARENA_MODELS.get(b, b)
    return h2h


# ============================================================
# Tournaments API
# ============================================================
class TournamentReq(BaseModel):
    name:   str = Field(default="Untitled Bracket", min_length=1, max_length=80)
    models: list[str] = Field(min_length=4, max_length=8)
    weapon: Literal["sword", "dagger", "spear", "flail", "bow"] = "sword"
    sharp:  list[str] = Field(default=["tip"], max_length=4)
    arena:  Literal["normal", "ice", "low_gravity"] = "normal"
    mode:   Literal["macro", "joint"] = "macro"


@app.post("/api/tournament")
def create_tournament(req: TournamentReq, request: Request):
    # validate inputs (same gates as single-match)
    for mdl in req.models:
        if not _valid_model(mdl):
            raise HTTPException(400, f"unknown model: {mdl}")
        security.check_model_spend_policy(mdl, C.ARENA_MODELS)
    security.check_match_allowed(request, jobs.qsize())

    # only 4- or 8-model brackets supported (clean single-elim)
    if len(req.models) not in (4, 8):
        raise HTTPException(400, "tournament size must be 4 or 8 models")
    if len(set(req.models)) != len(req.models):
        raise HTTPException(400, "duplicate model entries not allowed")

    from weapons import WEAPONS, WEAPON_ZONES
    if req.weapon not in WEAPONS:
        raise HTTPException(400, f"invalid weapon '{req.weapon}'. Valid weapons: {WEAPONS}")
    valid_zones = WEAPON_ZONES[req.weapon]
    if not req.sharp or not all(z in valid_zones for z in req.sharp):
        raise HTTPException(400, f"invalid sharp zones {req.sharp} for weapon '{req.weapon}'. Valid zones: {valid_zones}")
    weapon = req.weapon
    sharp  = req.sharp
    arena  = req.arena
    mode   = req.mode

    tid = store.create_tournament(req.name, req.models, weapon, sharp,
                                  arena, mode)
    tournament_jobs.put(tid)
    return {"tournament_id": tid, "status": "queued",
            "size": len(req.models), "weapon": weapon, "arena": arena}


@app.get("/api/tournament/{tid}")
def tournament_status(tid: str):
    _validate_id(tid)
    t = store.get_tournament(tid)
    if not t:
        raise HTTPException(404, "no such tournament")
    # decorate with display names
    t["model_names"] = {m: C.ARENA_MODELS.get(m, m) for m in t["models"]}
    return t


@app.get("/api/tournaments")
def list_tournaments():
    rows = store.recent_tournaments()
    for r in rows:
        if r.get("winner_model"):
            r["winner_name"] = C.ARENA_MODELS.get(r["winner_model"],
                                                  r["winner_model"])
    return rows


@app.get("/api/leaderboard/objective")
def leaderboard_objective(sharp: str | None = None, weapon: str | None = None,
                          mode: str | None = None, arena: str | None = None,
                          blindfolded: bool | None = None):
    """Objective-skill leaderboard — per-model rollup of proxy metrics
    (damage_per_turn, hit_rate, fallback_rate, avg_distance) computed
    from the raw match event stream. Independent of human votes; every
    completed match contributes regardless of vote status.

    Powers the 'Objective Skill' tab alongside 'Perceived Skill' (the
    human-vote Elo leaderboard). Decouples ranking from the small-N
    vote pool — a model with 100 matches and 5 votes still has full
    objective stats.

    Filters mirror /api/leaderboard (same 5 axes). Blindfolded matches
    have their own objective leaderboard for the same reason they have
    their own Elo cell: they're literally a different question.

    Rows sorted by damage_per_turn desc by default; frontend can re-sort.
    """
    from weapons import WEAPONS
    if weapon is not None and weapon not in WEAPONS:
        raise HTTPException(400, f"weapon must be one of {WEAPONS}")
    if mode is not None and mode not in ("macro", "joint"):
        raise HTTPException(400, "mode must be 'macro' or 'joint'")
    if arena is not None and arena not in ("normal", "ice", "low_gravity"):
        raise HTTPException(400, "arena must be 'normal', 'ice', or 'low_gravity'")
    rows = store.objective_leaderboard(sharp, weapon, mode, arena, blindfolded)
    for r in rows:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
    rollup, _ = _quality_cell(sharp, weapon, mode, arena, blindfolded)
    return _label_rows(rows, rollup)


@app.get("/api/leaderboard/bradley_terry")
def leaderboard_bradley_terry(sharp: str | None = None,
                              weapon: str | None = None,
                              mode: str | None = None,
                              arena: str | None = None,
                              blindfolded: bool | None = None,
                              bootstraps: int = 200,
                              tier: str | None = None):
    """Uncertainty-aware ranking (action-plan §5).

    Elo is a good live scoreboard and a weak scientific claim: it has no
    confidence interval, it is order-dependent, and it cannot say "we don't
    know yet". This endpoint fits a Bradley-Terry model (with Davidson ties)
    by maximum likelihood over ALL voted matches in the cell at once, and
    reports a bootstrap 95% interval per model.

    Because it refits the whole match set rather than updating sequentially,
    two models with the same record get the same rating regardless of the
    order the matches happened to arrive in — which Elo does not guarantee.

    Read the output as: `rating` is the point estimate on an Elo-like scale
    (only for readability — it is NOT Elo), and [ci_low, ci_high] is where
    the model plausibly sits. Overlapping intervals mean "not separable",
    and the UI says so rather than implying an ordering that isn't there.
    """
    from ratings import fit_with_ci, preference_pairs_from_votes
    from weapons import WEAPONS
    if weapon is not None and weapon not in WEAPONS:
        raise HTTPException(400, f"weapon must be one of {WEAPONS}")
    if mode is not None and mode not in ("macro", "joint"):
        raise HTTPException(400, "mode must be 'macro' or 'joint'")
    if arena is not None and arena not in ("normal", "ice", "low_gravity"):
        raise HTTPException(400, "arena must be 'normal', 'ice' or 'low_gravity'")
    if tier is not None and tier not in ("casual", "expert"):
        raise HTTPException(400, "tier must be 'casual' or 'expert'")
    bootstraps = max(0, min(int(bootstraps or 0), 1000))

    rows = store.preference_pairs(sharp, weapon, mode, arena, blindfolded,
                                  tier)
    pairs = preference_pairs_from_votes(rows)
    out = fit_with_ci(pairs, bootstraps=bootstraps)
    for r in out:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
    rollup, summ = _quality_cell(sharp, weapon, mode, arena, blindfolded)
    _label_rows(out, rollup)
    return {"benchmark_version": BENCHMARK_VERSION,
            "model": "bradley-terry-davidson",
            "scale": "elo-like (400/ln10 per logit, centred on 1000)",
            "comparisons": len(pairs),
            "bootstraps": bootstraps,
            "voter_tier": tier or "all",
            "data_quality": summ,
            "rows": out}


@app.get("/api/model_stats")
def model_stats(sharp: str | None = None, weapon: str | None = None,
                mode: str | None = None, arena: str | None = None,
                blindfolded: bool | None = None):
    """Full per-model metric table (action-plan §5).

    Every number the plan asks to publish beside a rating: win rate,
    human preference rate, damage per turn, hit rate, lethal rate,
    survival rate, timeout rate, invalid-action rate, decision latency,
    fallback rate, and sample size. `/api/leaderboard/objective` remains as
    the smaller tab the UI already renders.
    """
    from weapons import WEAPONS
    if weapon is not None and weapon not in WEAPONS:
        raise HTTPException(400, f"weapon must be one of {WEAPONS}")
    if mode is not None and mode not in ("macro", "joint"):
        raise HTTPException(400, "mode must be 'macro' or 'joint'")
    if arena is not None and arena not in ("normal", "ice", "low_gravity"):
        raise HTTPException(400, "arena must be 'normal', 'ice' or 'low_gravity'")
    rows = store.model_stats(sharp, weapon, mode, arena, blindfolded)
    for r in rows:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
    rollup, summ = _quality_cell(sharp, weapon, mode, arena, blindfolded)
    _label_rows(rows, rollup)
    return {"benchmark_version": BENCHMARK_VERSION,
            "data_quality": summ, "rows": rows}


@app.get("/api/events")
def list_events(past: int = 3, future: int = 4, bootstraps: int = 100):
    """Recurring event calendar + archive of decided champions (§31).

    The schedule is derived from `stickblade/events.py` — there is no table
    to fall out of sync and no cron that can silently stop. Standings come
    from the same Bradley-Terry estimator as the leaderboard, and an event
    with too little data reports *why* it is undecided rather than naming a
    winner anyway.
    """
    from events import calendar as _calendar, champions as _champions
    past = max(0, min(int(past or 0), 24))
    future = max(0, min(int(future or 0), 24))
    bootstraps = max(0, min(int(bootstraps or 0), 500))
    cal = _calendar(store, past=past, future=future, bootstraps=bootstraps)
    return {"benchmark_version": BENCHMARK_VERSION,
            "events": cal,
            "champions": _champions(store, bootstraps=min(bootstraps, 100))}


@app.get("/api/events/{event_id}")
def event_detail(event_id: str, past: int = 6, bootstraps: int = 200):
    """One event's windows and standings (§31)."""
    from events import EVENTS, calendar as _calendar
    if not any(e["id"] == event_id for e in EVENTS):
        raise HTTPException(404, f"unknown event: {event_id}")
    past = max(0, min(int(past or 0), 60))
    bootstraps = max(0, min(int(bootstraps or 0), 500))
    cal = _calendar(store, past=past, future=1, bootstraps=bootstraps)
    windows = [c for c in cal if c["event_id"] == event_id]
    meta = next(e for e in EVENTS if e["id"] == event_id)
    return {"benchmark_version": BENCHMARK_VERSION,
            "event": {k: v for k, v in meta.items() if k != "cadence"},
            "windows": windows}


@app.get("/api/costs")
def costs(days: int = 30):
    """Measured operating cost + budget state (action-plan §33).

    Tokens come from the providers' own usage blocks, accumulated across
    retries and buddy fallbacks, so a match that degraded still reports
    what it cost. If any billable match reported no usage, `complete` is
    false and every figure is a **lower bound** — unreported is never
    treated as free.
    """
    from costs import rollup, budget_state, budgets, ACCESS_TIERS
    import time as _time
    days = max(1, min(int(days or 30), 365))
    # Filtered in SQL: a cost endpoint that loads the whole match table is
    # exactly the kind of self-inflicted load this project keeps auditing.
    rows = store.export_matches(since=_time.time() - days * 86400,
                                limit=50000, include_votes=False)
    full = rollup(rows, days=days)
    today = rollup(rows, days=1)
    month = rollup(rows, days=30)
    return {"benchmark_version": BENCHMARK_VERSION,
            "window": full,
            "budget": budget_state(today["usd_total"], month["usd_total"]),
            "limits": budgets(),
            # §34: the access model is published, not implied. The core
            # benchmark is never paywalled; what would be metered is
            # volume and hosting.
            "access_tiers": ACCESS_TIERS}


@app.get("/api/export")
def export_matches(
    since: float | None = None,
    until: float | None = None,
    limit: int = 10000,
    fmt: str = "json",
    include_votes: bool = True,
):
    """Tier-A #3: bulk dataset export. Powers the eventual daily HF
    Datasets snapshot (huggingface.co/datasets/Pioneer37/stickblade-
    matches). Also directly usable by researchers who want to grab a
    reproducible slice for offline analysis.

    Query params:
      * `since` / `until` — unix epoch bounds on matches.created.
        Omit for unbounded. Both bounded = closed interval.
      * `limit` — hard cap [1, 50000]. Default 10000.
      * `fmt` — 'json' (default: {matches:[...], count, exported_at,
        prompt_version, since, until}) OR 'jsonl' (one match per
        line, streaming-friendly, ideal for HF Datasets ingestion).
      * `include_votes` — attach anonymous vote objects per match.
        Default true. Set false for lighter payload.

    Deliberately excludes replay JSON blobs (per-match multi-MB;
    fetch individually via /api/replay/{mid} using the ids surfaced
    here). Includes: model_a/b, sharp, weapon, mode, arena,
    blindfolded, status, winner_side, method, turns, commentary,
    proxy metrics (damage/hits/fallback/avg_distance per side),
    prompt_version tag.

    No PII: no IPs, no user ids, no BYOK residue. Votes are
    anonymous (id + match_id + created + choice + the optional
    execution/entertainment/deserved axes + self-reported confidence +
    self-declared voter_tier — nothing identifying). Same
    exposure profile as /api/leaderboard.

    Rate-limited by the same middleware as other endpoints. If
    someone hammers it we'll add a dedicated slower bucket, not
    yet needed at 200 monthly visitors.
    """
    lim = max(1, min(int(limit or 10000), 50000))
    if fmt not in ("json", "jsonl", "csv"):
        raise HTTPException(400, "fmt must be 'json', 'jsonl', or 'csv'")
    rows = store.export_matches(since=since, until=until, limit=lim,
                                include_votes=bool(include_votes))
    _obs_bump("export_rows", len(rows))
    # Data-quality label per row (next-step priority 2/3): downstream
    # analysts must be able to filter scripted-baseline rows out without
    # re-deriving our provider heuristics.
    import data_quality as DQ
    for r in rows:
        r["evidence"] = DQ.evidence_class(r)
    if fmt == "csv":
        # Flat analysis-oriented export (action-plan §27). Every scalar
        # match column becomes a column; nested vote objects are
        # collapsed to counts so the file opens cleanly in pandas/Excel.
        import csv as _csv
        import io as _io
        from fastapi.responses import PlainTextResponse
        cols = [
            "id", "created", "benchmark_version", "physics_version",
            "prompt_version", "spec_fingerprint", "seed", "match_length",
            "max_turns", "fallback_policy", "model_a", "model_b",
            "model_used_a", "model_used_b", "provider_used_a",
            "provider_used_b", "fallback_used", "latency_ms_a",
            "latency_ms_b", "invalid_actions_a", "invalid_actions_b",
            "ranking_eligible", "sharp", "weapon", "mode", "arena",
            "blindfolded", "status", "winner_side", "method", "turns",
            "damage_dealt_a", "damage_dealt_b", "hits_landed_a",
            "hits_landed_b", "hits_attempted_a", "hits_attempted_b",
            "fallback_turns_a", "fallback_turns_b", "avg_distance",
            "voted", "flip", "votes_a", "votes_b", "votes_draw",
            "votes_total", "votes_expert", "votes_casual",
            # §33: billed tokens, so anyone can re-derive our cost numbers
            # instead of taking them on trust.
            "prompt_tokens_a", "completion_tokens_a", "prompt_tokens_b",
            "completion_tokens_b", "api_calls_a", "api_calls_b",
            # data-quality evidence class: real_provider | mixed_provider |
            # scripted_baseline (who actually decided, not who was asked)
            "evidence",
        ]
        buf = _io.StringIO()
        w = _csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore",
                            restval="")
        w.writeheader()
        for r in rows:
            votes = r.get("votes") or []
            r["votes_a"] = sum(1 for v in votes if v.get("choice") == "a")
            r["votes_b"] = sum(1 for v in votes if v.get("choice") == "b")
            r["votes_draw"] = sum(1 for v in votes if v.get("choice") == "draw")
            r["votes_total"] = len(votes)
            # §6: expert and casual votes travel as separate columns, not
            # one pooled total — otherwise a downstream analyst cannot
            # reproduce either tier's leaderboard.
            r["votes_expert"] = sum(
                1 for v in votes
                if (v.get("voter_tier") or "casual") == "expert")
            r["votes_casual"] = r["votes_total"] - r["votes_expert"]
            w.writerow(r)
        return PlainTextResponse(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition":
                     'attachment; filename="stickblade-matches.csv"'})
    if fmt == "jsonl":
        # Streaming-friendly one-line-per-match. HF Datasets ingests
        # this directly with `load_dataset("json", data_files=url)`.
        import json as _json
        from fastapi.responses import PlainTextResponse
        body = "\n".join(_json.dumps(r, separators=(",", ":")) for r in rows)
        return PlainTextResponse(
            body, media_type="application/x-ndjson",
            headers={"Content-Disposition":
                     'attachment; filename="stickblade-matches.jsonl"'})
    # Default JSON wrapper — carries metadata alongside the array so
    # dataset consumers can pin their analysis to a specific export.
    import time as _time
    from brains import PROMPT_VERSION
    return {
        "count": len(rows),
        "exported_at": _time.time(),
        "prompt_version": PROMPT_VERSION,
        "since": since, "until": until, "limit": lim,
        # Data license declared explicitly so downstream consumers know
        # the terms without having to guess or ask. Match data is under
        # CC-BY-SA 4.0 (attribution + share-alike), separate from the
        # Apache 2.0 code license. See research/DATA_LICENSE.md in the
        # repo for the human-readable version + citation format.
        "license": "CC-BY-SA-4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "cite": "See https://github.com/Cometbuster4969/STICKBLADE-ARENA/blob/main/CITATION.cff",
        # Board-level evidence summary so a downloader knows up front how
        # much of this file is scripted baseline vs real-provider data.
        "data_quality": DQ.summary(rows),
        "matches": rows,
    }


@app.get("/api/stats/vote_rate")
def stats_vote_rate(days: int = 7):
    """Public vote-through rate — what fraction of completed matches
    actually get voted on. Instrumentation for the "people run matches
    but skip voting" hypothesis surfaced before the HN launch. Both
    lifetime and last-N-day windows so we can see whether UI changes
    (reveal-as-reward copy, streak card, prediction-accuracy display)
    actually move the number.

    Deliberately public: (a) it's aggregate-only, no PII, no per-match
    detail beyond counts, (b) transparency about eval methodology is
    the whole positioning of this project — "here's how many people
    actually voted vs. just watched" is exactly the kind of
    limitations-disclosure a research artifact should ship.

    `days` clamped to [1, 90] to keep the Supabase count query bounded."""
    days = max(1, min(int(days or 7), 90))
    return store.vote_rate_stats(window_days=days)


@app.get("/api/recent")
def recent():
    """Recent duels for the history list.

    Carries the full ruleset of each match (weapon / sharp / arena / mode /
    blindfolded), the winner side, the integrity summary and a timestamp so
    the history cards are scannable without opening every replay. Model
    names stay hidden until the match has been voted on — that's the blind
    boundary, and it applies to the history list too.
    """
    rows = store.recent_matches()
    out = []
    for m in rows:
        fb_a = int(m.get("fallback_turns_a") or 0)
        fb_b = int(m.get("fallback_turns_b") or 0)
        turns = int(m.get("turns") or 0)
        out.append({
            "match_id": m["id"],
            "created": m.get("created"),
            "sharp": m["sharp"],
            "weapon": m.get("weapon") or "sword",
            "arena": m.get("arena") or "normal",
            "mode": m.get("mode") or "macro",
            "blindfolded": bool(m.get("blindfolded")),
            "turns": turns,
            "method": m["method"],
            "winner_side": m.get("winner_side"),
            "voted": bool(m["voted"]),
            "fallback_turns": fb_a + fb_b,
            "total_turns": turns,
            "fully_llm_controlled": (fb_a + fb_b) == 0,
            "models": ([C.ARENA_MODELS.get(m["model_a"], m["model_a"]),
                        C.ARENA_MODELS.get(m["model_b"], m["model_b"])]
                       if m["voted"] or not m["blind"] else None),
        })
    return out


# ------------------------------------------------------------- arena page
HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(HERE, "arena_page.html")) as f:
        return f.read()


@app.get("/static/player.js")
def player_js():
    """Serve the canvas replay player. Single source of truth is
    stickblade-web/public/player.js (the file Vercel serves to the
    real Next.js frontend). This route exists only for the legacy
    embedded arena_page.html; keeping ONE copy of the player prevents
    the drift bug where the backend/frontend copies got out of sync
    (missing WEAPON_GEO table, missing audio, wrong canvas sizing).
    Falls back to a stub file in the same dir if the frontend tree
    isn't present (e.g. someone pip-installs just the backend)."""
    from fastapi.responses import FileResponse
    candidates = [
        # 1) monorepo layout used in this repo
        os.path.normpath(os.path.join(HERE, "..", "stickblade-web",
                                      "public", "player.js")),
        # 2) backend-only install fallback (kept for offline dev)
        os.path.join(HERE, "player.js"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return FileResponse(path,
                                media_type="application/javascript",
                                headers={"Cache-Control": "no-cache, max-age=0"})
    raise HTTPException(404, "player.js not found — frontend tree missing")
