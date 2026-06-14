"""Storage layer for the web arena.

Local backend: SQLite (matches, votes, Elo) + files (replay JSON).
The interface is intentionally tiny so a SupabaseStorage drop-in replacement
only has to implement these same methods (Postgres tables + Storage bucket).
"""
import json
import os
import sqlite3
import threading
import time
import uuid

K_FACTOR = 32
START_ELO = 1000.0


class LocalStorage:
    def __init__(self, root="arena_data"):
        self.root = root
        self.replay_dir = os.path.join(root, "replays")
        os.makedirs(self.replay_dir, exist_ok=True)
        self.db_path = os.path.join(root, "arena.db")
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY,
                created REAL,
                model_a TEXT, model_b TEXT,
                sharp TEXT,
                weapon TEXT DEFAULT 'sword',
                status TEXT,            -- queued | running | done | error
                winner_side TEXT,       -- a | b | draw | NULL  (canvas-side: a=green, b=blue)
                method TEXT,
                turns INTEGER,
                error TEXT,
                blind INTEGER DEFAULT 1,
                voted INTEGER DEFAULT 0,
                flip INTEGER DEFAULT 0  -- 1 = model_a was rendered as Fighter B (blue)
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                match_id TEXT, created REAL,
                choice TEXT              -- a | b | draw
            );
            CREATE TABLE IF NOT EXISTS elo (
                model TEXT,
                sharp TEXT,
                weapon TEXT DEFAULT 'sword',
                rating REAL,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                PRIMARY KEY (model, sharp, weapon)
            );
            """)
            # ------ idempotent migrations (so existing DBs pick up new cols)
            for ddl in [
                "ALTER TABLE matches ADD COLUMN weapon TEXT DEFAULT 'sword'",
                "ALTER TABLE matches ADD COLUMN flip   INTEGER DEFAULT 0",
                "ALTER TABLE elo     ADD COLUMN weapon TEXT DEFAULT 'sword'",
            ]:
                try:
                    c.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already there

    # ----------------------------------------------------------- matches
    def create_match(self, model_a, model_b, sharp, blind=True, weapon="sword"):
        mid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO matches (id, created, model_a, model_b, sharp,"
                " weapon, status, blind) VALUES (?,?,?,?,?,?,?,?)",
                (mid, time.time(), model_a, model_b, ",".join(sharp),
                 weapon, "queued", int(blind)))
        return mid

    def set_flip(self, mid, flip: bool):
        """Persist the random A↔green/B↔blue mapping for this match."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE matches SET flip=? WHERE id=?",
                      (1 if flip else 0, mid))

    def set_status(self, mid, status, error=None):
        with self._lock, self._conn() as c:
            c.execute("UPDATE matches SET status=?, error=? WHERE id=?",
                      (status, error, mid))

    def finish_match(self, mid, winner_side, method, turns, replay):
        path = os.path.join(self.replay_dir, mid + ".json")
        with open(path, "w") as f:
            json.dump(replay, f, separators=(",", ":"))
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE matches SET status='done', winner_side=?, method=?,"
                " turns=? WHERE id=?", (winner_side, method, turns, mid))

    def get_match(self, mid):
        with self._conn() as c:
            r = c.execute("SELECT * FROM matches WHERE id=?", (mid,)).fetchone()
        return dict(r) if r else None

    def get_replay(self, mid):
        path = os.path.join(self.replay_dir, mid + ".json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def recent_matches(self, limit=20):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM matches WHERE status='done'"
                " ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------- voting / elo
    def _get_elo(self, c, model, sharp, weapon):
        r = c.execute("SELECT rating FROM elo WHERE model=? AND sharp=? AND weapon=?",
                      (model, sharp, weapon)).fetchone()
        if r:
            return r["rating"]
        c.execute("INSERT INTO elo (model, sharp, weapon, rating) VALUES (?,?,?,?)",
                  (model, sharp, weapon, START_ELO))
        return START_ELO

    @staticmethod
    def _unflip_choice(choice, flip):
        """User clicked 'a'/'b' on the CANVAS (green/blue). Translate to the
        model_a/model_b axis stored in the matches row."""
        if choice == "draw":
            return "draw"
        if not flip:
            return choice
        return "a" if choice == "b" else "b"

    def record_vote(self, mid, choice):
        """choice: 'a' | 'b' | 'draw' (canvas-side). Updates Elo once per match."""
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        weapon = m.get("weapon") or "sword"
        flip = bool(m.get("flip"))
        a, b = m["model_a"], m["model_b"]
        # translate canvas vote -> model_a/model_b axis
        choice_model = self._unflip_choice(choice, flip)
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO votes (id, match_id, created, choice)"
                      " VALUES (?,?,?,?)",
                      (uuid.uuid4().hex[:12], mid, time.time(), choice))
            ra, rb = (self._get_elo(c, a, sharp, weapon),
                      self._get_elo(c, b, sharp, weapon))
            ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[choice_model]
            ra2 = ra + K_FACTOR * (sa - ea)
            rb2 = rb + K_FACTOR * ((1.0 - sa) - (1.0 - ea))
            wa, la, da = ("wins", "losses", "draws")
            W = "model=? AND sharp=? AND weapon=?"
            ax = (a, sharp, weapon)
            bx = (b, sharp, weapon)
            if choice_model == "a":
                c.execute(f"UPDATE elo SET rating=?, {wa}={wa}+1 WHERE {W}", (ra2, *ax))
                c.execute(f"UPDATE elo SET rating=?, {la}={la}+1 WHERE {W}", (rb2, *bx))
            elif choice_model == "b":
                c.execute(f"UPDATE elo SET rating=?, {la}={la}+1 WHERE {W}", (ra2, *ax))
                c.execute(f"UPDATE elo SET rating=?, {wa}={wa}+1 WHERE {W}", (rb2, *bx))
            else:
                c.execute(f"UPDATE elo SET rating=?, {da}={da}+1 WHERE {W}", (ra2, *ax))
                c.execute(f"UPDATE elo SET rating=?, {da}={da}+1 WHERE {W}", (rb2, *bx))
            c.execute("UPDATE matches SET voted=1 WHERE id=?", (mid,))
        return {"elo_change": {a: round(ra2 - ra, 1), b: round(rb2 - rb, 1)},
                **self.reveal(mid)}

    def reveal(self, mid):
        m = self.get_match(mid)
        flip = bool(m.get("flip"))
        # winner_side in the DB is canvas-side (a=green, b=blue).
        # The 'engine_winner_side' returned here is *also* canvas-side because
        # that's what the user sees and votes on. The reveal payload includes
        # the canvas→model mapping so the UI can show "Fighter A (green) was X".
        canvas_a_model = m["model_b"] if flip else m["model_a"]
        canvas_b_model = m["model_a"] if flip else m["model_b"]
        return {
            "model_a": m["model_a"],          # the user's first pick
            "model_b": m["model_b"],          # the user's second pick
            "canvas_a_model": canvas_a_model, # who fought as GREEN on the canvas
            "canvas_b_model": canvas_b_model, # who fought as BLUE on the canvas
            "engine_winner_side": m["winner_side"],
            "method": m["method"],
            "flip": flip,
            "weapon": m.get("weapon") or "sword",
        }

    def leaderboard(self, sharp=None, weapon=None):
        with self._conn() as c:
            where, params = [], []
            if sharp:
                where.append("sharp=?"); params.append(sharp)
            if weapon:
                where.append("weapon=?"); params.append(weapon)
            if where:
                rows = c.execute(
                    "SELECT * FROM elo WHERE " + " AND ".join(where) +
                    " ORDER BY rating DESC", params).fetchall()
            else:
                rows = c.execute(
                    "SELECT model, 'ALL' as sharp, 'ALL' as weapon,"
                    " AVG(rating) as rating,"
                    " SUM(wins) as wins, SUM(losses) as losses,"
                    " SUM(draws) as draws FROM elo GROUP BY model"
                    " ORDER BY rating DESC").fetchall()
        return [dict(r) for r in rows]
