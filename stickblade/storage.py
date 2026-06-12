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
                status TEXT,            -- queued | running | done | error
                winner_side TEXT,       -- a | b | draw | NULL
                method TEXT,
                turns INTEGER,
                error TEXT,
                blind INTEGER DEFAULT 1,
                voted INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                match_id TEXT, created REAL,
                choice TEXT              -- a | b | draw
            );
            CREATE TABLE IF NOT EXISTS elo (
                model TEXT, sharp TEXT, rating REAL,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                PRIMARY KEY (model, sharp)
            );
            """)

    # ----------------------------------------------------------- matches
    def create_match(self, model_a, model_b, sharp, blind=True):
        mid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO matches (id, created, model_a, model_b, sharp,"
                " status, blind) VALUES (?,?,?,?,?,?,?)",
                (mid, time.time(), model_a, model_b, ",".join(sharp),
                 "queued", int(blind)))
        return mid

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
    def _get_elo(self, c, model, sharp):
        r = c.execute("SELECT rating FROM elo WHERE model=? AND sharp=?",
                      (model, sharp)).fetchone()
        if r:
            return r["rating"]
        c.execute("INSERT INTO elo (model, sharp, rating) VALUES (?,?,?)",
                  (model, sharp, START_ELO))
        return START_ELO

    def record_vote(self, mid, choice):
        """choice: 'a' | 'b' | 'draw'. Updates Elo once per match."""
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        a, b = m["model_a"], m["model_b"]
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO votes (id, match_id, created, choice)"
                      " VALUES (?,?,?,?)",
                      (uuid.uuid4().hex[:12], mid, time.time(), choice))
            ra, rb = self._get_elo(c, a, sharp), self._get_elo(c, b, sharp)
            ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[choice]
            ra2 = ra + K_FACTOR * (sa - ea)
            rb2 = rb + K_FACTOR * ((1.0 - sa) - (1.0 - ea))
            wa, la, da = ("wins", "losses", "draws")
            if choice == "a":
                c.execute(f"UPDATE elo SET rating=?, {wa}={wa}+1 WHERE model=? AND sharp=?", (ra2, a, sharp))
                c.execute(f"UPDATE elo SET rating=?, {la}={la}+1 WHERE model=? AND sharp=?", (rb2, b, sharp))
            elif choice == "b":
                c.execute(f"UPDATE elo SET rating=?, {la}={la}+1 WHERE model=? AND sharp=?", (ra2, a, sharp))
                c.execute(f"UPDATE elo SET rating=?, {wa}={wa}+1 WHERE model=? AND sharp=?", (rb2, b, sharp))
            else:
                c.execute(f"UPDATE elo SET rating=?, {da}={da}+1 WHERE model=? AND sharp=?", (ra2, a, sharp))
                c.execute(f"UPDATE elo SET rating=?, {da}={da}+1 WHERE model=? AND sharp=?", (rb2, b, sharp))
            c.execute("UPDATE matches SET voted=1 WHERE id=?", (mid,))
        return {"elo_change": {a: round(ra2 - ra, 1), b: round(rb2 - rb, 1)},
                **self.reveal(mid)}

    def reveal(self, mid):
        m = self.get_match(mid)
        return {"model_a": m["model_a"], "model_b": m["model_b"],
                "engine_winner_side": m["winner_side"], "method": m["method"]}

    def leaderboard(self, sharp=None):
        with self._conn() as c:
            if sharp:
                rows = c.execute(
                    "SELECT * FROM elo WHERE sharp=? ORDER BY rating DESC",
                    (sharp,)).fetchall()
            else:
                rows = c.execute(
                    "SELECT model, 'ALL' as sharp, AVG(rating) as rating,"
                    " SUM(wins) as wins, SUM(losses) as losses,"
                    " SUM(draws) as draws FROM elo GROUP BY model"
                    " ORDER BY rating DESC").fetchall()
        return [dict(r) for r in rows]
