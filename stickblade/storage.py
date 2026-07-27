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
                -- Tier S #3: blindfolded variant. When true, build_state()
                -- strips derived spatial booleans (facing_enemy, higher/
                -- lower/level) and forces the model to reason from raw
                -- coords. Separate rating cell = separate eval axis.
                blindfolded INTEGER DEFAULT 0,
                status TEXT,            -- queued | running | done | error
                winner_side TEXT,       -- a | b | draw | NULL  (canvas-side: a=green, b=blue)
                method TEXT,
                turns INTEGER,
                error TEXT,
                blind INTEGER DEFAULT 1,
                voted INTEGER DEFAULT 0,
                flip INTEGER DEFAULT 0, -- 1 = model_a was rendered as Fighter B (blue)
                commentary TEXT,        -- post-fight 2-sentence commentary/roast
                -- Tier S #3: automated proxy metrics computed from the
                -- replay event stream at finish_match() time. Powers the
                -- objective-skill leaderboard alongside human-vote Elo.
                -- All NULL if the replay didn't include a metrics dict
                -- (older code, malformed replay). See recorder._proxy_metrics.
                damage_dealt_a   REAL,
                damage_dealt_b   REAL,
                hits_landed_a    INTEGER,
                hits_landed_b    INTEGER,
                hits_attempted_a INTEGER,
                hits_attempted_b INTEGER,
                fallback_turns_a INTEGER,
                fallback_turns_b INTEGER,
                avg_distance     REAL
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                match_id TEXT, created REAL,
                choice TEXT              -- a | b | draw
            );
            -- Elo is segmented per (model, sharp, weapon, mode, arena,
            -- blindfolded). PK evolution documented in AGENTS.md §10.5
            -- ELO CELL KEY changelog. Pre-migration rows land at the
            -- (macro, normal, 0) defaults which is what every historical
            -- match was actually run under.
            CREATE TABLE IF NOT EXISTS elo (
                model TEXT,
                sharp TEXT,
                weapon TEXT DEFAULT 'sword',
                mode TEXT DEFAULT 'macro',
                arena TEXT DEFAULT 'normal',
                blindfolded INTEGER DEFAULT 0,
                rating REAL,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                PRIMARY KEY (model, sharp, weapon, mode, arena, blindfolded)
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
                # Tier S #1 → #2 legacy
                "ALTER TABLE matches ADD COLUMN weapon TEXT DEFAULT 'sword'",
                "ALTER TABLE matches ADD COLUMN flip   INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN commentary TEXT",
                "ALTER TABLE matches ADD COLUMN mode   TEXT DEFAULT 'macro'",
                "ALTER TABLE matches ADD COLUMN arena  TEXT DEFAULT 'normal'",
                "ALTER TABLE elo     ADD COLUMN weapon TEXT DEFAULT 'sword'",
                "ALTER TABLE elo     ADD COLUMN mode   TEXT DEFAULT 'macro'",
                "ALTER TABLE elo     ADD COLUMN arena  TEXT DEFAULT 'normal'",
                # Tier S #3: blindfolded variant + proxy metric columns
                "ALTER TABLE matches ADD COLUMN blindfolded      INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN damage_dealt_a   REAL",
                "ALTER TABLE matches ADD COLUMN damage_dealt_b   REAL",
                "ALTER TABLE matches ADD COLUMN hits_landed_a    INTEGER",
                "ALTER TABLE matches ADD COLUMN hits_landed_b    INTEGER",
                "ALTER TABLE matches ADD COLUMN hits_attempted_a INTEGER",
                "ALTER TABLE matches ADD COLUMN hits_attempted_b INTEGER",
                "ALTER TABLE matches ADD COLUMN fallback_turns_a INTEGER",
                "ALTER TABLE matches ADD COLUMN fallback_turns_b INTEGER",
                "ALTER TABLE matches ADD COLUMN avg_distance     REAL",
                "ALTER TABLE elo     ADD COLUMN blindfolded      INTEGER DEFAULT 0",
            ]:
                try:
                    c.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already there
            # ------ PK promotion on `elo`
            # PK evolution (see AGENTS.md §10.5 ELO CELL KEY changelog):
            #   original: (model, sharp)
            #   Tier S #1: (model, sharp, weapon)                   [pre-CI era]
            #   Tier S #2: (model, sharp, weapon, mode, arena)      [prior commit]
            #   Tier S #3: (model, sharp, weapon, mode, arena, blindfolded)  [this]
            # SQLite can't ALTER a PK. If the existing PK isn't the full
            # 6-tuple, rebuild the table (create-copy-swap) inside a txn.
            try:
                cols = c.execute("PRAGMA table_info(elo)").fetchall()
                pk_cols = {row["name"] for row in cols if row["pk"]}
                needs_promotion = ("mode" not in pk_cols or "arena" not in pk_cols
                                   or "blindfolded" not in pk_cols)
            except sqlite3.OperationalError:
                needs_promotion = False
            if needs_promotion:
                # Backfill NULLs on any pre-existing rows so the composite
                # PK is well-defined (explicit UPDATE runs once at
                # migration time — no per-vote COALESCE cost).
                c.execute("UPDATE elo SET mode        = COALESCE(mode,        'macro')")
                c.execute("UPDATE elo SET arena       = COALESCE(arena,       'normal')")
                c.execute("UPDATE elo SET weapon      = COALESCE(weapon,      'sword')")
                c.execute("UPDATE elo SET blindfolded = COALESCE(blindfolded, 0)")
                # Recreate table with the full 6-key PK, copy data, swap in.
                # NOTE: individual c.execute() calls (NOT executescript)
                # because executescript() issues an implicit COMMIT that
                # conflicts with sqlite3's connection-level implicit txn
                # under `with self._conn() as c:`. Learned in Tier S #2.
                c.execute("""
                    CREATE TABLE elo_new (
                        model TEXT,
                        sharp TEXT,
                        weapon TEXT DEFAULT 'sword',
                        mode TEXT DEFAULT 'macro',
                        arena TEXT DEFAULT 'normal',
                        blindfolded INTEGER DEFAULT 0,
                        rating REAL,
                        wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                        draws INTEGER DEFAULT 0,
                        PRIMARY KEY (model, sharp, weapon, mode, arena, blindfolded)
                    )
                """)
                c.execute("""
                    INSERT INTO elo_new
                        (model, sharp, weapon, mode, arena, blindfolded,
                         rating, wins, losses, draws)
                    SELECT
                        model, sharp, weapon,
                        COALESCE(mode,        'macro'),
                        COALESCE(arena,       'normal'),
                        COALESCE(blindfolded, 0),
                        rating, wins, losses, draws
                    FROM elo
                """)
                c.execute("DROP TABLE elo")
                c.execute("ALTER TABLE elo_new RENAME TO elo")
                # Explicit commit: defense-in-depth against Python
                # sqlite3's txn tracker getting confused after mixed DDL.
                c.commit()

    # ----------------------------------------------------------- matches
    def create_match(self, model_a, model_b, sharp, blind=True, weapon="sword",
                     mode="macro", arena="normal", blindfolded=False):
        """Insert a new match. mode/arena/blindfolded default to the
        historic defaults (macro control, normal arena, not blindfolded)
        so any caller that hasn't been updated behaves exactly as before.
        New callers pass explicit values so votes route to the correct
        elo cell.
        """
        mid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO matches (id, created, model_a, model_b, sharp,"
                " weapon, mode, arena, blindfolded, status, blind)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (mid, time.time(), model_a, model_b, ",".join(sharp),
                 weapon, mode, arena, int(bool(blindfolded)),
                 "queued", int(blind)))
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
        # Tier S #3: extract proxy metrics from replay.meta.metrics
        # and persist as top-level columns on `matches`. Kept optional
        # (COALESCE-safe) so a replay build that didn't include metrics
        # (older code paths, malformed replays) doesn't crash the finish.
        m = (replay.get("meta") or {}).get("metrics") or {}
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE matches SET status='done', winner_side=?, method=?,"
                " turns=?, commentary=?,"
                " damage_dealt_a=?, damage_dealt_b=?,"
                " hits_landed_a=?, hits_landed_b=?,"
                " hits_attempted_a=?, hits_attempted_b=?,"
                " fallback_turns_a=?, fallback_turns_b=?,"
                " avg_distance=?"
                " WHERE id=?",
                (winner_side, method, turns, commentary,
                 m.get("damage_dealt_a"),   m.get("damage_dealt_b"),
                 m.get("hits_landed_a"),    m.get("hits_landed_b"),
                 m.get("hits_attempted_a"), m.get("hits_attempted_b"),
                 m.get("fallback_turns_a"), m.get("fallback_turns_b"),
                 m.get("avg_distance"),
                 mid))

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
    def _get_elo(self, c, model, sharp, weapon, mode="macro", arena="normal",
                 blindfolded=0):
        """Fetch or lazily-create the elo row for a specific eval cell.
        Cell key is (model, sharp, weapon, mode, arena, blindfolded)
        — Tier S #3 extension of the #2 key. See AGENTS.md §10.5."""
        r = c.execute("SELECT rating FROM elo WHERE model=? AND sharp=?"
                      " AND weapon=? AND mode=? AND arena=? AND blindfolded=?",
                      (model, sharp, weapon, mode, arena, blindfolded)).fetchone()
        if r:
            return r["rating"]
        c.execute("INSERT INTO elo (model, sharp, weapon, mode, arena,"
                  " blindfolded, rating) VALUES (?,?,?,?,?,?,?)",
                  (model, sharp, weapon, mode, arena, blindfolded, START_ELO))
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
        # Pull mode + arena + blindfolded from the match row so votes
        # route to the SAME elo cell the match was played under. Pre-
        # migration matches (NULL fields) fall back to historic
        # defaults — macro/normal/not-blindfolded — because that's what
        # every historical match actually was.
        mode = m.get("mode") or "macro"
        arena = m.get("arena") or "normal"
        blindfolded = int(m.get("blindfolded") or 0)
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
                self._get_elo(c, a, sharp, weapon, mode, arena, blindfolded)
                c.execute("UPDATE elo SET draws=draws+1 "
                          "WHERE model=? AND sharp=? AND weapon=?"
                          " AND mode=? AND arena=? AND blindfolded=?",
                          (a, sharp, weapon, mode, arena, blindfolded))
                c.execute("UPDATE matches SET voted=1 WHERE id=?", (mid,))
                return {"elo_change": {a: 0.0}, **self.reveal(mid)}
            ra, rb = (self._get_elo(c, a, sharp, weapon, mode, arena, blindfolded),
                      self._get_elo(c, b, sharp, weapon, mode, arena, blindfolded))
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
            W = ("model=? AND sharp=? AND weapon=? AND mode=? AND arena=?"
                 " AND blindfolded=?")
            ax = (a, sharp, weapon, mode, arena, blindfolded)
            bx = (b, sharp, weapon, mode, arena, blindfolded)
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

    def objective_leaderboard(self, sharp=None, weapon=None, mode=None,
                              arena=None, blindfolded=None):
        """Objective-skill leaderboard — aggregates per-model proxy
        metrics across all completed matches (whether voted on or not).
        Independent of the human-vote Elo path. See Tier-S #3.

        For each model, computes:
          matches            total done matches this model played
          damage_per_turn    total damage dealt / total turns played
          hit_rate           hits_landed / hits_attempted (in [0, 1])
          fallback_rate      fallback_turns / total_turns (lower = better)
          avg_distance       mean of match-level avg_distance
          wins/losses/draws  from winner_side (only when voted, so N may
                             be lower than `matches`)

        Since a match has two fighters, each done match contributes to
        BOTH models' stats — model_a gets *_a fields, model_b gets *_b.
        Excludes matches where the metric column is NULL (pre-Tier-S-3
        matches don't have these fields populated).

        Filters mirror the vote-based leaderboard for consistency."""
        with self._conn() as c:
            where = ["status='done'", "damage_dealt_a IS NOT NULL"]
            params = []
            if sharp:  where.append("sharp=?");  params.append(sharp)
            if weapon: where.append("weapon=?"); params.append(weapon)
            if mode:   where.append("mode=?");   params.append(mode)
            if arena:  where.append("arena=?");  params.append(arena)
            if blindfolded is not None:
                where.append("blindfolded=?")
                params.append(int(bool(blindfolded)))
            # 'where' is hardcoded strings only; user values through `params`.
            # Bandit B608 false positive, globally skipped.
            rows = c.execute(
                "SELECT model_a, model_b, winner_side, turns,"
                " damage_dealt_a, damage_dealt_b,"
                " hits_landed_a, hits_landed_b,"
                " hits_attempted_a, hits_attempted_b,"
                " fallback_turns_a, fallback_turns_b,"
                " avg_distance"
                " FROM matches WHERE " + " AND ".join(where),
                params).fetchall()
        # Roll up per-model
        agg = {}
        for r in rows:
            r = dict(r)
            t = int(r["turns"] or 0)
            avg_d = float(r["avg_distance"] or 0.0)
            for side, model in (("a", r["model_a"]), ("b", r["model_b"])):
                m = agg.setdefault(model, {
                    "model": model, "matches": 0, "turns": 0,
                    "damage": 0.0, "hits_landed": 0, "hits_attempted": 0,
                    "fallback": 0, "distance_sum": 0.0,
                    "wins": 0, "losses": 0, "draws": 0,
                })
                m["matches"] += 1
                m["turns"] += t
                m["damage"] += float(r[f"damage_dealt_{side}"] or 0.0)
                m["hits_landed"] += int(r[f"hits_landed_{side}"] or 0)
                m["hits_attempted"] += int(r[f"hits_attempted_{side}"] or 0)
                m["fallback"] += int(r[f"fallback_turns_{side}"] or 0)
                m["distance_sum"] += avg_d
                # Convert canvas-side winner into model_a/model_b outcome.
                # Note: `winner_side` is canvas-side ("a"/"b"/"draw"),
                # and flip mapping isn't in this row. We DON'T unflip
                # here because objective metrics aren't tied to the
                # canvas-side vote — model_a always plays the model_a
                # role from the sim perspective. The winner_side maps
                # through flip in the storage vote path; for objective
                # W/L we treat winner_side as canvas which corresponds
                # to sim slot after flip resolution... this is the same
                # ambiguity the head_to_head query handles. Simplest
                # honest approach: only count W/L when winner_side is
                # NOT draw, and attribute the win to whichever side's
                # damage was higher. That's tautological to physics but
                # matches "who actually killed whom" which is what
                # objective means.
                pass
            # Attribute W/L by higher damage-dealt this match (physics-
            # authoritative, ignores flip / vote canvas mapping which
            # objective metrics shouldn't depend on).
            if (r["winner_side"] or "").lower() == "draw":
                agg[r["model_a"]]["draws"] += 1
                agg[r["model_b"]]["draws"] += 1
            else:
                da = float(r["damage_dealt_a"] or 0.0)
                db = float(r["damage_dealt_b"] or 0.0)
                if da > db:
                    agg[r["model_a"]]["wins"]   += 1
                    agg[r["model_b"]]["losses"] += 1
                elif db > da:
                    agg[r["model_b"]]["wins"]   += 1
                    agg[r["model_a"]]["losses"] += 1
                # equal damage on a non-draw match = physics tie; count draw
                else:
                    agg[r["model_a"]]["draws"] += 1
                    agg[r["model_b"]]["draws"] += 1
        # Finalize derived metrics
        out = []
        for m in agg.values():
            t = m["turns"] or 1
            att = m["hits_attempted"] or 1
            n = m["matches"] or 1
            out.append({
                "model": m["model"],
                "matches":         m["matches"],
                "damage_per_turn": round(m["damage"] / t, 2),
                "hit_rate":        round(m["hits_landed"] / att, 3),
                "fallback_rate":   round(m["fallback"] / t, 3),
                "avg_distance":    round(m["distance_sum"] / n, 1),
                "total_damage":    round(m["damage"], 1),
                "hits_landed":     m["hits_landed"],
                "hits_attempted":  m["hits_attempted"],
                "wins":            m["wins"],
                "losses":          m["losses"],
                "draws":           m["draws"],
            })
        # Default sort: damage_per_turn desc. Frontend can re-sort.
        out.sort(key=lambda x: -x["damage_per_turn"])
        return out

    def leaderboard(self, sharp=None, weapon=None, mode=None, arena=None,
                    blindfolded=None):
        """Leaderboard filter. Any of (sharp, weapon, mode, arena,
        blindfolded) can be None to skip that dimension. When ALL five
        are None the query aggregates across every cell per-model
        (historic 'overall' view).

        Tier-S #3: blindfolded added as 5th eval axis. The blindfolded
        variant strips derived spatial booleans from state — it's a
        different question the model is answering, so its Elo is not
        comparable to normal-mode Elo. Segmenting keeps the leaderboard
        honest.

        `blindfolded` filter accepts True/False/None (Python) or 1/0/None
        (int). We coerce to int here so callers can pass either shape."""
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
            if blindfolded is not None:
                where.append("blindfolded=?"); params.append(int(bool(blindfolded)))
            if where:
                # 'where' only ever contains hardcoded strings; user values
                # flow through `params`. Bandit B608 false positive, skipped
                # globally in .bandit.
                rows = c.execute(
                    "SELECT * FROM elo WHERE " + " AND ".join(where) +
                    " ORDER BY rating DESC", params).fetchall()
            else:
                rows = c.execute(
                    "SELECT model, 'ALL' as sharp, 'ALL' as weapon,"
                    " 'ALL' as mode, 'ALL' as arena, 0 as blindfolded,"
                    " AVG(rating) as rating,"
                    " SUM(wins) as wins, SUM(losses) as losses,"
                    " SUM(draws) as draws FROM elo GROUP BY model"
                    " ORDER BY rating DESC").fetchall()
        return [dict(r) for r in rows]
