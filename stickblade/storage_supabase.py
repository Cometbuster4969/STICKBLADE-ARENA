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
    def create_match(self, model_a, model_b, sharp, blind=True):
        mid = uuid.uuid4().hex[:12]
        self._rest("POST", "matches", body={
            "id": mid, "created": time.time(),
            "model_a": model_a, "model_b": model_b,
            "sharp": ",".join(sharp), "status": "queued",
            "blind": bool(blind), "voted": False,
        })
        return mid

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
    def _get_elo_row(self, model, sharp):
        rows = self._rest("GET", "elo", params={
            "model": f"eq.{model}", "sharp": f"eq.{sharp}"})
        if rows:
            return dict(rows[0])
        row = {"model": model, "sharp": sharp, "rating": START_ELO,
               "wins": 0, "losses": 0, "draws": 0}
        self._rest("POST", "elo", body=row,
                   prefer="resolution=merge-duplicates")
        return row

    def _set_elo_row(self, row):
        self._rest("PATCH", "elo", params={
            "model": f"eq.{row['model']}", "sharp": f"eq.{row['sharp']}"},
            body={"rating": row["rating"], "wins": row["wins"],
                  "losses": row["losses"], "draws": row["draws"]})

    def record_vote(self, mid, choice):
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        a, b = m["model_a"], m["model_b"]
        self._rest("POST", "votes", body={
            "id": uuid.uuid4().hex[:12], "match_id": mid,
            "created": time.time(), "choice": choice})
        ra, rb = self._get_elo_row(a, sharp), self._get_elo_row(b, sharp)
        ea = 1.0 / (1.0 + 10 ** ((rb["rating"] - ra["rating"]) / 400.0))
        sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[choice]
        d_a = K_FACTOR * (sa - ea)
        d_b = K_FACTOR * ((1.0 - sa) - (1.0 - ea))
        ra["rating"] += d_a
        rb["rating"] += d_b
        if choice == "a":
            ra["wins"] += 1
            rb["losses"] += 1
        elif choice == "b":
            ra["losses"] += 1
            rb["wins"] += 1
        else:
            ra["draws"] += 1
            rb["draws"] += 1
        self._set_elo_row(ra)
        self._set_elo_row(rb)
        self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                   body={"voted": True})
        return {"elo_change": {a: round(d_a, 1), b: round(d_b, 1)},
                **self.reveal(mid)}

    def reveal(self, mid):
        m = self.get_match(mid)
        return {"model_a": m["model_a"], "model_b": m["model_b"],
                "engine_winner_side": m["winner_side"], "method": m["method"]}

    def leaderboard(self, sharp=None):
        if sharp:
            rows = self._rest("GET", "elo", params={
                "sharp": f"eq.{sharp}", "order": "rating.desc"})
            return [dict(r) for r in rows]
        rows = self._rest("GET", "elo", params={"order": "rating.desc"})
        agg = {}
        for r in rows:
            a = agg.setdefault(r["model"], {
                "model": r["model"], "sharp": "ALL", "rating": [],
                "wins": 0, "losses": 0, "draws": 0})
            a["rating"].append(r["rating"])
            a["wins"] += r["wins"]
            a["losses"] += r["losses"]
            a["draws"] += r["draws"]
        out = []
        for a in agg.values():
            a["rating"] = sum(a["rating"]) / len(a["rating"])
            out.append(a)
        out.sort(key=lambda x: -x["rating"])
        return out
