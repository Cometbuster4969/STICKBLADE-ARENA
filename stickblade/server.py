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
import threading

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import config as C
import security
from storage import LocalStorage

app = FastAPI(title="Stickblade Arena", docs_url=None, redoc_url=None,
              openapi_url=None)
# Allow the standalone Next.js frontend (Vercel) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
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


# ------------------------------------------------------------- simulation
def run_simulation(mid):
    """Worker: run one headless match and store the replay (names hidden)."""
    import pygame
    from main import Match
    from recorder import ReplayRecorder, RecordingFX

    m = store.get_match(mid)
    store.set_status(mid, "running")
    try:
        if not pygame.get_init():
            pygame.init()
            pygame.display.set_mode((C.WIDTH, C.HEIGHT))
        sharp = m["sharp"].split(",")
        rec = ReplayRecorder(every=2)
        fx = RecordingFX(rec)
        match = Match(m["model_a"], m["model_b"], sharp, fx,
                      log_path=os.path.join(store.root, f"log_{mid}.json"),
                      mode=MATCH_MODES.get(mid, "macro"))
        # blind mode: hide model identity in the replay itself
        if m["blind"]:
            match.f1.name = match.b1.label = BLIND_NAMES["a"]
            match.f2.name = match.b2.label = BLIND_NAMES["b"]
        rec.attach(match)
        frames = 0
        while match.phase != Match.PH_OVER and frames < 60 * 60 * 30:
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
            frames += 1
        for _ in range(90):
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
        res = match.result
        if res["winner"] is None:
            side = "draw"
        else:
            side = "a" if res["winner"] == match.f1.name else "b"
        store.finish_match(mid, side, res["method"], res["turns"], rec.build())
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.set_status(mid, "error", str(e)[:300])


def worker_loop():
    while True:
        mid = jobs.get()
        try:
            run_simulation(mid)
        except Exception as e:          # never let the worker die
            import traceback
            traceback.print_exc()
            try:
                store.set_status(mid, "error", str(e)[:300])
            except Exception:
                pass


threading.Thread(target=worker_loop, daemon=True).start()


# ------------------------------------------------------------- API
class MatchReq(BaseModel):
    model_a: str = Field(min_length=1, max_length=120)
    model_b: str = Field(min_length=1, max_length=120)
    sharp: list[str] = Field(default=["tip"], max_length=4)
    blind: bool = True
    mode: str = Field(default="macro", max_length=8)  # macro | joint


class VoteReq(BaseModel):
    choice: str = Field(max_length=8)  # a | b | draw


@app.get("/api/models")
def models():
    return [{"id": k, "name": v} for k, v in C.ARENA_MODELS.items()]


import re

_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:-]*$", re.I)


def _valid_model(mdl: str) -> bool:
    """Roster models, mock:* personalities, or a well-formed OpenRouter id."""
    if mdl in C.ARENA_MODELS or mdl in ("mock:duelist", "mock:berserker"):
        return True
    return bool(_MODEL_ID_RE.match(mdl)) and len(mdl) < 120


@app.post("/api/match")
def create_match(req: MatchReq, request: Request):
    # validate first so rejected requests don't consume the rate budget
    for mdl in (req.model_a, req.model_b):
        if not _valid_model(mdl):
            raise HTTPException(400, f"unknown model: {mdl}")
        security.check_model_spend_policy(mdl, C.ARENA_MODELS)
    security.check_match_allowed(request, jobs.qsize())
    sharp = [z for z in req.sharp if z in C.ALL_ZONES] or ["tip"]
    mode = req.mode if req.mode in ("macro", "joint") else "macro"
    mid = store.create_match(req.model_a, req.model_b, sharp, req.blind)
    MATCH_MODES[mid] = mode
    jobs.put(mid)
    return {"match_id": mid, "status": "queued", "mode": mode}


@app.get("/api/match/{mid}")
def match_status(mid: str):
    m = store.get_match(mid)
    if not m:
        raise HTTPException(404, "no such match")
    out = {"match_id": mid, "status": m["status"], "sharp": m["sharp"],
           "voted": bool(m["voted"]), "error": m["error"]}
    if m["status"] == "done":
        out.update({"engine_winner_side": m["winner_side"],
                    "method": m["method"], "turns": m["turns"]})
        if not m["blind"] or m["voted"]:
            out.update({"model_a": m["model_a"], "model_b": m["model_b"]})
    return out


@app.get("/api/replay/{mid}")
def replay(mid: str):
    r = store.get_replay(mid)
    if not r:
        raise HTTPException(404, "replay not ready")
    return JSONResponse(r)


@app.post("/api/vote/{mid}")
def vote(mid: str, req: VoteReq, request: Request):
    security.check_vote_allowed(request)
    if req.choice not in ("a", "b", "draw"):
        raise HTTPException(400, "choice must be a|b|draw")
    res = store.record_vote(mid, req.choice)
    if res is None:
        raise HTTPException(400, "match not finished or not found")
    # add display names
    res["names"] = {m: C.ARENA_MODELS.get(m, m)
                    for m in (res["model_a"], res["model_b"])}
    return res


@app.get("/api/leaderboard")
def leaderboard(sharp: str | None = None):
    rows = store.leaderboard(sharp)
    for r in rows:
        r["name"] = C.ARENA_MODELS.get(r["model"], r["model"])
        r["rating"] = round(r["rating"], 1)
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
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(HERE, "player.js"),
                        media_type="application/javascript")
