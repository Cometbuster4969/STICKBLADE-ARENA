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
import threading
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
        # In-process fallback lock. Serializes record_vote() calls WITHIN
        # this Python process so the read-modify-write path (used when the
        # apply_elo_vote RPC isn't installed) can't race with itself. This
        # is a belt to the RPC's suspenders — the RPC still gives real
        # concurrency safety across multiple processes, but this saves us
        # from lost updates the first time you deploy after adding a new
        # supabase-hosted node without re-running the schema.
        self._vote_lock = threading.Lock()
        # Cache the RPC availability check (one-time probe per process).
        # True  = RPC installed, use atomic path
        # False = RPC missing, fall back to REST + in-process lock
        self._rpc_ok = None

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
    def create_match(self, model_a, model_b, sharp, blind=True, weapon="sword",
                     mode="macro", arena="normal"):
        mid = uuid.uuid4().hex[:12]
        body = {
            "id": mid, "created": time.time(),
            "model_a": model_a, "model_b": model_b,
            "sharp": ",".join(sharp), "weapon": weapon,
            "mode": mode, "arena": arena,
            "status": "queued",
            "blind": bool(blind), "voted": False, "flip": False,
        }
        try:
            self._rest("POST", "matches", body=body)
        except Exception:
            # Older Supabase schema without weapon/flip/mode/arena columns:
            # try again without them so the deploy doesn't break before the
            # migration. record_vote() will fall back to (macro, normal) for
            # any match created this way (fields are NULL, python COALESCEs).
            for k in ("weapon", "flip", "mode", "arena"):
                body.pop(k, None)
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

    def finish_match(self, mid, winner_side, method, turns, replay,
                     commentary=None):
        data = json.dumps(replay, separators=(",", ":")).encode()
        r = self.http.post(
            f"{self.url}/storage/v1/object/{BUCKET}/{mid}.json",
            content=data,
            headers={"Content-Type": "application/json",
                     "x-upsert": "true"})
        r.raise_for_status()
        body = {"status": "done", "winner_side": winner_side,
                "method": method, "turns": turns}
        if commentary:
            body["commentary"] = commentary
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"}, body=body)
        except Exception:
            # commentary col may not exist on older schemas — retry without it
            body.pop("commentary", None)
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"}, body=body)

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

    def vote_rate_stats(self, window_days=7):
        """Mirror of SQLite vote_rate_stats. The Supabase `matches.created`
        column is a float epoch (per create_match: `time.time()`), not
        an ISO timestamp, so we pass the threshold as a numeric compare
        (`gte.<epoch>`). Bounded to 10k rows per query — well above any
        realistic 7-day window even under HN-frontpage load."""
        import time as _time
        since_epoch = _time.time() - window_days * 86400

        def _count(params):
            try:
                rows = self._rest("GET", "matches",
                                  params={**params, "select": "id",
                                          "limit": "10000"})
                return len(rows)
            except Exception:
                return 0

        done_win  = _count({"status": "eq.done",
                            "created": f"gte.{since_epoch}"})
        voted_win = _count({"status": "eq.done", "voted": "eq.true",
                            "created": f"gte.{since_epoch}"})
        done_all  = _count({"status": "eq.done"})
        voted_all = _count({"status": "eq.done", "voted": "eq.true"})
        return {
            "window_days": window_days,
            "window": {"done": done_win, "voted": voted_win,
                       "rate": round(voted_win / done_win, 4) if done_win else 0.0},
            "lifetime": {"done": done_all, "voted": voted_all,
                         "rate": round(voted_all / done_all, 4) if done_all else 0.0},
        }

    def head_to_head(self, a, b, limit=50):
        """Order-insensitive H2H aggregate for the wait-screen card.
        Matches signature of LocalStorage.head_to_head — see that docstring."""
        if not a or not b:
            return {"total": 0, "a_wins": 0, "b_wins": 0, "draws": 0,
                    "avg_turns": 0, "recent": []}
        # PostgREST OR filter: (model_a.eq.A,model_b.eq.B),(model_a.eq.B,model_b.eq.A)
        or_clause = (f"and(model_a.eq.{a},model_b.eq.{b}),"
                     f"and(model_a.eq.{b},model_b.eq.{a})")
        rows = self._rest("GET", "matches", params={
            "status": "eq.done", "or": f"({or_clause})",
            "order":  "created.desc", "limit": str(limit)})
        rows = [dict(r) for r in (rows or [])]
        aw = bw = dr = 0
        turns_total = 0
        for r in rows:
            turns_total += (r.get("turns") or 0)
            side = r.get("winner_side")
            if side == "draw":
                dr += 1
                continue
            flip = bool(r.get("flip"))
            model_axis = ("a" if side == "a" else "b")
            if flip:
                model_axis = "b" if model_axis == "a" else "a"
            winner_model = r["model_a"] if model_axis == "a" else r["model_b"]
            if winner_model == a:
                aw += 1
            elif winner_model == b:
                bw += 1
        n = len(rows)
        return {
            "total":     n,
            "a_wins":    aw,
            "b_wins":    bw,
            "draws":     dr,
            "avg_turns": round(turns_total / n, 1) if n else 0,
            "recent":    [{"id": r["id"], "sharp": r["sharp"],
                            "weapon": r["weapon"], "turns": r["turns"]}
                           for r in rows[:8]],
        }

    # ------------------------------------------------------------ votes/elo
    def _get_elo_row(self, model, sharp, weapon, mode="macro", arena="normal"):
        """Tier-S commit 2: PK is now (model, sharp, weapon, mode, arena).
        Callers that don't pass mode/arena default to (macro, normal),
        which is what pre-migration data effectively was."""
        params = {"model": f"eq.{model}", "sharp": f"eq.{sharp}",
                  "weapon": f"eq.{weapon}",
                  "mode": f"eq.{mode}", "arena": f"eq.{arena}"}
        rows = self._rest("GET", "elo", params=params)
        if rows:
            return dict(rows[0])
        row = {"model": model, "sharp": sharp, "weapon": weapon,
               "mode": mode, "arena": arena,
               "rating": START_ELO, "wins": 0, "losses": 0, "draws": 0}
        # Same rationale as the old comment: hard-fail loudly instead of
        # silently corrupting cross-cell data. If POST fails, the operator
        # needs to re-run supabase_schema.sql (with the new mode/arena
        # migration block) before votes can flow again.
        self._rest("POST", "elo", body=row,
                   prefer="resolution=merge-duplicates")
        return row

    def _set_elo_row(self, row):
        # (model, sharp, weapon, mode, arena) are ALL required — they're
        # the PK, and PATCHing without one would spray the update across
        # every row that matches the partial key. Enforced by contract,
        # not silently papered over. If this fires: re-run
        # supabase_schema.sql; the migration is incomplete.
        for key in ("weapon", "mode", "arena"):
            if not row.get(key):
                raise ValueError(
                    f"_set_elo_row: '{key}' is required (part of the elo PK); "
                    f"re-run supabase_schema.sql if this fires — the migration "
                    f"is incomplete.")
        params = {"model":  f"eq.{row['model']}",
                  "sharp":  f"eq.{row['sharp']}",
                  "weapon": f"eq.{row['weapon']}",
                  "mode":   f"eq.{row['mode']}",
                  "arena":  f"eq.{row['arena']}"}
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

    def _apply_elo_atomic(self, a, b, sharp, weapon, mode, arena, choice_model):
        """Call the apply_elo_vote() Postgres RPC in one atomic txn.
        Returns (d_a, d_b) or raises if the RPC isn't installed.
        Tier-S commit 2: signature now includes mode + arena so ratings
        segment correctly. Requires the updated RPC — re-run the SQL in
        supabase_schema.sql after pulling this commit."""
        rows = self._rest(
            "POST", "rpc/apply_elo_vote",
            body={"a_model": a, "b_model": b,
                  "p_sharp": sharp, "p_weapon": weapon,
                  "p_mode": mode, "p_arena": arena,
                  "choice_model": choice_model,
                  "k_factor": K_FACTOR, "start_elo": START_ELO})
        if not rows:
            raise RuntimeError("apply_elo_vote RPC returned no row")
        row = rows[0] if isinstance(rows, list) else rows
        return float(row["d_a"]), float(row["d_b"])

    def _apply_elo_fallback(self, a, b, sharp, weapon, mode, arena, choice_model):
        """Read-modify-write path. Racy across processes, but this method
        is only reached if the atomic RPC isn't installed on the Postgres
        side. Wrapped by self._vote_lock in record_vote() so it's at least
        safe within a single Python process."""
        # Self-play (mirror match): can't gain rating vs yourself. Log a
        # draw and return zero deltas so the leaderboard reflects the
        # match without double-updating the same row (which would corrupt).
        if a == b:
            row = self._get_elo_row(a, sharp, weapon, mode, arena)
            row["draws"] += 1
            self._set_elo_row(row)
            return 0.0, 0.0
        ra, rb = (self._get_elo_row(a, sharp, weapon, mode, arena),
                  self._get_elo_row(b, sharp, weapon, mode, arena))
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
        return d_a, d_b

    def record_vote(self, mid, choice):
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        weapon = m.get("weapon") or "sword"
        # Pull mode + arena from the match row — same rationale as SQLite:
        # votes must route to the cell the match was played under.
        # Pre-commit-2 matches (NULL mode/arena) fall back to macro/normal.
        mode = m.get("mode") or "macro"
        arena = m.get("arena") or "normal"
        flip = bool(m.get("flip"))
        a, b = m["model_a"], m["model_b"]
        choice_model = self._unflip_choice(choice, flip)
        self._rest("POST", "votes", body={
            "id": uuid.uuid4().hex[:12], "match_id": mid,
            "created": time.time(), "choice": choice})
        # Prefer the atomic Postgres RPC (safe across processes).
        # Fall back to REST + in-process lock if the RPC isn't installed
        # yet — that gates concurrency inside this Python instance but
        # can still lose updates if the backend runs multiple workers.
        # After first success we cache _rpc_ok so we skip the retry cost.
        d_a = d_b = None
        if self._rpc_ok is not False:
            try:
                d_a, d_b = self._apply_elo_atomic(a, b, sharp, weapon,
                                                  mode, arena, choice_model)
                self._rpc_ok = True
            except Exception as e:
                # RPC missing / bad signature / etc — log once and downgrade.
                if self._rpc_ok is None:
                    print(f"[storage] apply_elo_vote RPC unavailable ({e}); "
                          f"falling back to REST + in-process lock. "
                          f"Re-run supabase_schema.sql to enable atomic path.")
                self._rpc_ok = False
        if d_a is None:
            with self._vote_lock:
                d_a, d_b = self._apply_elo_fallback(a, b, sharp, weapon,
                                                    mode, arena, choice_model)
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
            "commentary": m.get("commentary") or "",
        }

    def leaderboard(self, sharp=None, weapon=None, mode=None, arena=None):
        """Mirror of SQLite leaderboard. Any of (sharp, weapon, mode, arena)
        can be None to skip that dimension. When ALL four are None the
        result aggregates across every cell per-model (historic 'overall'
        view). See storage.py:LocalStorage.leaderboard for rationale."""
        params = {"order": "rating.desc"}
        if sharp:  params["sharp"]  = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if mode:   params["mode"]   = f"eq.{mode}"
        if arena:  params["arena"]  = f"eq.{arena}"
        if sharp or weapon or mode or arena:
            rows = self._rest("GET", "elo", params=params)
            return [dict(r) for r in rows]
        # No filters => aggregate per-model across every cell.
        rows = self._rest("GET", "elo", params=params)
        agg = {}
        for r in rows:
            a = agg.setdefault(r["model"], {
                "model": r["model"],
                "sharp": "ALL", "weapon": "ALL",
                "mode": "ALL", "arena": "ALL",
                "rating": [], "wins": 0, "losses": 0, "draws": 0})
            a["rating"].append(r["rating"])
            a["wins"] += r["wins"]; a["losses"] += r["losses"]; a["draws"] += r["draws"]
        out = []
        for a in agg.values():
            a["rating"] = sum(a["rating"]) / len(a["rating"])
            out.append(a)
        out.sort(key=lambda x: -x["rating"])
        return out

    # ============================================================
    # Tournaments (mirrors LocalStorage; Postgres tables in Supabase)
    # ============================================================
    def create_tournament(self, name, models, weapon, sharp, arena, mode):
        tid = uuid.uuid4().hex[:12]
        body = {
            "id": tid, "created": time.time(), "name": name,
            "size": len(models), "weapon": weapon,
            "sharp": ",".join(sharp), "arena": arena, "mode": mode,
            "status": "queued", "current_round": 0,
            "models": json.dumps(models),
        }
        self._rest("POST", "tournaments", body=body)
        return tid

    def set_tournament_status(self, tid, status, error=None):
        self._rest("PATCH", "tournaments", params={"id": f"eq.{tid}"},
                   body={"status": status, "error": error})

    def set_tournament_round(self, tid, round_n):
        self._rest("PATCH", "tournaments", params={"id": f"eq.{tid}"},
                   body={"current_round": round_n})

    def finish_tournament(self, tid, winner_model):
        self._rest("PATCH", "tournaments", params={"id": f"eq.{tid}"},
                   body={"status": "done", "winner_model": winner_model})

    def get_tournament(self, tid):
        rows = self._rest("GET", "tournaments", params={"id": f"eq.{tid}"})
        if not rows:
            return None
        t = dict(rows[0])
        try:
            t["models"] = json.loads(t["models"]) if t.get("models") else []
        except Exception:
            t["models"] = []
        ms = self._rest("GET", "tournament_matches", params={
            "tournament_id": f"eq.{tid}",
            "order": "round.asc,slot.asc"})
        t["matches"] = [dict(m) for m in (ms or [])]
        return t

    def recent_tournaments(self, limit=20):
        rows = self._rest("GET", "tournaments", params={
            "order": "created.desc", "limit": str(limit)})
        return [dict(r) for r in (rows or [])]

    def add_tournament_match(self, tid, round_n, slot, model_a, model_b):
        self._rest("POST", "tournament_matches", body={
            "tournament_id": tid, "round": round_n, "slot": slot,
            "model_a": model_a, "model_b": model_b})

    def bind_tournament_match(self, tid, round_n, slot, match_id):
        self._rest("PATCH", "tournament_matches",
                   params={"tournament_id": f"eq.{tid}",
                           "round": f"eq.{round_n}",
                           "slot":  f"eq.{slot}"},
                   body={"match_id": match_id})

    def set_tournament_match_winner(self, tid, round_n, slot, winner_model):
        self._rest("PATCH", "tournament_matches",
                   params={"tournament_id": f"eq.{tid}",
                           "round": f"eq.{round_n}",
                           "slot":  f"eq.{slot}"},
                   body={"winner_model": winner_model})
