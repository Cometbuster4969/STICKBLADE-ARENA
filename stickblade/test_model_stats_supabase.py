"""Supabase model_stats regression test (headless, no network).

Guards two stacked failures that 500'd GET /api/model_stats on every
Supabase-backed deploy (the leaderboard "metrics" tab):

  1. CODE GAP — SupabaseStorage never implemented model_stats() (only
     LocalStorage had it), so the route raised AttributeError.
  2. SCHEMA DRIFT — caught separately: on an un-migrated Supabase
     (missing v1.0 metric columns) the method must return [] (HTTP 200
     with empty rows), never raise. Operator re-runs supabase_schema.sql
     to fill the columns.

Checks:
  1. AGG   — flip-aware attribution, kill/timeout/draw handling,
             preference counting (side vote, draw vote = 0.5, vote on a
             ranking-ineligible match ignored, NULL eligibility = eligible).
  2. PARAMS — filter args map to the right PostgREST operators.
  3. DEGRADE — matches-query failure -> []; votes-query failure -> rows
             with preference_rate None (never a raise).
  4. PARITY — byte-identical output to LocalStorage.model_stats on the
             same dataset (the "mirror must match" property).

Run:  python test_model_stats_supabase.py   (from stickblade/)
Exits non-zero if any check fails.
"""
import json
import sqlite3
import sys
import tempfile
import types

# storage_supabase imports httpx at module top; stub it — these tests
# never touch the network (we bypass __init__ and fake _rest).
sys.modules.setdefault("httpx", types.ModuleType("httpx"))

from storage_supabase import SupabaseStorage  # noqa: E402
from storage import LocalStorage  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ------------------------------------------------------------------ fixture
# Canvas sides (a/b) are what winner_side/votes reference; flip swaps which
# MODEL sits on which canvas side. M2 is flipped: canvas-a = C, canvas-b = B.
MATCHES = [
    {  # M1: A kills B, voted for canvas-a. fallback_used credits BOTH sides.
        "id": "m1", "model_a": "A", "model_b": "B", "flip": False,
        "winner_side": "a", "method": "kill", "turns": 10,
        "damage_dealt_a": 100.0, "damage_dealt_b": 20.0,
        "hits_landed_a": 8, "hits_landed_b": 2,
        "hits_attempted_a": 10, "hits_attempted_b": 9,
        "fallback_turns_a": 0, "fallback_turns_b": 3,
        "latency_ms_a": 500.0, "latency_ms_b": 900.0,
        "invalid_actions_a": 0, "invalid_actions_b": 1,
        "fallback_used": True, "ranking_eligible": True,
    },
    {  # M2: flipped timeout, canvas-b (B) wins, draw vote, NULL eligibility.
        "id": "m2", "model_a": "B", "model_b": "C", "flip": True,
        "winner_side": "b", "method": "timeout_points", "turns": 24,
        "damage_dealt_a": 30.0, "damage_dealt_b": 40.0,
        "hits_landed_a": 3, "hits_landed_b": 4,
        "hits_attempted_a": 12, "hits_attempted_b": 12,
        "fallback_turns_a": 1, "fallback_turns_b": 1,
        "latency_ms_a": 700.0, "latency_ms_b": 700.0,
        "invalid_actions_a": 0, "invalid_actions_b": 0,
        "fallback_used": False, "ranking_eligible": None,
    },
    {  # M3: draw, ranking-INeligible — its vote must not count anywhere.
        "id": "m3", "model_a": "A", "model_b": "C", "flip": False,
        "winner_side": "draw", "method": "points", "turns": 24,
        "damage_dealt_a": 50.0, "damage_dealt_b": 50.0,
        "hits_landed_a": 5, "hits_landed_b": 5,
        "hits_attempted_a": 20, "hits_attempted_b": 20,
        "fallback_turns_a": 0, "fallback_turns_b": 0,
        "latency_ms_a": 600.0, "latency_ms_b": 650.0,
        "invalid_actions_a": 2, "invalid_actions_b": 0,
        "fallback_used": False, "ranking_eligible": False,
    },
]
VOTES = [
    {"match_id": "m1", "choice": "a"},
    {"match_id": "m2", "choice": "draw"},
    {"match_id": "m3", "choice": "a"},  # ignored: m3 ineligible
]


def make_store(matches=MATCHES, votes=VOTES, fail_on=()):
    s = SupabaseStorage.__new__(SupabaseStorage)  # skip __init__ (env+network)
    seen = {}

    def fake_rest(method, table, params=None, body=None, prefer=None):
        if table in fail_on:
            raise RuntimeError(f"simulated {table} failure")
        seen[table] = params
        if table == "matches":
            return [dict(r) for r in matches]
        if table == "votes":
            return [dict(v) for v in votes]
        raise AssertionError(f"unexpected table {table}")

    s._rest = fake_rest
    return s, seen


def by_model(rows):
    return {r["model"]: r for r in rows}


# ------------------------------------------------------------ 1. aggregation
rows = make_store()[0].model_stats()
m = by_model(rows)
check("agg: three models", set(m) == {"A", "B", "C"}, sorted(m))

a, b, c = m["A"], m["B"], m["C"]
check("agg: A 2 matches, 1 win, 1 draw", (a["matches"], a["wins"], a["losses"], a["draws"]) == (2, 1, 0, 1), a)
check("agg: A win_rate 1.0", a["win_rate"] == 1.0, a["win_rate"])
check("agg: A lethal_rate 0.5 (kill in M1 only)", a["lethal_rate"] == 0.5, a["lethal_rate"])
check("agg: A survived 1.0", a["survival_rate"] == 1.0, a["survival_rate"])
check("agg: A preference 1.0 over 1 voted match (M3 ignored)",
      (a["preference_rate"], a["voted_matches"]) == (1.0, 1), (a["preference_rate"], a["voted_matches"]))
check("agg: A damage_per_turn", a["damage_per_turn"] == round(150.0 / 34, 2), a["damage_per_turn"])
check("agg: A fallback_match_rate 0.5 (M1 only)", a["fallback_match_rate"] == 0.5, a["fallback_match_rate"])
check("agg: A latency mean/max", (a["latency_ms_mean"], a["latency_ms_max"]) == (550.0, 600.0),
      (a["latency_ms_mean"], a["latency_ms_max"]))

check("agg: B win_rate 0.5", b["win_rate"] == 0.5, b["win_rate"])
check("agg: B preference 0.25 (0 + 0.5 over 2)", b["preference_rate"] == 0.25, b["preference_rate"])
check("agg: B timeout_rate 0.5", b["timeout_rate"] == 0.5, b["timeout_rate"])
check("agg: B survived 0.5 (died in M1 kill)", b["survival_rate"] == 0.5, b["survival_rate"])

check("agg: C win_rate 0.0", c["win_rate"] == 0.0, c["win_rate"])
check("agg: C preference 0.5 (draw vote over 1)", c["preference_rate"] == 0.5, c["preference_rate"])
check("agg: sorted by win_rate desc", [r["model"] for r in rows] == ["A", "B", "C"],
      [r["model"] for r in rows])

# ----------------------------------------------------------------- 2. params
s, seen = make_store()
s.model_stats(sharp="tip", weapon="sword", mode="macro", arena="ice", blindfolded=True)
p = seen["matches"]
check("params: base filters", p["status"] == "eq.done" and p["damage_dealt_a"] == "not.is.null", p)
check("params: eq filters",
      (p["sharp"], p["weapon"], p["mode"], p["arena"], p["blindfolded"]) ==
      ("eq.tip", "eq.sword", "eq.macro", "eq.ice", "eq.true"), p)
check("params: select has all 21 columns", len(p["select"].split(",")) == 21, p["select"])
s2, seen2 = make_store()
s2.model_stats()
check("params: no filter keys when unfiltered",
      not any(k in seen2["matches"] for k in ("sharp", "weapon", "mode", "arena", "blindfolded")),
      seen2["matches"])

# --------------------------------------------------------- 3. degradation
check("degrade: matches failure -> []", make_store(fail_on=("matches",))[0].model_stats() == [])
novote = make_store(fail_on=("votes",))[0].model_stats()
check("degrade: votes failure still returns rows", len(novote) == 3, len(novote))
check("degrade: votes failure -> preference None",
      all(r["preference_rate"] is None and r["voted_matches"] == 0 for r in novote), novote)

# ------------------------------------------------ 4. parity with LocalStorage
tmp = tempfile.mkdtemp(prefix="msb_parity_")
local = LocalStorage(root=tmp)
cols = ("id,model_a,model_b,flip,winner_side,method,turns,status,"
        "damage_dealt_a,damage_dealt_b,hits_landed_a,hits_landed_b,"
        "hits_attempted_a,hits_attempted_b,fallback_turns_a,fallback_turns_b,"
        "latency_ms_a,latency_ms_b,invalid_actions_a,invalid_actions_b,"
        "fallback_used,ranking_eligible")
with local._conn() as conn:
    for r in MATCHES:
        vals = [r["id"], r["model_a"], r["model_b"], int(r["flip"]),
                r["winner_side"], r["method"], r["turns"], "done",
                r["damage_dealt_a"], r["damage_dealt_b"],
                r["hits_landed_a"], r["hits_landed_b"],
                r["hits_attempted_a"], r["hits_attempted_b"],
                r["fallback_turns_a"], r["fallback_turns_b"],
                r["latency_ms_a"], r["latency_ms_b"],
                r["invalid_actions_a"], r["invalid_actions_b"],
                int(r["fallback_used"]),
                (None if r["ranking_eligible"] is None else int(r["ranking_eligible"]))]
        conn.execute(f"INSERT INTO matches ({cols}) VALUES ({','.join('?' * len(vals))})", vals)
    for i, v in enumerate(VOTES):
        conn.execute("INSERT INTO votes (id, match_id, choice) VALUES (?,?,?)",
                     (f"v{i}", v["match_id"], v["choice"]))
expected = local.model_stats()
got = make_store()[0].model_stats()
check("parity: identical output to LocalStorage",
      json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True),
      f"\n got={json.dumps(got, sort_keys=True)}\n exp={json.dumps(expected, sort_keys=True)}")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("all model_stats supabase checks passed")
