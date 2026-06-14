"""Supabase storage backend — drop-in replacement for LocalStorage.

Activated automatically by server.py when these env vars are set:
    SUPABASE_URL  = https://<project>.supabase.co
    SUPABASE_KEY  = service_role key (Settings -> API). Keep it server-side only!

Setup (one time): run supabase_schema.sql in the Supabase SQL editor, and
create a private Storage bucket named 'replays'.

Implementation: talks straight to Supabase's PostgREST + Storage HTTP APIs
via httpx — no extra SDK dependency.
"""
import json
import os
import time
import uuid

import httpx

K_FACTOR = 32
START_ELO = 1000.0
BUCKET = "replays"


class SupabaseStorage:
    def __init__(self, url=None, key=None):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = key or os.environ["SUPABASE_KEY"]
        self.root = "arena_data"          # kept for turn-log file paths
        os.makedirs(self.root, exist_ok=True)
        self.http = httpx.Client(
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
            },
            timeout=30,
        )

    # ------------------------------------------------------------ helpers
    def _rest(self, method, table, params=None, body=None, prefer=None):
        headers = {"Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        r = self.http.request(
            method, f"{self.url}/rest/v1/{table}",
            params=params, json=body, headers=headers)
        r.raise_for_status()
        return r.json() if r.content else None

    # ------------------------------------------------------------ matches
    def create_match(self, model_a, model_b, sharp, blind=True, weapon="sword"):
        mid = uuid.uuid4().hex[:12]
        body = {
            "id": mid, "created": time.time(),
            "model_a": model_a, "model_b": model_b,
            "sharp": ",".join(sharp), "weapon": weapon,
            "status": "queued",
            "blind": bool(blind), "voted": False, "flip": False,
        }
        try:
            self._rest("POST", "matches", body=body)
        except Exception:
            # Older Supabase schema without weapon/flip columns: try again
            # without them so the deploy doesn't break before the migration.
            body.pop("weapon", None); body.pop("flip", None)
            self._rest("POST", "matches", body=body)
        return mid

    def set_flip(self, mid, flip: bool):
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                       body={"flip": bool(flip)})
        except Exception:
            pass   # column not present yet

    def set_status(self, mid, status, error=None):
        self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                   body={"status": status, "error": error})

    def finish_match(self, mid, winner_side, method, turns, replay):
        data = json.dumps(replay, separators=(",", ":")).encode()
        r = self.http.post(
            f"{self.url}/storage/v1/object/{BUCKET}/{mid}.json",
            content=data,
            headers={"Content-Type": "application/json",
                     "x-upsert": "true"})
        r.raise_for_status()
        self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                   body={"status": "done", "winner_side": winner_side,
                         "method": method, "turns": turns})

    def get_match(self, mid):
        rows = self._rest("GET", "matches", params={"id": f"eq.{mid}"})
        if not rows:
            return None
        m = dict(rows[0])
        m["blind"] = 1 if m.get("blind") else 0
        m["voted"] = 1 if m.get("voted") else 0
        return m

    def get_replay(self, mid):
        r = self.http.get(f"{self.url}/storage/v1/object/{BUCKET}/{mid}.json")
        if r.status_code != 200:
            return None
        return r.json()

    def recent_matches(self, limit=20):
        rows = self._rest("GET", "matches", params={
            "status": "eq.done", "order": "created.desc", "limit": str(limit)})
        out = []
        for r in rows:
            m = dict(r)
            m["blind"] = 1 if m.get("blind") else 0
            m["voted"] = 1 if m.get("voted") else 0
            out.append(m)
        return out

    # ------------------------------------------------------------ votes/elo
    def _get_elo_row(self, model, sharp, weapon):
        params = {"model": f"eq.{model}", "sharp": f"eq.{sharp}",
                  "weapon": f"eq.{weapon}"}
        rows = self._rest("GET", "elo", params=params)
        if rows:
            return dict(rows[0])
        row = {"model": model, "sharp": sharp, "weapon": weapon,
               "rating": START_ELO, "wins": 0, "losses": 0, "draws": 0}
        try:
            self._rest("POST", "elo", body=row,
                       prefer="resolution=merge-duplicates")
        except Exception:
            row.pop("weapon", None)
            self._rest("POST", "elo", body=row,
                       prefer="resolution=merge-duplicates")
        return row

    def _set_elo_row(self, row):
        params = {"model": f"eq.{row['model']}", "sharp": f"eq.{row['sharp']}"}
        if row.get("weapon"):
            params["weapon"] = f"eq.{row['weapon']}"
        self._rest("PATCH", "elo", params=params,
            body={"rating": row["rating"], "wins": row["wins"],
                  "losses": row["losses"], "draws": row["draws"]})

    @staticmethod
    def _unflip_choice(choice, flip):
        if choice == "draw":
            return "draw"
        if not flip:
            return choice
        return "a" if choice == "b" else "b"

    def record_vote(self, mid, choice):
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        weapon = m.get("weapon") or "sword"
        flip = bool(m.get("flip"))
        a, b = m["model_a"], m["model_b"]
        choice_model = self._unflip_choice(choice, flip)
        self._rest("POST", "votes", body={
            "id": uuid.uuid4().hex[:12], "match_id": mid,
            "created": time.time(), "choice": choice})
        ra, rb = (self._get_elo_row(a, sharp, weapon),
                  self._get_elo_row(b, sharp, weapon))
        ea = 1.0 / (1.0 + 10 ** ((rb["rating"] - ra["rating"]) / 400.0))
        sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[choice_model]
        d_a = K_FACTOR * (sa - ea)
        d_b = K_FACTOR * ((1.0 - sa) - (1.0 - ea))
        ra["rating"] += d_a
        rb["rating"] += d_b
        if choice_model == "a":
            ra["wins"] += 1; rb["losses"] += 1
        elif choice_model == "b":
            ra["losses"] += 1; rb["wins"] += 1
        else:
            ra["draws"] += 1; rb["draws"] += 1
        self._set_elo_row(ra)
        self._set_elo_row(rb)
        self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                   body={"voted": True})
        return {"elo_change": {a: round(d_a, 1), b: round(d_b, 1)},
                **self.reveal(mid)}

    def reveal(self, mid):
        m = self.get_match(mid)
        flip = bool(m.get("flip"))
        canvas_a = m["model_b"] if flip else m["model_a"]
        canvas_b = m["model_a"] if flip else m["model_b"]
        return {
            "model_a": m["model_a"], "model_b": m["model_b"],
            "canvas_a_model": canvas_a, "canvas_b_model": canvas_b,
            "engine_winner_side": m["winner_side"], "method": m["method"],
            "flip": flip, "weapon": m.get("weapon") or "sword",
        }

    def leaderboard(self, sharp=None, weapon=None):
        params = {"order": "rating.desc"}
        if sharp:  params["sharp"] = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if sharp or weapon:
            rows = self._rest("GET", "elo", params=params)
            return [dict(r) for r in rows]
        rows = self._rest("GET", "elo", params=params)
        agg = {}
        for r in rows:
            a = agg.setdefault(r["model"], {
                "model": r["model"], "sharp": "ALL", "weapon": "ALL",
                "rating": [], "wins": 0, "losses": 0, "draws": 0})
            a["rating"].append(r["rating"])
            a["wins"] += r["wins"]; a["losses"] += r["losses"]; a["draws"] += r["draws"]
        out = []
        for a in agg.values():
            a["rating"] = sum(a["rating"]) / len(a["rating"])
            out.append(a)
        out.sort(key=lambda x: -x["rating"])
        return out
