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
                -- Mode (macro | joint) and arena (normal | ice | low_gravity)
                -- are part of the eval axis — different control regime or
                -- physics = different rating cell. Persisted per-match so
                -- votes update the RIGHT elo row instead of silently
                -- clobbering the (macro, normal) default. Both default to
                -- their "vanilla" values so any pre-existing INSERTs that
                -- don't set them behave exactly as before the migration.
                mode TEXT DEFAULT 'macro',
                arena TEXT DEFAULT 'normal',
                status TEXT,            -- queued | running | done | error
                winner_side TEXT,       -- a | b | draw | NULL  (canvas-side: a=green, b=blue)
                method TEXT,
                turns INTEGER,
                error TEXT,
                blind INTEGER DEFAULT 1,
                voted INTEGER DEFAULT 0,
                flip INTEGER DEFAULT 0, -- 1 = model_a was rendered as Fighter B (blue)
                commentary TEXT         -- post-fight 2-sentence commentary/roast
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                match_id TEXT, created REAL,
                choice TEXT              -- a | b | draw
            );
            -- Elo is segmented per (model, sharp, weapon, mode, arena). Prior
            -- schema had (model, sharp, weapon) — the mode/arena migration
            -- below promotes the PK for existing installs. Rows created
            -- before the migration are treated as (macro, normal), which
            -- is what production had been running all along.
            CREATE TABLE IF NOT EXISTS elo (
                model TEXT,
                sharp TEXT,
                weapon TEXT DEFAULT 'sword',
                mode TEXT DEFAULT 'macro',
                arena TEXT DEFAULT 'normal',
                rating REAL,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                PRIMARY KEY (model, sharp, weapon, mode, arena)
            );
            CREATE TABLE IF NOT EXISTS tournaments (
                id            TEXT PRIMARY KEY,
                created       REAL,
                name          TEXT,
                size          INTEGER,            -- 4 | 8
                weapon        TEXT DEFAULT 'sword',
                sharp         TEXT,               -- comma-joined zones
                arena         TEXT DEFAULT 'normal',
                mode          TEXT DEFAULT 'macro',
                status        TEXT,               -- queued | running | done | error
                current_round INTEGER DEFAULT 0,
                winner_model  TEXT,
                models        TEXT,               -- JSON array of model ids in seed order
                error         TEXT
            );
            CREATE TABLE IF NOT EXISTS tournament_matches (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id TEXT,
                round         INTEGER,
                slot          INTEGER,            -- position within the round (0..n-1)
                match_id      TEXT,               -- FK -> matches.id (NULL while pending)
                model_a       TEXT,
                model_b       TEXT,
                winner_model  TEXT,               -- model id of winner (NULL while pending)
                UNIQUE (tournament_id, round, slot)
            );
            """)
            # ------ idempotent migrations (so existing DBs pick up new cols)
            for ddl in [
                "ALTER TABLE matches ADD COLUMN weapon TEXT DEFAULT 'sword'",
                "ALTER TABLE matches ADD COLUMN flip   INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN commentary TEXT",
                "ALTER TABLE matches ADD COLUMN mode   TEXT DEFAULT 'macro'",
                "ALTER TABLE matches ADD COLUMN arena  TEXT DEFAULT 'normal'",
                "ALTER TABLE elo     ADD COLUMN weapon TEXT DEFAULT 'sword'",
                "ALTER TABLE elo     ADD COLUMN mode   TEXT DEFAULT 'macro'",
                "ALTER TABLE elo     ADD COLUMN arena  TEXT DEFAULT 'normal'",
            ]:
                try:
                    c.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already there
            # ------ PK promotion on `elo`: (model,sharp,weapon) -> +(mode,arena)
            # SQLite can't ALTER a PK. If the existing `elo` PK doesn't
            # include mode+arena, we rebuild the table (create-copy-swap)
            # inside a txn so a crash mid-migration doesn't leave a broken
            # schema. Detection: look at pragma index list to see if the
            # existing PK includes 'mode'.
            try:
                cols = c.execute("PRAGMA table_info(elo)").fetchall()
                pk_cols = {row["name"] for row in cols if row["pk"]}
                needs_promotion = "mode" not in pk_cols or "arena" not in pk_cols
            except sqlite3.OperationalError:
                needs_promotion = False
            if needs_promotion:
                # Backfill NULLs on any pre-existing rows so the composite
                # PK is well-defined (COALESCE isn't cheap; explicit UPDATE
                # runs once at migration time).
                c.execute("UPDATE elo SET mode  = COALESCE(mode,  'macro')")
                c.execute("UPDATE elo SET arena = COALESCE(arena, 'normal')")
                c.execute("UPDATE elo SET weapon= COALESCE(weapon,'sword')")
                # Recreate table with the correct PK, copy data, swap in.
                # NOTE: use individual c.execute() calls (NOT executescript)
                # because executescript() issues an implicit COMMIT that
                # conflicts with sqlite3's connection-level implicit txn
                # under `with self._conn() as c:`. The visible symptom was
                # the copied rows disappearing after the DROP. Individual
                # execute() calls run in the same txn cleanly.
                c.execute("""
                    CREATE TABLE elo_new (
                        model TEXT,
                        sharp TEXT,
                        weapon TEXT DEFAULT 'sword',
                        mode TEXT DEFAULT 'macro',
                        arena TEXT DEFAULT 'normal',
                        rating REAL,
                        wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                        draws INTEGER DEFAULT 0,
                        PRIMARY KEY (model, sharp, weapon, mode, arena)
                    )
                """)
                c.execute("""
                    INSERT INTO elo_new
                        (model, sharp, weapon, mode, arena, rating, wins, losses, draws)
                    SELECT
                        model, sharp, weapon,
                        COALESCE(mode,  'macro'),
                        COALESCE(arena, 'normal'),
                        rating, wins, losses, draws
                    FROM elo
                """)
                c.execute("DROP TABLE elo")
                c.execute("ALTER TABLE elo_new RENAME TO elo")
                # Force commit here so the rebuild is durable even if the
                # outer `with self._conn() as c:` context's implicit COMMIT
                # runs into weirdness with a mix of executescript + DDL
                # (Python sqlite3's txn semantics get confusing when a
                # single connection issues both script + statements).
                # Explicit commit = zero ambiguity, migration lands.
                c.commit()

    # ----------------------------------------------------------- matches
    def create_match(self, model_a, model_b, sharp, blind=True, weapon="sword",
                     mode="macro", arena="normal"):
        """Insert a new match. `mode` and `arena` default to the pre-Tier-S-
        commit-2 defaults (macro control, normal arena) so any caller that
        hasn't been updated behaves exactly as before. New callers should
        pass the actual mode/arena so votes route to the correct elo cell.
        """
        mid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO matches (id, created, model_a, model_b, sharp,"
                " weapon, mode, arena, status, blind)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (mid, time.time(), model_a, model_b, ",".join(sharp),
                 weapon, mode, arena, "queued", int(blind)))
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

    def finish_match(self, mid, winner_side, method, turns, replay,
                     commentary=None):
        path = os.path.join(self.replay_dir, mid + ".json")
        with open(path, "w") as f:
            json.dump(replay, f, separators=(",", ":"))
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE matches SET status='done', winner_side=?, method=?,"
                " turns=?, commentary=? WHERE id=?",
                (winner_side, method, turns, commentary, mid))

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

    def vote_rate_stats(self, window_days=7):
        """Compute vote-through rate: what fraction of completed matches
        get voted on? Powers the /api/stats/vote_rate endpoint that lets
        us diagnose the "people run matches but don't vote" problem
        surfaced pre-HN. Returns done/voted counts over the last
        `window_days` plus lifetime, so we can see if UI changes moved
        the needle.

        We measure over completed (status='done') matches only —
        pending/failed matches wouldn't produce a vote either way and
        shouldn't dilute the ratio. `voted=1` flips exactly once per
        match in `record_vote()` (self-play too), so it's a clean
        boolean per match. No PII, no BYOK residue — just two integers
        and a ratio."""
        import time as _time
        since = _time.time() - window_days * 86400
        with self._conn() as c:
            # Window (last N days)
            done_win = c.execute(
                "SELECT COUNT(*) FROM matches"
                " WHERE status='done' AND created >= ?", (since,)).fetchone()[0]
            voted_win = c.execute(
                "SELECT COUNT(*) FROM matches"
                " WHERE status='done' AND voted=1 AND created >= ?",
                (since,)).fetchone()[0]
            # Lifetime
            done_all = c.execute(
                "SELECT COUNT(*) FROM matches WHERE status='done'").fetchone()[0]
            voted_all = c.execute(
                "SELECT COUNT(*) FROM matches"
                " WHERE status='done' AND voted=1").fetchone()[0]
        return {
            "window_days": window_days,
            "window": {"done": done_win, "voted": voted_win,
                       "rate": round(voted_win / done_win, 4) if done_win else 0.0},
            "lifetime": {"done": done_all, "voted": voted_all,
                         "rate": round(voted_all / done_all, 4) if done_all else 0.0},
        }

    def head_to_head(self, a, b, limit=50):
        """Return VOTED done-matches where (model_a,model_b) is exactly the
        {a, b} pair (order-insensitive). Used by the wait-screen H2H card
        to show 'Llama is 2-1 in previous duels vs Qwen'.
        Returns a small aggregate + up to `limit` recent rows."""
        if not a or not b:
            return {"total": 0, "a_wins": 0, "b_wins": 0, "draws": 0,
                    "avg_turns": 0, "recent": []}
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, model_a, model_b, winner_side, method, turns,"
                " sharp, weapon, flip, voted, created FROM matches"
                " WHERE status='done'"
                "   AND ((model_a=? AND model_b=?) OR (model_a=? AND model_b=?))"
                " ORDER BY created DESC LIMIT ?",
                (a, b, b, a, limit)).fetchall()
        rows = [dict(r) for r in rows]
        aw = bw = dr = 0
        turns_total = 0
        for r in rows:
            turns_total += (r.get("turns") or 0)
            side = r.get("winner_side")   # canvas side "a"/"b"/"draw"
            if side == "draw":
                dr += 1
                continue
            flip = bool(r.get("flip"))
            # canvas side -> model_a/model_b axis of THIS row
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

    # ----------------------------------------------------------- voting / elo
    def _get_elo(self, c, model, sharp, weapon, mode="macro", arena="normal"):
        """Fetch or lazily-create the elo row for a specific eval cell.
        Cell key is (model, sharp, weapon, mode, arena) — see Tier-S
        commit 2 rationale in AGENTS.md §10.5."""
        r = c.execute("SELECT rating FROM elo WHERE model=? AND sharp=?"
                      " AND weapon=? AND mode=? AND arena=?",
                      (model, sharp, weapon, mode, arena)).fetchone()
        if r:
            return r["rating"]
        c.execute("INSERT INTO elo (model, sharp, weapon, mode, arena, rating)"
                  " VALUES (?,?,?,?,?,?)",
                  (model, sharp, weapon, mode, arena, START_ELO))
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
        # Pull mode + arena from the match row so votes route to the SAME
        # elo cell that the match was played under. Pre-Tier-S-commit-2
        # matches (no mode/arena set) fall back to the historic defaults
        # via COALESCE-in-Python; that's what those matches actually were.
        mode = m.get("mode") or "macro"
        arena = m.get("arena") or "normal"
        flip = bool(m.get("flip"))
        a, b = m["model_a"], m["model_b"]
        # translate canvas vote -> model_a/model_b axis
        choice_model = self._unflip_choice(choice, flip)
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO votes (id, match_id, created, choice)"
                      " VALUES (?,?,?,?)",
                      (uuid.uuid4().hex[:12], mid, time.time(), choice))
            # Self-play (mirror match): both fighters ARE the same row. Elo
            # delta must be zero (you can't beat yourself) and W/L would
            # double-update the same row and clobber. Log as a single draw.
            if a == b:
                self._get_elo(c, a, sharp, weapon, mode, arena)   # ensure row exists
                c.execute("UPDATE elo SET draws=draws+1 "
                          "WHERE model=? AND sharp=? AND weapon=?"
                          " AND mode=? AND arena=?",
                          (a, sharp, weapon, mode, arena))
                c.execute("UPDATE matches SET voted=1 WHERE id=?", (mid,))
                return {"elo_change": {a: 0.0}, **self.reveal(mid)}
            ra, rb = (self._get_elo(c, a, sharp, weapon, mode, arena),
                      self._get_elo(c, b, sharp, weapon, mode, arena))
            ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[choice_model]
            ra2 = ra + K_FACTOR * (sa - ea)
            rb2 = rb + K_FACTOR * ((1.0 - sa) - (1.0 - ea))
            # Column names ({wa}/{la}/{da}) and WHERE clause ({W}) are Python
            # string CONSTANTS defined here — never user input. User values
            # flow through the (ra2, *ax) params tuple (parameterized).
            # Bandit flags all of these as B608 SQL injection but they aren't;
            # B608 is globally skipped in .bandit for this reason.
            wa, la, da = ("wins", "losses", "draws")
            W = "model=? AND sharp=? AND weapon=? AND mode=? AND arena=?"
            ax = (a, sharp, weapon, mode, arena)
            bx = (b, sharp, weapon, mode, arena)
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
            "commentary": m.get("commentary") or "",
        }

    # ============================================================
    # Tournaments
    # ============================================================
    def create_tournament(self, name, models, weapon, sharp, arena, mode):
        tid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO tournaments (id, created, name, size, weapon,"
                " sharp, arena, mode, status, current_round, models)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (tid, time.time(), name, len(models), weapon,
                 ",".join(sharp), arena, mode, "queued", 0,
                 json.dumps(models)))
        return tid

    def set_tournament_status(self, tid, status, error=None):
        with self._lock, self._conn() as c:
            c.execute("UPDATE tournaments SET status=?, error=? WHERE id=?",
                      (status, error, tid))

    def set_tournament_round(self, tid, round_n):
        with self._lock, self._conn() as c:
            c.execute("UPDATE tournaments SET current_round=? WHERE id=?",
                      (round_n, tid))

    def finish_tournament(self, tid, winner_model):
        with self._lock, self._conn() as c:
            c.execute("UPDATE tournaments SET status='done', winner_model=?"
                      " WHERE id=?", (winner_model, tid))

    def get_tournament(self, tid):
        with self._conn() as c:
            r = c.execute("SELECT * FROM tournaments WHERE id=?",
                          (tid,)).fetchone()
            if not r:
                return None
            t = dict(r)
            t["models"] = json.loads(t["models"]) if t.get("models") else []
            matches = c.execute(
                "SELECT * FROM tournament_matches WHERE tournament_id=?"
                " ORDER BY round, slot", (tid,)).fetchall()
            t["matches"] = [dict(m) for m in matches]
        return t

    def recent_tournaments(self, limit=20):
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, name, status, winner_model, size, weapon,"
                " current_round, created FROM tournaments"
                " ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def add_tournament_match(self, tid, round_n, slot, model_a, model_b):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO tournament_matches"
                      " (tournament_id, round, slot, model_a, model_b)"
                      " VALUES (?,?,?,?,?)",
                      (tid, round_n, slot, model_a, model_b))

    def bind_tournament_match(self, tid, round_n, slot, match_id):
        with self._lock, self._conn() as c:
            c.execute("UPDATE tournament_matches SET match_id=?"
                      " WHERE tournament_id=? AND round=? AND slot=?",
                      (match_id, tid, round_n, slot))

    def set_tournament_match_winner(self, tid, round_n, slot, winner_model):
        with self._lock, self._conn() as c:
            c.execute("UPDATE tournament_matches SET winner_model=?"
                      " WHERE tournament_id=? AND round=? AND slot=?",
                      (winner_model, tid, round_n, slot))

    def leaderboard(self, sharp=None, weapon=None, mode=None, arena=None):
        """Leaderboard filter. Any of (sharp, weapon, mode, arena) can be
        None; None = don't filter on that dimension. When ALL four are
        None the query aggregates across every cell per-model (the
        historic 'overall' view). Any non-None combination returns the
        raw rows matching those filters.

        Tier-S commit 2: previously segmented by (sharp, weapon) only.
        Now supports (sharp, weapon, mode, arena) segmentation — mode
        and arena are legitimate eval axes (macro vs joint = totally
        different control regime; ice vs normal = totally different
        physics), and averaging across them was silent dishonesty."""
        with self._conn() as c:
            where, params = [], []
            if sharp:
                where.append("sharp=?"); params.append(sharp)
            if weapon:
                where.append("weapon=?"); params.append(weapon)
            if mode:
                where.append("mode=?"); params.append(mode)
            if arena:
                where.append("arena=?"); params.append(arena)
            if where:
                # 'where' only ever contains hardcoded strings ("sharp=?",
                # "weapon=?", "mode=?", "arena=?"); user values go through
                # the `params` tuple (parameterized). Bandit flags this as
                # B608 — globally skipped in .bandit for that reason.
                rows = c.execute(
                    "SELECT * FROM elo WHERE " + " AND ".join(where) +
                    " ORDER BY rating DESC", params).fetchall()
            else:
                rows = c.execute(
                    "SELECT model, 'ALL' as sharp, 'ALL' as weapon,"
                    " 'ALL' as mode, 'ALL' as arena,"
                    " AVG(rating) as rating,"
                    " SUM(wins) as wins, SUM(losses) as losses,"
                    " SUM(draws) as draws FROM elo GROUP BY model"
                    " ORDER BY rating DESC").fetchall()
        return [dict(r) for r in rows]
