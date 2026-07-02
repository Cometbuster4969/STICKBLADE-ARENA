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

import config as C
import security
from storage import LocalStorage

VERSION = "1.3.0"   # weapons + joint mode + player polyfill + admin bypass

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

print(f"[server] STICKBLADE ARENA v1.3.0 — weapons: sword/flail/bow, "
      f"modes: macro/joint")
if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
    from storage_supabase import SupabaseStorage
    store = SupabaseStorage()
    print("[server] storage: Supabase (persistent)")
else:
    store = LocalStorage()
    print("[server] storage: local SQLite (set SUPABASE_URL + SUPABASE_KEY "
          "for persistence)")
jobs: "queue.Queue[str]" = queue.Queue()
MATCH_MODES: dict = {}   # match_id -> "macro" | "joint" (in-memory; default macro)

BLIND_NAMES = {"a": "Fighter A", "b": "Fighter B"}
BLIND_COLORS = {"a": ("#56dc82", 1), "b": ("#5aa0ff", 2)}

# Per-match A↔green / B↔blue assignment, picked at queue time and consumed
# by the worker when the simulation kicks off. Keeps the user from knowing
# which colored ragdoll is the model they personally picked.
MATCH_FLIP = {}     # mid -> bool   True = (model_a -> Fighter B, model_b -> Fighter A)

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


def _live_init(mid):
    with LIVE_STATE_LOCK:
        LIVE_STATE[mid] = {"quips": None, "turn": 0, "log": [], "queue_pos": None}


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
                "log": list(st["log"]), "queue_pos": st["queue_pos"]}


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
    tick = {
        "turn":   turn,
        "action_a": _pick_action(f1.name),
        "action_b": _pick_action(f2.name),
        "hits":   hits,
        "hp_a":   round(float(f1.hp), 1),
        "hp_b":   round(float(f2.hp), 1),
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
        match = Match(slot_left, slot_right, sharp, fx,
                      log_path=os.path.join(store.root, f"log_{mid}.json"),
                      mode=mm.get("mode", "macro"),
                      weapon=mm.get("weapon", "sword"),
                      arena=mm.get("arena", "normal"))
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
        deadline = _t.time() + 45 * 60
        sim_frames = 0
        # Live wait-screen ticker: publish each turn to LIVE_STATE the moment
        # it finalizes (hits appended). Rule: match.log[i] is finalized once
        # match.log has grown past i (i.e. the NEXT turn started) OR the
        # match is over. Watching len() avoids racing with the PH_SIM ->
        # PH_THINK phase transition.
        last_published = 0
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
        while match.phase != Match.PH_OVER and _t.time() < deadline \
                and sim_frames < 60 * 60 * 10:
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
            _publish_finalized()
            if match.phase == Match.PH_THINK:
                _t.sleep(0.02)      # don't burn CPU while LLMs think
            else:
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

        store.finish_match(mid, side, res["method"], res["turns"],
                           rec.build(), commentary=commentary)
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.set_status(mid, "error", _safe_err(e))
    finally:
        # Free the per-match config dict now that the sim is done. Without
        # this, MATCH_MODES grew unbounded for the life of the process
        # (~300 bytes/match, small but real on a long-running instance).
        # MATCH_FLIP already pops itself on line 139 above; this closes
        # the matching leak on the mode/weapon/arena side.
        MATCH_MODES.pop(mid, None)
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
    mid = store.create_match(model_a, model_b, sharp, blind=True, weapon=weapon)
    # Same arena / mode for the whole tournament
    MATCH_MODES[mid] = {"mode": t.get("mode", "macro"),
                        "weapon": weapon,
                        "arena":  t.get("arena", "normal")}
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
    mode: str = Field(default="macro", max_length=8)    # macro | joint
    weapon: str = Field(default="sword", max_length=8)  # sword | dagger | spear | flail | bow
    arena: str = Field(default="normal", max_length=16) # normal | ice | low_gravity


class VoteReq(BaseModel):
    choice: str = Field(max_length=8)  # a | b | draw


@app.get("/api/version")
def version():
    from weapons import WEAPONS
    return {"version": VERSION, "weapons": WEAPONS,
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
        "has_openai":     bool(C.OPENAI_API_KEY),
        "has_gemini":     bool(C.GEMINI_API_KEY),
        "has_supabase":   bool(os.environ.get("SUPABASE_URL")
                              and os.environ.get("SUPABASE_KEY")),
        "queue":            jobs.qsize(),
        "tournament_queue": tournament_jobs.qsize(),
    }


@app.get("/api/models")
def models():
    return [{"id": k, "name": v} for k, v in C.ARENA_MODELS.items()]


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


@app.get("/api/weapons")
def weapons_list():
    from weapons import WEAPONS, WEAPON_ZONES
    return [{"id": w, "zones": WEAPON_ZONES[w]} for w in WEAPONS]


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
    weapon = req.weapon if req.weapon in WEAPONS else "sword"
    sharp = [z for z in req.sharp if z in WEAPON_ZONES[weapon]] \
        or [WEAPON_ZONES[weapon][0]]
    mode = req.mode if req.mode in ("macro", "joint") else "macro"
    arena = req.arena if req.arena in ("normal", "ice", "low_gravity") else "normal"
    mid = store.create_match(req.model_a, req.model_b, sharp, req.blind, weapon)
    MATCH_MODES[mid] = {"mode": mode, "weapon": weapon, "arena": arena}
    # Lock in the A↔green/B↔blue random assignment at queue time so even
    # the worker that picks up the job can't pre-leak which colored
    # ragdoll the user's picks correspond to.
    import random as _r
    MATCH_FLIP[mid] = _r.random() < 0.5
    jobs.put(mid)
    return {"match_id": mid, "status": "queued", "mode": mode,
            "weapon": weapon, "arena": arena}


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
    if m["status"] in ("queued", "running"):
        snap = _live_snapshot(mid)
        if snap is None and m["status"] == "queued":
            # Queued but the worker hasn't dequeued us yet: compute
            # position from the FIFO's current size. Not exact under
            # concurrent enqueues, but plenty good enough for the UI's
            # "N ahead of you" text.
            snap = {"quips": None, "turn": 0, "log": [],
                    "queue_pos": max(0, jobs.qsize() - 1)}
        if snap is not None:
            out["live"] = snap
    if m["status"] == "done":
        out.update({"engine_winner_side": m["winner_side"],
                    "method": m["method"], "turns": m["turns"]})
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


@app.get("/api/replay/{mid}")
def replay(mid: str):
    _validate_id(mid)
    r = store.get_replay(mid)
    if not r:
        raise HTTPException(404, "replay not ready")
    return JSONResponse(r)


@app.post("/api/vote/{mid}")
def vote(mid: str, req: VoteReq, request: Request):
    _validate_id(mid)
    security.check_vote_allowed(request)
    if req.choice not in ("a", "b", "draw"):
        raise HTTPException(400, "choice must be a|b|draw")
    res = store.record_vote(mid, req.choice)
    if res is None:
        raise HTTPException(400, "match not finished or not found")
    # add display names — for both the user's original pick axis AND the
    # canvas (green/blue) axis so the UI can say "Fighter A (green) was X".
    all_models = {res["model_a"], res["model_b"],
                  res.get("canvas_a_model"), res.get("canvas_b_model")}
    res["names"] = {m: C.ARENA_MODELS.get(m, m) for m in all_models if m}
    return res


@app.get("/api/leaderboard")
def leaderboard(sharp: str | None = None, weapon: str | None = None):
    rows = store.leaderboard(sharp, weapon)
    for r in rows:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
        r["rating"] = round(r["rating"], 1)
    return rows


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
    weapon: str = Field(default="sword", max_length=8)
    sharp:  list[str] = Field(default=["tip"], max_length=4)
    arena:  str = Field(default="normal", max_length=16)
    mode:   str = Field(default="macro", max_length=8)


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
    weapon = req.weapon if req.weapon in WEAPONS else "sword"
    sharp  = [z for z in req.sharp if z in WEAPON_ZONES[weapon]] \
             or [WEAPON_ZONES[weapon][0]]
    arena  = req.arena if req.arena in ("normal", "ice", "low_gravity") else "normal"
    mode   = req.mode  if req.mode  in ("macro", "joint")               else "macro"

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


@app.get("/api/recent")
def recent():
    rows = store.recent_matches()
    out = []
    for m in rows:
        out.append({"match_id": m["id"], "sharp": m["sharp"],
                    "turns": m["turns"], "method": m["method"],
                    "voted": bool(m["voted"]),
                    "models": ([C.ARENA_MODELS.get(m["model_a"], m["model_a"]),
                                C.ARENA_MODELS.get(m["model_b"], m["model_b"])]
                               if m["voted"] or not m["blind"] else None)})
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
