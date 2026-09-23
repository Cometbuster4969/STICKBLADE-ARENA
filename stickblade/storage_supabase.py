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
                     mode="macro", arena="normal", blindfolded=False,
                     seed=None, match_length="full", max_turns=None,
                     fallback_policy="operational"):
        """Create a match row, carrying the benchmark-spec provenance.

        The version triple + seed + length + fallback policy are recorded at
        CREATION time (not finish) so a match that dies mid-flight still
        leaves an auditable record of what it was meant to be. Unknown
        columns are stripped and retried, so an un-migrated Supabase schema
        keeps working — the provenance fields are additive.
        """
        from benchmark import (BENCHMARK_VERSION, PHYSICS_VERSION,
                               SPEC_FINGERPRINT, max_turns_for,
                               FALLBACK_POLICIES, DEFAULT_FALLBACK_POLICY,
                               MATCH_LENGTHS, DEFAULT_MATCH_LENGTH)
        from brains import PROMPT_VERSION
        mid = uuid.uuid4().hex[:12]
        ml = (match_length or DEFAULT_MATCH_LENGTH).lower()
        if ml not in MATCH_LENGTHS:
            ml = DEFAULT_MATCH_LENGTH
        pol = fallback_policy if fallback_policy in FALLBACK_POLICIES \
            else DEFAULT_FALLBACK_POLICY
        body = {
            "id": mid, "created": time.time(),
            "model_a": model_a, "model_b": model_b,
            "sharp": ",".join(sharp), "weapon": weapon,
            "mode": mode, "arena": arena, "blindfolded": bool(blindfolded),
            "status": "queued",
            "blind": bool(blind), "voted": False, "flip": False,
            # ---- benchmark spec v1.0 provenance ----
            "benchmark_version": BENCHMARK_VERSION,
            "physics_version": PHYSICS_VERSION,
            "prompt_version": str(PROMPT_VERSION),
            "spec_fingerprint": SPEC_FINGERPRINT,
            "seed": seed,
            "match_length": ml,
            "max_turns": int(max_turns) if max_turns else max_turns_for(ml),
            "fallback_policy": pol,
            "ranking_eligible": pol != "demo",
        }
        prov_keys = ("benchmark_version", "physics_version", "prompt_version",
                     "spec_fingerprint", "seed", "match_length", "max_turns",
                     "fallback_policy", "ranking_eligible")
        try:
            self._rest("POST", "matches", body=body)
        except Exception:
            # Older Supabase schema without weapon/flip/mode/arena/
            # blindfolded columns: retry without them so deploys don't
            # break before the migration. record_vote() falls back to
            # historic defaults (macro/normal/not-blindfolded) for any
            # match created this way (NULL fields, python COALESCEs).
            for k in ("weapon", "flip", "mode", "arena", "blindfolded"):
                body.pop(k, None)
            try:
                self._rest("POST", "matches", body=body)
            except Exception:
                # Pre-benchmark-spec schema: drop provenance too. The match
                # still runs; it just won't carry a version stamp, which is
                # exactly what /api/integrity reports as unverifiable.
                for k in prov_keys:
                    body.pop(k, None)
                self._rest("POST", "matches", body=body)
        return mid

    def cancel_match(self, mid):
        """Mark a queued/running match cancelled (action-plan §13)."""
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                       body={"cancelled": True, "status": "error",
                             "error": "cancelled by user"})
            return True
        except Exception as e:
            print(f"[storage] cancel_match failed for {mid}: {e}")
            return False

    def is_cancelled(self, mid):
        m = self.get_match(mid)
        return bool(m and m.get("cancelled"))

    def set_provenance(self, mid, prov: dict):
        """Persist outcome-side provenance (model/provider actually used,
        latency, fallback, invalid actions, ranking eligibility)."""
        if not prov:
            return
        import json as _json
        body = {
            "model_used_a": prov.get("model_used_a"),
            "model_used_b": prov.get("model_used_b"),
            "provider_used_a": prov.get("provider_used_a"),
            "provider_used_b": prov.get("provider_used_b"),
            "fallback_used": bool(prov.get("fallback_used")),
            "latency_ms_a": prov.get("latency_ms_a"),
            "latency_ms_b": prov.get("latency_ms_b"),
            "invalid_actions_a": int(prov.get("invalid_actions_a") or 0),
            "invalid_actions_b": int(prov.get("invalid_actions_b") or 0),
            "ranking_eligible": bool(prov.get("ranking_eligible", True)),
        }
        for k in ("models_used_a", "models_used_b"):
            if prov.get(k):
                try:
                    body[k] = _json.dumps(prov[k])
                except (TypeError, ValueError):
                    pass
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                       body=body)
        except Exception:
            # Un-migrated schema: keep only the columns we know exist.
            for k in list(body):
                if k not in ("model_used_a", "model_used_b",
                             "provider_used_a", "provider_used_b",
                             "fallback_used"):
                    body.pop(k, None)
            try:
                self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                           body=body)
            except Exception as e:
                print(f"[storage] set_provenance skipped for {mid}: {e}")

    def set_flip(self, mid, flip: bool):
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                       body={"flip": bool(flip)})
        except Exception as exc:
            print(f"[storage] failed to persist flip for match {mid}: {exc}")
            raise RuntimeError(f"Failed to persist match flip state for {mid}: {exc}") from exc

    def set_status(self, mid, status, error=None):
        self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                   body={"status": status, "error": error})

    def cleanup_stale_matches(self, error_msg="Server restarted while match was in progress"):
        """Clean up matches that were left in 'queued' or 'running' state across server restarts."""
        try:
            self._rest("PATCH", "matches",
                       params={"status": "in.(queued,running)"},
                       body={"status": "error", "error": error_msg})
        except Exception as e:
            print(f"[storage] cleanup_stale_matches warning: {e}")

    def finish_match(self, mid, winner_side, method, turns, replay,
                     commentary=None, provenance=None):
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
        # Tier S #3: proxy metrics from replay.meta.metrics -> match columns.
        # Skipped entirely if the replay didn't include a metrics dict
        # (older code paths / malformed replay). Individual keys sent
        # only when present so an un-migrated Supabase schema doesn't
        # 400 the PATCH; the graceful-fallback catch below strips them
        # all if any column is unknown.
        metrics = (replay.get("meta") or {}).get("metrics") or {}
        metric_keys = [
            "damage_dealt_a", "damage_dealt_b",
            "hits_landed_a", "hits_landed_b",
            "hits_attempted_a", "hits_attempted_b",
            "fallback_turns_a", "fallback_turns_b",
            "avg_distance",
        ]
        for k in metric_keys:
            if k in metrics:
                body[k] = metrics[k]
        prov_keys = ["model_used_a", "model_used_b", "provider_used_a",
                     "provider_used_b", "fallback_used", "latency_ms_a",
                     "latency_ms_b", "invalid_actions_a",
                     "invalid_actions_b", "ranking_eligible",
                     "models_used_a", "models_used_b"]
        try:
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"}, body=body)
        except Exception:
            # Column not present on this schema (commentary OR any of the
            # Tier-S-3 metrics). Retry with a minimal body so the finish
            # still lands. Operator should re-run supabase_schema.sql.
            for k in ["commentary"] + metric_keys:
                body.pop(k, None)
            self._rest("PATCH", "matches", params={"id": f"eq.{mid}"}, body=body)
        # benchmark spec v1.0: outcome-side provenance, best-effort.
        if provenance:
            self.set_provenance(mid, provenance)
            if int(provenance.get("fallback_used") or 0):
                try:
                    self._rest("PATCH", "matches",
                               params={"id": f"eq.{mid}"},
                               body={"fallback_used": True})
                except Exception:
                    pass

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

    def export_matches(self, since=None, until=None, limit=10000,
                       include_votes=True):
        """Tier-A #3: mirror of SQLite export_matches for Supabase.
        See storage.py:LocalStorage.export_matches for definitions +
        rationale. `created` is a float epoch on the Supabase side too
        (create_match writes time.time()), so bounds pass as numeric."""
        from brains import PROMPT_VERSION
        params = {"status": "eq.done", "order": "created.asc",
                  "limit": str(int(limit))}
        if since is not None:
            params["created"] = f"gte.{float(since)}"
            # PostgREST accepts multiple filters on the same column via
            # separate params only if the API surface uses `and=(...)` —
            # simpler: only ONE side-bound at a time via the direct
            # param, upper bound via the `and` block if both given.
        # If both bounds given, use the `and` composite (PostgREST doc'd
        # combinator). Documented here because it's non-obvious.
        if since is not None and until is not None:
            params.pop("created", None)
            params["and"] = f"(created.gte.{float(since)},created.lte.{float(until)})"
        elif until is not None:
            params["created"] = f"lte.{float(until)}"
        try:
            rows = self._rest("GET", "matches", params=params)
        except Exception:
            return []
        rows = [dict(r) for r in rows]
        if include_votes and rows:
            mids = [r["id"] for r in rows]
            # PostgREST `in` operator wants comma-joined values in parens
            vote_params = {"match_id": f"in.({','.join(mids)})",
                           "select": "id,match_id,created,choice",
                           "limit": "50000"}
            try:
                vrows = self._rest("GET", "votes", params=vote_params)
            except Exception:
                vrows = []
            by_mid = {}
            for v in vrows:
                by_mid.setdefault(v["match_id"], []).append(dict(v))
            for r in rows:
                r["votes"] = by_mid.get(r["id"], [])
                r["prompt_version"] = PROMPT_VERSION
        else:
            for r in rows:
                r["prompt_version"] = PROMPT_VERSION
        return rows

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
    def _get_elo_row(self, model, sharp, weapon, mode="macro", arena="normal",
                     blindfolded=0):
        """Tier-S #3: PK is (model, sharp, weapon, mode, arena, blindfolded).
        Callers that don't pass mode/arena/blindfolded default to the
        historic (macro, normal, 0) which is what pre-migration data was."""
        params = {"model": f"eq.{model}", "sharp": f"eq.{sharp}",
                  "weapon": f"eq.{weapon}",
                  "mode": f"eq.{mode}", "arena": f"eq.{arena}",
                  "blindfolded": f"eq.{'true' if blindfolded else 'false'}"}
        rows = self._rest("GET", "elo", params=params)
        if rows:
            return dict(rows[0])
        row = {"model": model, "sharp": sharp, "weapon": weapon,
               "mode": mode, "arena": arena,
               "blindfolded": bool(blindfolded),
               "rating": START_ELO, "wins": 0, "losses": 0, "draws": 0}
        # Hard-fail loudly instead of silently corrupting cross-cell data.
        # If POST fails, operator needs to re-run supabase_schema.sql
        # (Tier-S-3 migration block) before votes can flow again.
        self._rest("POST", "elo", body=row,
                   prefer="resolution=merge-duplicates")
        return row

    def _set_elo_row(self, row):
        # (model, sharp, weapon, mode, arena, blindfolded) are ALL
        # required — they're the PK. PATCHing without one would spray
        # the update across every row matching the partial key. Enforced
        # by contract. If this fires: re-run supabase_schema.sql; the
        # Tier-S-3 migration is incomplete.
        for key in ("weapon", "mode", "arena"):
            if not row.get(key):
                raise ValueError(
                    f"_set_elo_row: '{key}' is required (part of the elo PK); "
                    f"re-run supabase_schema.sql if this fires — the migration "
                    f"is incomplete.")
        if "blindfolded" not in row:
            raise ValueError("_set_elo_row: 'blindfolded' is required "
                             "(part of the elo PK); re-run supabase_schema.sql")
        params = {"model":  f"eq.{row['model']}",
                  "sharp":  f"eq.{row['sharp']}",
                  "weapon": f"eq.{row['weapon']}",
                  "mode":   f"eq.{row['mode']}",
                  "arena":  f"eq.{row['arena']}",
                  "blindfolded": f"eq.{'true' if row['blindfolded'] else 'false'}"}
        self._rest("PATCH", "elo", params=params,
            body={"rating": row["rating"], "wins": row["wins"],
                  "losses": row["losses"], "draws": row["draws"]})

    @staticmethod
    def _exclusion_reason(m):
        """Human-readable reason a match is not ranked."""
        pol = m.get("fallback_policy") or "operational"
        if pol == "demo":
            return "demo match (scripted fighters) — not ranked"
        if pol == "strict" and m.get("fallback_used"):
            return ("strict fallback policy: a provider fallback occurred, "
                    "so this match is excluded from rankings")
        return "excluded from rankings"

    @staticmethod
    def _unflip_choice(choice, flip):
        if choice == "draw":
            return "draw"
        if not flip:
            return choice
        return "a" if choice == "b" else "b"

    def _apply_elo_atomic(self, a, b, sharp, weapon, mode, arena,
                          blindfolded, choice_model):
        """Call the apply_elo_vote() Postgres RPC in one atomic txn.
        Tier-S #3: signature now includes blindfolded (7 params before
        k_factor/start_elo). Requires the updated RPC — re-run
        supabase_schema.sql after pulling this commit."""
        rows = self._rest(
            "POST", "rpc/apply_elo_vote",
            body={"a_model": a, "b_model": b,
                  "p_sharp": sharp, "p_weapon": weapon,
                  "p_mode": mode, "p_arena": arena,
                  "p_blindfolded": bool(blindfolded),
                  "choice_model": choice_model,
                  "k_factor": K_FACTOR, "start_elo": START_ELO})
        if not rows:
            raise RuntimeError("apply_elo_vote RPC returned no row")
        row = rows[0] if isinstance(rows, list) else rows
        return float(row["d_a"]), float(row["d_b"])

    def _apply_elo_fallback(self, a, b, sharp, weapon, mode, arena,
                            blindfolded, choice_model):
        """Read-modify-write path. Only reached if the atomic RPC isn't
        installed. Wrapped by self._vote_lock in record_vote()."""
        if a == b:
            row = self._get_elo_row(a, sharp, weapon, mode, arena, blindfolded)
            row["draws"] += 1
            self._set_elo_row(row)
            return 0.0, 0.0
        ra, rb = (self._get_elo_row(a, sharp, weapon, mode, arena, blindfolded),
                  self._get_elo_row(b, sharp, weapon, mode, arena, blindfolded))
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

    def record_vote(self, mid, choice, axes=None, confidence=None):
        m = self.get_match(mid)
        if not m or m["status"] != "done":
            return None
        if m.get("voted"):
            return {"already_voted": True, **self.reveal(mid)}
        sharp = m["sharp"]
        weapon = m.get("weapon") or "sword"
        # Pull mode + arena + blindfolded from the match row so votes
        # route to the SAME elo cell the match was played under. Pre-
        # migration matches (NULL fields) fall back to historic defaults.
        mode = m.get("mode") or "macro"
        arena = m.get("arena") or "normal"
        blindfolded = int(bool(m.get("blindfolded") or 0))
        flip = bool(m.get("flip"))
        a, b = m["model_a"], m["model_b"]
        choice_model = self._unflip_choice(choice, flip)
        # Multi-axis vote (action-plan §6): `choice` is the tactical vote
        # and the only ranked one; the rest are research signal.
        axes = axes or {}
        vote_body = {
            "id": uuid.uuid4().hex[:12], "match_id": mid,
            "created": time.time(), "choice": choice}
        for axis in ("execution", "entertainment", "deserved"):
            v = axes.get(axis)
            if v in ("a", "b", "draw"):
                vote_body[axis] = v
        try:
            conf = int(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            conf = None
        if conf is not None:
            vote_body["confidence"] = max(1, min(5, conf))
        try:
            self._rest("POST", "votes", body=vote_body)
        except Exception as ve:
            # Un-migrated votes table: retry with the tactical vote only.
            for k in ("execution", "entertainment", "deserved", "confidence"):
                vote_body.pop(k, None)
            try:
                self._rest("POST", "votes", body=vote_body)
            except Exception:
                pass
        if m.get("ranking_eligible") is False:
            # Recorded and revealed, but deliberately unranked.
            try:
                self._rest("PATCH", "matches", params={"id": f"eq.{mid}"},
                           body={"voted": True})
            except Exception:
                pass
            return {"elo_change": {}, "ranking_excluded": True,
                    "exclusion_reason": self._exclusion_reason(m),
                    **self.reveal(mid)}
        d_a = d_b = None
        if self._rpc_ok is not False:
            try:
                d_a, d_b = self._apply_elo_atomic(a, b, sharp, weapon,
                                                  mode, arena, blindfolded,
                                                  choice_model)
                self._rpc_ok = True
            except Exception as e:
                if self._rpc_ok is None:
                    print(f"[storage] apply_elo_vote RPC unavailable ({e}); "
                          f"falling back to REST + in-process lock. "
                          f"Re-run supabase_schema.sql to enable atomic path.")
                self._rpc_ok = False
        if d_a is None:
            with self._vote_lock:
                d_a, d_b = self._apply_elo_fallback(a, b, sharp, weapon,
                                                    mode, arena, blindfolded,
                                                    choice_model)
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

    def objective_leaderboard(self, sharp=None, weapon=None, mode=None,
                              arena=None, blindfolded=None):
        """Mirror of SQLite objective_leaderboard. Pulls done matches
        with non-null proxy metrics via PostgREST, rolls up per-model
        in Python. See storage.py:LocalStorage.objective_leaderboard
        for definitions of damage_per_turn / hit_rate / fallback_rate.

        Bounded to 10k rows per query — well above any realistic done-
        match count under HN-frontpage load. If we ever exceed that
        we'll paginate; for now the simple path is fine."""
        params = {
            "status": "eq.done",
            "damage_dealt_a": "not.is.null",
            "select": ("model_a,model_b,flip,winner_side,turns,"
                       "damage_dealt_a,damage_dealt_b,"
                       "hits_landed_a,hits_landed_b,"
                       "hits_attempted_a,hits_attempted_b,"
                       "fallback_turns_a,fallback_turns_b,"
                       "avg_distance"),
            "limit": "10000",
        }
        if sharp:  params["sharp"]  = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if mode:   params["mode"]   = f"eq.{mode}"
        if arena:  params["arena"]  = f"eq.{arena}"
        if blindfolded is not None:
            params["blindfolded"] = f"eq.{'true' if blindfolded else 'false'}"
        try:
            rows = self._rest("GET", "matches", params=params)
        except Exception:
            # Un-migrated schema (no proxy-metric columns): return empty.
            return []
        agg = {}
        for r in rows:
            t = int(r.get("turns") or 0)
            avg_d = float(r.get("avg_distance") or 0.0)
            flip = bool(r.get("flip"))
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
                m["damage"] += float(r.get(f"damage_dealt_{side}") or 0.0)
                m["hits_landed"] += int(r.get(f"hits_landed_{side}") or 0)
                m["hits_attempted"] += int(r.get(f"hits_attempted_{side}") or 0)
                m["fallback"] += int(r.get(f"fallback_turns_{side}") or 0)
                m["distance_sum"] += avg_d
            if (r.get("winner_side") or "").lower() == "draw":
                agg[r["model_a"]]["draws"] += 1
                agg[r["model_b"]]["draws"] += 1
            else:
                da = float((r.get("damage_dealt_b") if flip else r.get("damage_dealt_a")) or 0.0)
                db = float((r.get("damage_dealt_a") if flip else r.get("damage_dealt_b")) or 0.0)
                if da > db:
                    agg[r["model_a"]]["wins"]   += 1
                    agg[r["model_b"]]["losses"] += 1
                elif db > da:
                    agg[r["model_b"]]["wins"]   += 1
                    agg[r["model_a"]]["losses"] += 1
                else:
                    agg[r["model_a"]]["draws"] += 1
                    agg[r["model_b"]]["draws"] += 1
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
        out.sort(key=lambda x: -x["damage_per_turn"])
        return out

    def model_stats(self, sharp=None, weapon=None, mode=None, arena=None,
                    blindfolded=None):
        """Mirror of SQLite model_stats. Pulls done matches with non-null
        proxy metrics via PostgREST, rolls up per-model in Python. See
        storage.py:LocalStorage.model_stats for definitions of every rate
        (hit_rate can exceed 1.0 — contacts per decision, not a
        probability; lethal_rate counts kills only, so an attrition
        winner correctly shows lethal_rate 0 with a high win_rate).

        Bounded to 10k match rows / 50k vote rows per query, same
        convention as objective_leaderboard. Un-migrated schema (any
        selected column missing from Supabase): return empty — operator
        should re-run supabase_schema.sql.
        """
        params = {
            "status": "eq.done",
            "damage_dealt_a": "not.is.null",
            "select": ("id,model_a,model_b,flip,winner_side,method,turns,"
                       "damage_dealt_a,damage_dealt_b,"
                       "hits_landed_a,hits_landed_b,"
                       "hits_attempted_a,hits_attempted_b,"
                       "fallback_turns_a,fallback_turns_b,"
                       "latency_ms_a,latency_ms_b,"
                       "invalid_actions_a,invalid_actions_b,"
                       "fallback_used,ranking_eligible"),
            "limit": "10000",
        }
        if sharp:  params["sharp"]  = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if mode:   params["mode"]   = f"eq.{mode}"
        if arena:  params["arena"]  = f"eq.{arena}"
        if blindfolded is not None:
            params["blindfolded"] = f"eq.{'true' if blindfolded else 'false'}"
        try:
            rows = self._rest("GET", "matches", params=params)
        except Exception:
            # Un-migrated schema (a selected column doesn't exist yet):
            # return empty. Operator should re-run supabase_schema.sql.
            return []
        try:
            votes = {}
            for v in self._rest("GET", "votes",
                                params={"select": "match_id,choice",
                                        "limit": "50000"}):
                votes[v["match_id"]] = (v["choice"] or "").lower()
        except Exception:
            votes = {}

        out = {}
        for r in rows:
            t = max(1, int(r.get("turns") or 1))
            flip = bool(r.get("flip"))
            side_a = r["model_b"] if flip else r["model_a"]
            side_b = r["model_a"] if flip else r["model_b"]
            lethal = (r.get("method") or "") == "kill"
            timeout = (r.get("method") or "").startswith("timeout")
            # ranking_eligible defaults true (mirrors the SQLite side's
            # COALESCE(ranking_eligible, 1) for pre-migration rows).
            eligible = r.get("ranking_eligible")
            eligible = True if eligible is None else bool(eligible)
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
                if choice and eligible:
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

    def quality_rows(self, sharp=None, weapon=None, mode=None, arena=None,
                     blindfolded=None, limit=50000):
        """Mirror of LocalStorage.quality_rows: finished match rows with the
        provenance columns the data-quality classifier reads. Falls back
        to the pre-§33 column set on an un-migrated schema so the labels
        still render (token coverage then reads as 'missing', which is the
        truthful answer for a database that never stored tokens)."""
        from storage import LocalStorage
        cols = [c.strip() for c in LocalStorage.QUALITY_COLUMNS.split(",")]
        params = {"status": "eq.done", "order": "created.asc",
                  "limit": str(int(limit))}
        if sharp:  params["sharp"]  = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if mode:   params["mode"]   = f"eq.{mode}"
        if arena:  params["arena"]  = f"eq.{arena}"
        if blindfolded is not None:
            params["blindfolded"] = f"eq.{'true' if blindfolded else 'false'}"
        try:
            rows = self._rest("GET", "matches",
                              params={**params, "select": ",".join(cols)})
        except Exception:
            legacy = [c for c in cols if not c.startswith(
                ("prompt_tokens", "completion_tokens", "api_calls"))]
            try:
                rows = self._rest("GET", "matches",
                                  params={**params, "select": ",".join(legacy)})
            except Exception:
                return []
        return [dict(r) for r in rows]

    def leaderboard(self, sharp=None, weapon=None, mode=None, arena=None,
                    blindfolded=None):
        """Mirror of SQLite leaderboard. Any of (sharp, weapon, mode,
        arena, blindfolded) can be None to skip that dimension. When
        ALL five are None the result aggregates per-model across every
        cell. Tier-S #3: blindfolded is the 5th eval axis."""
        params = {"order": "rating.desc"}
        if sharp:  params["sharp"]  = f"eq.{sharp}"
        if weapon: params["weapon"] = f"eq.{weapon}"
        if mode:   params["mode"]   = f"eq.{mode}"
        if arena:  params["arena"]  = f"eq.{arena}"
        if blindfolded is not None:
            params["blindfolded"] = f"eq.{'true' if blindfolded else 'false'}"
        if sharp or weapon or mode or arena or blindfolded is not None:
            rows = self._rest("GET", "elo", params=params)
            return [dict(r) for r in rows]
        # No filters => aggregate per-model across every cell.
        rows = self._rest("GET", "elo", params=params)
        agg = {}
        for r in rows:
            a = agg.setdefault(r["model"], {
                "model": r["model"],
                "sharp": "ALL", "weapon": "ALL",
                "mode": "ALL", "arena": "ALL", "blindfolded": False,
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
