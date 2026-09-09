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
                avg_distance     REAL,
                -- ---- benchmark spec v1.0: per-match provenance ----
                -- Every published match is pinned to a version triple so
                -- cross-date leaderboard slices stay interpretable.
                benchmark_version TEXT,
                physics_version   TEXT,
                prompt_version    TEXT,
                spec_fingerprint  TEXT,
                seed              INTEGER,   -- NULL = unseeded (not reproducible)
                match_length      TEXT,      -- sprint | standard | full
                max_turns         INTEGER,
                fallback_policy   TEXT,      -- strict | operational | demo
                model_used_a      TEXT,      -- after buddy/fallback swaps
                model_used_b      TEXT,
                provider_used_a   TEXT,
                provider_used_b   TEXT,
                fallback_used     INTEGER DEFAULT 0,
                latency_ms_a      REAL,
                latency_ms_b      REAL,
                invalid_actions_a INTEGER DEFAULT 0,
                invalid_actions_b INTEGER DEFAULT 0,
                ranking_eligible  INTEGER DEFAULT 1,
                cancelled         INTEGER DEFAULT 0,
                -- Per-fighter damage attempt/landing split is in the replay;
                -- these denormalised copies power the public dashboard
                -- without re-reading multi-MB replay blobs.
                models_used_a     TEXT,      -- JSON {model_id: turns}
                models_used_b     TEXT
            );
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                match_id TEXT, created REAL,
                choice TEXT,             -- a | b | draw  (tactical; ranked)
                -- Separate vote axes (action-plan §6). Only `choice` feeds
                -- the ranking; the rest exist so we can measure the gap
                -- between "fought intelligently" and "was fun to watch".
                execution TEXT,          -- a | b | draw | NULL
                entertainment TEXT,
                deserved TEXT,
                confidence INTEGER       -- 1..5 self-reported, NULL = skipped
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_match_id ON votes(match_id);
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
                # ---- benchmark spec v1.0 provenance ----
                "ALTER TABLE matches ADD COLUMN benchmark_version TEXT",
                "ALTER TABLE matches ADD COLUMN physics_version   TEXT",
                "ALTER TABLE matches ADD COLUMN prompt_version    TEXT",
                "ALTER TABLE matches ADD COLUMN spec_fingerprint  TEXT",
                "ALTER TABLE matches ADD COLUMN seed              INTEGER",
                "ALTER TABLE matches ADD COLUMN match_length      TEXT",
                "ALTER TABLE matches ADD COLUMN max_turns         INTEGER",
                "ALTER TABLE matches ADD COLUMN fallback_policy   TEXT",
                "ALTER TABLE matches ADD COLUMN model_used_a      TEXT",
                "ALTER TABLE matches ADD COLUMN model_used_b      TEXT",
                "ALTER TABLE matches ADD COLUMN provider_used_a   TEXT",
                "ALTER TABLE matches ADD COLUMN provider_used_b   TEXT",
                "ALTER TABLE matches ADD COLUMN fallback_used     INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN latency_ms_a      REAL",
                "ALTER TABLE matches ADD COLUMN latency_ms_b      REAL",
                "ALTER TABLE matches ADD COLUMN invalid_actions_a INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN invalid_actions_b INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN ranking_eligible  INTEGER DEFAULT 1",
                "ALTER TABLE matches ADD COLUMN cancelled         INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN models_used_a     TEXT",
                "ALTER TABLE matches ADD COLUMN models_used_b     TEXT",
                # ---- multi-axis votes ----
                "ALTER TABLE votes ADD COLUMN execution      TEXT",
                "ALTER TABLE votes ADD COLUMN entertainment  TEXT",
                "ALTER TABLE votes ADD COLUMN deserved       TEXT",
                "ALTER TABLE votes ADD COLUMN confidence     INTEGER",
                # ---- §6 expert-evaluator track ----
                "ALTER TABLE votes ADD COLUMN voter_tier     TEXT DEFAULT 'casual'",
                # ---- §33 cost accounting (provider-reported tokens) ----
                "ALTER TABLE matches ADD COLUMN prompt_tokens_a     INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN completion_tokens_a INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN prompt_tokens_b     INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN completion_tokens_b INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN api_calls_a         INTEGER DEFAULT 0",
                "ALTER TABLE matches ADD COLUMN api_calls_b         INTEGER DEFAULT 0",
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
                     mode="macro", arena="normal", blindfolded=False,
                     seed=None, match_length="full", max_turns=None,
                     fallback_policy="operational"):
        """Insert a new match. mode/arena/blindfolded default to the
        historic defaults (macro control, normal arena, not blindfolded)
        so any caller that hasn't been updated behaves exactly as before.
        New callers pass explicit values so votes route to the correct
        elo cell.

        benchmark spec v1.0: the provenance knobs (seed, match_length,
        fallback_policy) are recorded at CREATION time, not at finish —
        a match that dies mid-flight still leaves an auditable record of
        what it was supposed to be.
        """
        from benchmark import (max_turns_for, FALLBACK_POLICIES,
                               DEFAULT_FALLBACK_POLICY, MATCH_LENGTHS,
                               DEFAULT_MATCH_LENGTH, BENCHMARK_VERSION,
                               PHYSICS_VERSION, SPEC_FINGERPRINT)
        from brains import PROMPT_VERSION
        mid = uuid.uuid4().hex[:12]
        ml = (match_length or DEFAULT_MATCH_LENGTH).lower()
        if ml not in MATCH_LENGTHS:
            ml = DEFAULT_MATCH_LENGTH
        pol = fallback_policy if fallback_policy in FALLBACK_POLICIES \
            else DEFAULT_FALLBACK_POLICY
        # A demo-policy or strict-policy match starts ineligible only once
        # we know whether a fallback happened; demo is ineligible up front.
        eligible = 0 if pol == "demo" else 1
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO matches (id, created, model_a, model_b, sharp,"
                " weapon, mode, arena, blindfolded, status, blind,"
                " benchmark_version, physics_version, prompt_version,"
                " spec_fingerprint, seed, match_length, max_turns,"
                " fallback_policy, ranking_eligible)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, time.time(), model_a, model_b, ",".join(sharp),
                 weapon, mode, arena, int(bool(blindfolded)),
                 "queued", int(blind),
                 BENCHMARK_VERSION, PHYSICS_VERSION, str(PROMPT_VERSION),
                 SPEC_FINGERPRINT, seed, ml,
                 int(max_turns) if max_turns else max_turns_for(ml),
                 pol, eligible))
        return mid

    def cancel_match(self, mid):
        """User-initiated cancel (action-plan §13).

        Marks the row cancelled + errored; the worker checks the flag and
        stops. Only queued/running matches can be cancelled — a finished
        match is immutable (its result is published data).
        """
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE matches SET cancelled=1, status='error',"
                " error='cancelled by user'"
                " WHERE id=? AND status IN ('queued','running')", (mid,))
            return cur.rowcount > 0

    def is_cancelled(self, mid):
        with self._conn() as c:
            r = c.execute("SELECT cancelled FROM matches WHERE id=?",
                          (mid,)).fetchone()
        return bool(r and r["cancelled"])

    def set_provenance(self, mid, prov: dict):
        """Persist the outcome-side provenance (model actually used,
        provider, latency, fallback, invalid actions, eligibility)."""
        if not prov:
            return
        def _j(v):
            try:
                return json.dumps(v) if v else None
            except (TypeError, ValueError):
                return None
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE matches SET model_used_a=?, model_used_b=?,"
                " provider_used_a=?, provider_used_b=?,"
                " fallback_used=?, latency_ms_a=?, latency_ms_b=?,"
                " invalid_actions_a=?, invalid_actions_b=?,"
                " ranking_eligible=?, models_used_a=?, models_used_b=?,"
                " prompt_tokens_a=?, completion_tokens_a=?,"
                " prompt_tokens_b=?, completion_tokens_b=?,"
                " api_calls_a=?, api_calls_b=?"
                " WHERE id=?",
                (prov.get("model_used_a"), prov.get("model_used_b"),
                 prov.get("provider_used_a"), prov.get("provider_used_b"),
                 int(bool(prov.get("fallback_used"))),
                 prov.get("latency_ms_a"), prov.get("latency_ms_b"),
                 int(prov.get("invalid_actions_a") or 0),
                 int(prov.get("invalid_actions_b") or 0),
                 int(bool(prov.get("ranking_eligible", True))),
                 _j(prov.get("models_used_a")), _j(prov.get("models_used_b")),
                 # §33: what the providers actually billed. Zero (not NULL)
                 # when a provider does not report usage, so a cost rollup
                 # cannot accidentally treat "unreported" as "free".
                 int(prov.get("prompt_tokens_a") or 0),
                 int(prov.get("completion_tokens_a") or 0),
                 int(prov.get("prompt_tokens_b") or 0),
                 int(prov.get("completion_tokens_b") or 0),
                 int(prov.get("api_calls_a") or 0),
                 int(prov.get("api_calls_b") or 0),
                 mid))

    def metrics_snapshot(self):
        """Observability rollup (action-plan §19).

        Cheap aggregate queries over the matches table — no replay blobs
        touched, so this is safe to poll every few seconds from a status
        page. Returns counts by status, completion/error/fallback/vote
        rates, and latency percentiles over the last 24h + lifetime.
        """
        import time as _time
        since = _time.time() - 86400
        with self._conn() as c:
            def _cnt(where="", params=()):
                return c.execute(
                    "SELECT COUNT(*) FROM matches WHERE 1=1 " + where,
                    tuple(params)).fetchone()[0]
            total = _cnt()
            done = _cnt("AND status='done'")
            err = _cnt("AND status='error'")
            running = _cnt("AND status IN ('queued','running')")
            voted = _cnt("AND voted=1")
            fb = _cnt("AND fallback_used=1")
            ineligible = _cnt("AND ranking_eligible=0")
            day_done = _cnt("AND status='done' AND created>=?", (since,))
            day_err = _cnt("AND status='error' AND created>=?", (since,))
            lats = [r[0] for r in c.execute(
                "SELECT latency_ms_a FROM matches WHERE latency_ms_a"
                " IS NOT NULL AND created>=?", (since,)).fetchall()]
            lats += [r[0] for r in c.execute(
                "SELECT latency_ms_b FROM matches WHERE latency_ms_b"
                " IS NOT NULL AND created>=?", (since,)).fetchall()]
            votes = c.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
        lats = sorted(x for x in lats if x is not None)

        def _pct(p):
            if not lats:
                return None
            return round(lats[min(len(lats) - 1, int(p * len(lats)))], 1)
        return {
            "matches": {"total": total, "done": done, "error": err,
                        "queued_or_running": running, "voted": voted,
                        "fallback_used": fb, "ranking_ineligible": ineligible,
                        "votes": votes},
            "rates": {
                "completion": round(done / total, 4) if total else 0.0,
                "error": round(err / total, 4) if total else 0.0,
                "failure_24h": round(day_err / day_done + day_err, 4)
                               if (day_done + day_err) else 0.0,
                "fallback": round(fb / done, 4) if done else 0.0,
                "vote_through": round(voted / done, 4) if done else 0.0,
            },
            "latency_ms_24h": {"n": len(lats), "p50": _pct(0.50),
                               "p90": _pct(0.90), "p95": _pct(0.95),
                               "max": round(lats[-1], 1) if lats else None},
            "matches_24h": {"done": day_done, "error": day_err},
        }

    def set_flip(self, mid, flip: bool):
        """Persist the random A↔green/B↔blue mapping for this match."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE matches SET flip=? WHERE id=?",
                      (1 if flip else 0, mid))

    def set_status(self, mid, status, error=None):
        with self._lock, self._conn() as c:
            c.execute("UPDATE matches SET status=?, error=? WHERE id=?",
                      (status, error, mid))

    def cleanup_stale_matches(self, error_msg="Server restarted while match was in progress"):
        """Clean up matches that were left in 'queued' or 'running' state across server restarts."""
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE matches SET status='error', error=? "
                "WHERE status IN ('queued', 'running')",
                (error_msg,))

    def finish_match(self, mid, winner_side, method, turns, replay,
                     commentary=None, provenance=None):
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
        # benchmark spec v1.0: persist the outcome-side provenance
        # (model/provider actually used, latency, fallback, invalid
        # actions, ranking eligibility).
        if provenance:
            self.set_provenance(mid, provenance)

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

    def export_matches(self, since=None, until=None, limit=10000,
                       include_votes=True):
        """Tier-A #3: bulk export of completed matches for the dataset
        dump. Powers /api/export and the eventual daily HF Datasets
        snapshot (huggingface.co/datasets/Pioneer37/stickblade-matches).

        Returns a list of match dicts, each augmented with:
          * `prompt_version` — pinned per-match from PROMPT_VERSION at
            finish time, so cross-version leaderboard slices stay honest
          * `votes` — list of votes on this match (if include_votes)

        Filters:
          * `since` / `until` — unix epoch bounds on matches.created;
            None means unbounded on that side
          * `limit` — hard cap to keep the query bounded even under
            HN-frontpage load. 10k is well above any realistic daily
            volume; if we ever hit it we paginate

        No PII in matches (model IDs, sharp zones, weapon, arena, mode,
        blindfolded, timings, proxy metrics, winner, commentary). Votes
        are anonymous (id + match_id + created + choice — no IP, no
        user id, we don't track those).

        Deliberately DOES NOT include replay JSON blobs — those live in
        the replays/ storage bucket and are per-match multi-MB. Exposing
        them via this endpoint would balloon the response and OOM the
        HF Space. Consumers who want a specific replay call the existing
        /api/replay/{mid} endpoint per-id after seeing the match in the
        export.
        """
        from brains import PROMPT_VERSION
        where = ["status='done'"]
        params = []
        if since is not None:
            where.append("created >= ?"); params.append(float(since))
        if until is not None:
            where.append("created <= ?"); params.append(float(until))
        params.append(int(limit))
        with self._conn() as c:
            # Same B608 comment as elsewhere — 'where' is hardcoded
            # strings, user values through params tuple. Bandit-skipped
            # globally in .bandit for this reason.
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM matches WHERE " + " AND ".join(where) +
                " ORDER BY created ASC LIMIT ?", params).fetchall()]
            if include_votes and rows:
                mids = tuple(r["id"] for r in rows)
                # sqlite3 IN () with a tuple needs len() placeholders
                placeholders = ",".join("?" * len(mids))
                vrows = [dict(v) for v in c.execute(
                    f"SELECT id, match_id, created, choice, execution,"
                    f" entertainment, deserved, confidence,"
                    f" COALESCE(voter_tier,'casual') AS voter_tier FROM votes"
                    f" WHERE match_id IN ({placeholders})", mids).fetchall()]
                by_mid = {}
                for v in vrows:
                    by_mid.setdefault(v["match_id"], []).append(v)
                for r in rows:
                    r["votes"] = by_mid.get(r["id"], [])
                    r["prompt_version"] = PROMPT_VERSION
            else:
                for r in rows:
                    r["prompt_version"] = PROMPT_VERSION
        return rows

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

    def record_vote(self, mid, choice, axes=None, confidence=None,
                    voter_tier="casual"):
        """Record a vote. Updates Elo once per match.

        choice      'a' | 'b' | 'draw' (canvas-side) — the TACTICAL vote.
                    This is the only axis that moves a rating.
        axes        optional dict with any of execution / entertainment /
                    deserved  ('a'|'b'|'draw'), collected separately so we
                    can measure tactical quality vs entertainment value
                    instead of silently conflating them (action-plan §6).
        confidence  optional int 1-5, self-reported certainty.
        voter_tier  'casual' (default) or 'expert' — self-declared. Stored,
                    never mixed: an expert vote and a casual vote are
                    different measurements of the same match, and pooling
                    them silently would let a small expert sample be
                    drowned out (or, worse, presented as if it were the
                    public's verdict). Both are always separable by filter.

        Ranking eligibility: matches flagged ineligible (strict policy with
        a fallback, or demo matches) still record the vote and reveal the
        models, but do NOT move Elo. The payload says so explicitly.
        """
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m["voted"]:
            return {"already_voted": True, **self.reveal(mid)}
        axes = axes or {}
        def _axis(name):
            v = axes.get(name)
            return v if v in ("a", "b", "draw") else None
        try:
            conf = int(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            conf = None
        if conf is not None:
            conf = max(1, min(5, conf))
        # Anything not explicitly "expert" is casual. We do not verify the
        # claim — there is no identity here — which is exactly why the tier
        # is reported alongside the numbers rather than used to override
        # them.
        tier = "expert" if str(voter_tier or "").lower() == "expert" else "casual"
        self._insert_vote(mid, choice, _axis("execution"),
                          _axis("entertainment"), _axis("deserved"), conf,
                          tier)
        if int(m.get("ranking_eligible") if m.get("ranking_eligible") is not None
               else 1) == 0:
            # Recorded, revealed, but deliberately unranked.
            with self._lock, self._conn() as c:
                c.execute("UPDATE matches SET voted=1 WHERE id=?", (mid,))
            return {"elo_change": {}, "ranking_excluded": True,
                    "exclusion_reason": self._exclusion_reason(m),
                    **self.reveal(mid)}
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

    def _insert_vote(self, mid, choice, execution=None, entertainment=None,
                     deserved=None, confidence=None, voter_tier="casual"):
        """Persist one vote row, carrying every axis we collect."""
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO votes (id, match_id, created, choice,"
                      " execution, entertainment, deserved, confidence,"
                      " voter_tier)"
                      " VALUES (?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:12], mid, time.time(), choice,
                       execution, entertainment, deserved, confidence,
                       voter_tier))

    @staticmethod
    def _exclusion_reason(m):
        """Human-readable why-this-match-isn't-ranked string."""
        pol = m.get("fallback_policy") or "operational"
        if pol == "demo":
            return "demo match (scripted fighters) — not ranked"
        if pol == "strict" and m.get("fallback_used"):
            return ("strict fallback policy: a provider fallback occurred, "
                    "so this match is excluded from rankings")
        return "excluded from rankings"

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
          hit_rate           hits_landed / hits_attempted. NOT a rate in
                             [0,1]: hit events are counted per contact while
                             attempts are counted per decision, so macro
                             bouts can exceed 1.0. See METHODOLOGY.md and
                             the "Hits/atk" label the UI already uses.
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
                "SELECT model_a, model_b, flip, winner_side, turns,"
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
            flip = bool(r.get("flip"))
            # Canvas side 'a' is model_b if flipped, else model_a.
            # Canvas side 'b' is model_a if flipped, else model_b.
            side_a_model = r["model_b"] if flip else r["model_a"]
            side_b_model = r["model_a"] if flip else r["model_b"]

            for side, model in (("a", side_a_model), ("b", side_b_model)):
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

            # Attribute W/L by higher damage-dealt this match (physics-authoritative)
            # un-flipping correctly for model_a vs model_b.
            if (r["winner_side"] or "").lower() == "draw":
                agg[r["model_a"]]["draws"] += 1
                agg[r["model_b"]]["draws"] += 1
            else:
                da = float((r["damage_dealt_b"] if flip else r["damage_dealt_a"]) or 0.0)
                db = float((r["damage_dealt_a"] if flip else r["damage_dealt_b"]) or 0.0)
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

    def preference_pairs(self, sharp=None, weapon=None, mode=None, arena=None,
                         blindfolded=None, tier=None):
        """Voted matches as `(model_a, model_b, flip, choice)` rows.

        This is the input to the Bradley-Terry fit (action-plan §5). It
        returns the RAW per-match vote rows rather than pre-aggregated
        counts, because the rating model needs to resample matches for its
        bootstrap intervals — you cannot bootstrap from a summary.

        Only ranking-eligible, finished, voted matches are included: the
        same exclusion rules the Elo path applies.
        """
        with self._conn() as c:
            where, params = ["m.status='done'", "m.voted=1"], []
            if tier in ("casual", "expert"):
                # §6: expert and casual votes are stored separately and are
                # never pooled silently. See docs/API.md.
                where.append("COALESCE(v.voter_tier,'casual')=?")
                params.append(tier)
            if sharp:
                where.append("m.sharp=?"); params.append(sharp)
            if weapon:
                where.append("m.weapon=?"); params.append(weapon)
            if mode:
                where.append("m.mode=?"); params.append(mode)
            if arena:
                where.append("m.arena=?"); params.append(arena)
            if blindfolded is not None:
                where.append("m.blindfolded=?")
                params.append(int(bool(blindfolded)))
            # One row per match: the tactical vote is the ranked axis, so a
            # match with several vote rows (older data) still counts once —
            # we take the most recent vote for that match.
            rows = c.execute(
                "SELECT m.model_a, m.model_b, m.flip, v.choice,"
                "       COALESCE(m.ranking_eligible, 1) AS ranking_eligible,"
                "       m.created, m.match_length"
                " FROM matches m JOIN votes v ON v.match_id = m.id"
                " WHERE " + " AND ".join(where) +
                " GROUP BY m.id HAVING v.created = MAX(v.created)"
                " ORDER BY m.created", params).fetchall()
        return [dict(r) for r in rows]

    # Columns the data-quality classifier needs (data_quality.py). Kept as a
    # module constant so the Supabase mirror selects exactly the same set.
    QUALITY_COLUMNS = (
        "id, created, status, model_a, model_b, flip, sharp, weapon, mode,"
        " arena, blindfolded, benchmark_version, fallback_policy,"
        " model_used_a, model_used_b, provider_used_a, provider_used_b,"
        " fallback_used, ranking_eligible, prompt_tokens_a, prompt_tokens_b,"
        " completion_tokens_a, completion_tokens_b, api_calls_a, api_calls_b"
    )

    def quality_rows(self, sharp=None, weapon=None, mode=None, arena=None,
                     blindfolded=None, limit=50000):
        """Finished match rows, provenance columns only, for data-quality
        labelling (next-step priority 2). Same five-axis filter as the
        leaderboards so the labels describe the cell being displayed."""
        with self._conn() as c:
            where, params = ["status='done'"], []
            if sharp:  where.append("sharp=?");  params.append(sharp)
            if weapon: where.append("weapon=?"); params.append(weapon)
            if mode:   where.append("mode=?");   params.append(mode)
            if arena:  where.append("arena=?");  params.append(arena)
            if blindfolded is not None:
                where.append("blindfolded=?")
                params.append(int(bool(blindfolded)))
            params.append(int(limit))
            rows = c.execute(
                "SELECT " + self.QUALITY_COLUMNS + " FROM matches WHERE "
                + " AND ".join(where) + " ORDER BY created ASC LIMIT ?",
                params).fetchall()
        return [dict(r) for r in rows]

    def model_stats(self, sharp=None, weapon=None, mode=None, arena=None,
                    blindfolded=None):
        """Full per-model metric table (action-plan §5).

        Everything the plan asks to publish beside a rating, computed from
        the match rows: win rate (physics), human preference rate (votes),
        damage/turn, lethal-hit rate, survival rate, timeout rate,
        invalid-action rate, mean latency, fallback rate, and per-model
        win/loss/draw counts. `objective_leaderboard()` is a subset of this
        kept for backwards compatibility with the existing UI tab.

        Two rates are easy to misread, so they are defined here rather than
        left to the reader: `hit_rate` can exceed 1.0 (contact events per
        decision, not a probability), and `lethal_rate` counts only kills —
        a model that wins by HP attrition has lethal_rate 0 and a high
        win_rate, which is correct, not a bug.
        """
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
            rows = c.execute(
                "SELECT id, model_a, model_b, flip, winner_side, method, turns,"
                " max_turns, damage_dealt_a, damage_dealt_b,"
                " hits_landed_a, hits_landed_b, hits_attempted_a,"
                " hits_attempted_b, fallback_turns_a, fallback_turns_b,"
                " latency_ms_a, latency_ms_b, invalid_actions_a,"
                " invalid_actions_b, fallback_used, voted,"
                " COALESCE(ranking_eligible, 1) AS ranking_eligible"
                " FROM matches WHERE " + " AND ".join(where),
                params).fetchall()
            # Votes, keyed by match id, for the preference rate.
            votes = {}
            try:
                for v in c.execute(
                        "SELECT match_id, choice FROM votes").fetchall():
                    votes[v["match_id"]] = (v["choice"] or "").lower()
            except Exception:
                pass

        out = {}
        for r in rows:
            r = dict(r)
            t = max(1, int(r.get("turns") or 1))
            flip = bool(r.get("flip"))
            side_a = r["model_b"] if flip else r["model_a"]
            side_b = r["model_a"] if flip else r["model_b"]
            lethal = (r.get("method") or "") == "kill"
            timeout = (r.get("method") or "").startswith("timeout")
            for side, model in (("a", side_a), ("b", side_b)):
                m = out.setdefault(model, {
                    "model": model, "matches": 0, "turns": 0,
                    "damage": 0.0, "hits_landed": 0, "hits_attempted": 0,
                    "fallback_turns": 0, "invalid_actions": 0,
                    "latency_sum": 0.0, "latency_max": 0.0,
                    "lethal_hits": 0, "survived": 0, "timeouts": 0,
                    "wins": 0, "losses": 0, "draws": 0,
                    "preferred": 0, "voted_matches": 0,
                    "fallback_matches": 0,
                })
                m["matches"] += 1
                m["turns"] += t
                m["damage"] += float(r.get(f"damage_dealt_{side}") or 0.0)
                m["hits_landed"] += int(r.get(f"hits_landed_{side}") or 0)
                m["hits_attempted"] += int(r.get(f"hits_attempted_{side}") or 0)
                m["fallback_turns"] += int(r.get(f"fallback_turns_{side}") or 0)
                m["invalid_actions"] += int(r.get(f"invalid_actions_{side}") or 0)
                lat = float(r.get(f"latency_ms_{side}") or 0.0)
                m["latency_sum"] += lat
                m["latency_max"] = max(m["latency_max"], lat)
                winner_side = (r.get("winner_side") or "").lower()
                # A kill is credited to the side that landed it; survival is
                # "did not die", which is only false for the loser of a kill.
                if lethal and winner_side == side:
                    m["lethal_hits"] += 1
                if not (lethal and winner_side != side):
                    m["survived"] += 1
                if timeout:
                    m["timeouts"] += 1
                if r.get("fallback_used"):
                    m["fallback_matches"] += 1
                # physics result on this side
                if winner_side == "draw":
                    m["draws"] += 1
                elif winner_side == side:
                    m["wins"] += 1
                else:
                    m["losses"] += 1
                # human preference (only voted, ranking-eligible matches)
                choice = votes.get(r.get("id"))
                if choice and r.get("ranking_eligible"):
                    m["voted_matches"] += 1
                    if choice == side:
                        m["preferred"] += 1
                    elif choice == "draw":
                        m["preferred"] += 0.5

        rows_out = []
        for m in out.values():
            n = m["matches"] or 1
            turns = m["turns"] or 1
            att = m["hits_attempted"] or 1
            decided = (m["wins"] + m["losses"]) or 1
            rows_out.append({
                "model": m["model"],
                "matches": m["matches"],
                "wins": m["wins"], "losses": m["losses"], "draws": m["draws"],
                "win_rate": round(m["wins"] / decided, 3),
                "preference_rate": (round(m["preferred"] / m["voted_matches"], 3)
                                    if m["voted_matches"] else None),
                "voted_matches": m["voted_matches"],
                "damage_per_turn": round(m["damage"] / turns, 2),
                "hit_rate": round(m["hits_landed"] / att, 3),
                "lethal_rate": round(m["lethal_hits"] / n, 3),
                "survival_rate": round(m["survived"] / n, 3),
                "timeout_rate": round(m["timeouts"] / n, 3),
                "invalid_action_rate": round(m["invalid_actions"] / turns, 3),
                "fallback_rate": round(m["fallback_turns"] / turns, 3),
                "fallback_match_rate": round(m["fallback_matches"] / n, 3),
                "latency_ms_mean": round(m["latency_sum"] / n, 1),
                "latency_ms_max": round(m["latency_max"], 1),
                "hits_landed": m["hits_landed"],
                "hits_attempted": m["hits_attempted"],
            })
        rows_out.sort(key=lambda x: -(x["win_rate"] or 0))
        return rows_out

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
