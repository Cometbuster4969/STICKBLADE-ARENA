# Stickblade Arena Audit & Resolution

**Audit date:** 2026-09-08

## Scope

Audited:
- Public deployment: https://stickblade-arena.vercel.app/
- Repository: https://github.com/Cometbuster4969/STICKBLADE-ARENA
- Frontend: `stickblade-web`
- Backend: `stickblade`
- Storage, benchmark methodology, and execution durability

---

## Findings & Resolutions

### 1. Objective metrics ignore blind flip mapping (Fixed)
- **Problem:** `LocalStorage.objective_leaderboard()` and `SupabaseStorage.objective_leaderboard()` aggregated `damage_dealt_a` and `damage_dealt_b` directly to `model_a` and `model_b` without applying the match's `flip` state. When `flip=True`, physical fighter A was `model_b`, meaning ~50% of matches had objective stats misattributed.
- **Resolution:** Updated `objective_leaderboard()` in both `storage.py` and `storage_supabase.py` to query `flip` and map canvas-side metrics (`side_a_model`, `side_b_model`) to their true model identities.

### 2. Frontend API base fallback (Fixed)
- **Problem:** `stickblade-web/lib/api.js` directly evaluated `process.env.NEXT_PUBLIC_API_BASE`, causing requests to fail with `undefined/api/...` if the variable was missing during local development.
- **Resolution:** Added a safe default in `stickblade-web/lib/api.js`: `const BASE = (process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000').replace(/\/+$/, '')` and provided `.env.example`.

### 3. Background execution durability & startup cleanup (Fixed)
- **Problem:** When the backend process restarted or crashed, queued or running matches remained stuck in `queued` or `running` state indefinitely.
- **Resolution:** Added `cleanup_stale_matches()` in `storage.py` and `storage_supabase.py`, automatically invoked on startup in `server.py` to mark stale in-progress matches as interrupted. Also ensured `run_simulation()` falls back to database-persisted mode/weapon/arena/blindfolded configurations if in-memory dicts were wiped.

### 4. Vote processing idempotency & transactionality (Fixed)
- **Problem:** Supabase vote insertion was vulnerable to concurrent duplicates and missing unique constraints.
- **Resolution:** Added `CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_match_id ON votes (match_id)` in `supabase_schema.sql` and SQLite schema, and made `record_vote()` safely return `{already_voted: True, ...}` on duplicate attempts.

### 5. `set_flip` failure handling (Fixed)
- **Problem:** `set_flip()` silently caught and ignored exceptions, which could cause blind identity mapping drift.
- **Resolution:** Updated `set_flip()` in `storage_supabase.py` to log and raise if `flip` fails to persist.

### 6. Strict input validation (Fixed)
- **Problem:** Invalid weapon, mode, arena, and sharp-zone values were silently coerced (e.g. invalid weapons defaulting to sword).
- **Resolution:** Enforced `Literal` typing on `MatchReq`, `VoteReq`, and `TournamentReq` in `server.py`, and added strict validation raising HTTP 400 when invalid weapons, arenas, modes, or weapon-incompatible sharp zones are passed.

### 7. Evaluation integrity & fallback visibility (Fixed)
- **Problem:** Matches running heuristic/scripted fallbacks could appear indistinguishable from full LLM evaluation.
- **Resolution:** Included `evaluation_integrity` in `recorder.py` (`meta.evaluation_integrity`) and exposed `evaluation_integrity` (with `fully_llm_controlled`, `fallback_turns_a`, `fallback_turns_b`, `total_turns`) in `/api/match/{mid}`.

---

## Verified Test Matrix

- [x] Objective leaderboard flip mapping (`flip=True` vs `flip=False`)
- [x] Storage regression (self-play, standard Elo update, K-factor deltas)
- [x] Stale match cleanup on startup
- [x] Strict API validation (invalid weapons, sharp zones, modes, arenas, vote choices)
- [x] Frontend JS/JSX syntax and balance check
- [x] Bandit security analysis & secret scanning
- [x] Full headless match simulations across all 5 weapons and 3 arenas
