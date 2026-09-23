"""Supabase preference_pairs regression test (headless, no network).

Guards the GET /api/leaderboard/bradley_terry + /api/events 500s: both
routes call store.preference_pairs(), which only LocalStorage had —
SupabaseStorage raised AttributeError (same bug class as model_stats).

Also guards the ratings.py eligibility fix: preference_pairs_from_votes
used `is False`, which silently INCLUDED ranking-ineligible rows from
SQLite (0/1 ints). Supabase rows carry real booleans, so without the
fix the two backends would disagree on what gets ranked.

Checks:
  1. UNIT   — most-recent-vote-wins, untimed-vote matches dropped,
             eligibility/created/match_length passthrough, NULLS-first
             order, PostgREST filter mapping.
  2. TIER   — expert/casual split when voter_tier exists; missing
             column degrades to casual-fallback / expert-empty, never raises.
  3. DEGRADE — matches-query failure -> [].
  4. PARITY — identical Bradley-Terry PAIRS to LocalStorage on the same
             dataset (the downstream contract), including exclusion of a
             ranking-ineligible match on BOTH backends.
  5. ELIG   — eligibility gate truth table (False/0 out; True/1/None/
             missing in).

Run:  python test_preference_pairs_supabase.py   (from stickblade/)
Exits non-zero if any check fails.
"""
import sys
import tempfile
import types

# storage_supabase imports httpx at module top; stub it — these tests
# never touch the network (we bypass __init__ and fake _rest).
sys.modules.setdefault("httpx", types.ModuleType("httpx"))

from storage_supabase import SupabaseStorage  # noqa: E402
from storage import LocalStorage  # noqa: E402
from ratings import preference_pairs_from_votes  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ------------------------------------------------------------------ fixture
MATCHES = [
    {"id": "m1", "model_a": "A", "model_b": "B", "flip": False,
     "ranking_eligible": True, "created": 100.0, "match_length": "standard"},
    {"id": "m2", "model_a": "B", "model_b": "C", "flip": True,
     "ranking_eligible": None, "created": 200.0, "match_length": "sprint"},
    {"id": "m3", "model_a": "A", "model_b": "C", "flip": False,
     "ranking_eligible": False, "created": 300.0, "match_length": "standard"},
    {"id": "m4", "model_a": "A", "model_b": "B", "flip": False,
     "ranking_eligible": True, "created": None, "match_length": "full"},
    {"id": "m5", "model_a": "B", "model_b": "C", "flip": False,
     "ranking_eligible": True, "created": 500.0, "match_length": "standard"},
]
VOTES = [
    {"match_id": "m1", "choice": "b", "created": 10.0},
    {"match_id": "m1", "choice": "a", "created": 20.0},  # most recent wins
    {"match_id": "m2", "choice": "draw", "created": 30.0},
    {"match_id": "m3", "choice": "a", "created": 40.0},  # ineligible match
    {"match_id": "m4", "choice": "a", "created": None},  # untimed: dropped
    # m5: no votes at all -> absent
]


def make_store(matches=MATCHES, votes=VOTES, fail_on=(), no_tier_col=False):
    s = SupabaseStorage.__new__(SupabaseStorage)  # skip __init__ (env+network)
    seen = {}

    def fake_rest(method, table, params=None, body=None, prefer=None):
        if table in fail_on:
            raise RuntimeError(f"simulated {table} failure")
        if (table == "votes" and no_tier_col
                and "voter_tier" in (params or {}).get("select", "")):
            raise RuntimeError("column voter_tier does not exist")
        seen.setdefault(table, []).append(params)
        if table == "matches":
            return [dict(r) for r in matches]
        if table == "votes":
            rows = [dict(v) for v in votes]
            if no_tier_col:
                # A missing column can't come back in rows either.
                for r in rows:
                    r.pop("voter_tier", None)
            return rows
        raise AssertionError(f"unexpected table {table}")

    s._rest = fake_rest
    return s, seen


# ------------------------------------------------------------------- 1. unit
rows = make_store()[0].preference_pairs()
by_id = {(r["model_a"], r["model_b"]): r for r in rows}
check("unit: m1/m2/m3 rows, m4/m5 dropped", len(rows) == 3, rows)
check("unit: m1 most-recent vote (a) wins", by_id[("A", "B")]["choice"] == "a", rows)
check("unit: m2 flip passthrough", by_id[("B", "C")]["flip"] is True, rows)
check("unit: NULL eligibility reads eligible",
      by_id[("B", "C")]["ranking_eligible"] is True, rows)
check("unit: False eligibility stays False",
      by_id[("A", "C")]["ranking_eligible"] is False, rows)
check("unit: match_length passthrough",
      [r["match_length"] for r in rows] == ["standard", "sprint", "standard"], rows)
check("unit: order by created", [r["created"] for r in rows] == [100.0, 200.0, 300.0], rows)

s, seen = make_store()
s.preference_pairs(sharp="tip", weapon="sword", mode="joint", arena="ice",
                   blindfolded=False)
p = seen["matches"][0]
check("unit: base filters + order",
      p["status"] == "eq.done" and p["voted"] == "eq.true"
      and p["order"] == "created.asc", p)
check("unit: eq filters",
      (p["sharp"], p["weapon"], p["mode"], p["arena"], p["blindfolded"]) ==
      ("eq.tip", "eq.sword", "eq.joint", "eq.ice", "eq.false"), p)
check("unit: no tier column selected when unfiltered",
      "voter_tier" not in seen["votes"][0]["select"], seen["votes"][0])

# ------------------------------------------------------------------- 2. tier
TIER_VOTES = [
    {"match_id": "m1", "choice": "a", "created": 1.0, "voter_tier": "expert"},
    {"match_id": "m2", "choice": "b", "created": 2.0, "voter_tier": "casual"},
    {"match_id": "m3", "choice": "a", "created": 3.0},  # missing -> casual
]
st, _ = make_store(votes=TIER_VOTES)
check("tier: expert keeps expert only",
      [(r["model_a"], r["model_b"]) for r in st.preference_pairs(tier="expert")] == [("A", "B")],
      st.preference_pairs(tier="expert"))
check("tier: casual keeps casual + missing",
      sorted((r["model_a"], r["model_b"]) for r in st.preference_pairs(tier="casual")) ==
      [("A", "C"), ("B", "C")],
      st.preference_pairs(tier="casual"))
check("tier: unfiltered keeps all",
      len(make_store(votes=TIER_VOTES)[0].preference_pairs()) == 3)
sc, _ = make_store(votes=TIER_VOTES, no_tier_col=True)
check("tier: casual falls back without column (all 3 rows)",
      len(sc.preference_pairs(tier="casual")) == 3)
check("tier: expert without column is honestly empty",
      sc.preference_pairs(tier="expert") == [])

# ------------------------------------------------------------- 3. degrade
check("degrade: matches failure -> []",
      make_store(fail_on=("matches",))[0].preference_pairs() == [])
check("degrade: votes failure -> []",
      make_store(fail_on=("votes",))[0].preference_pairs() == [])
check("degrade: no matches -> [] (no votes query)",
      make_store(matches=[])[0].preference_pairs() == [])

# ------------------------------------------------- 4. parity with LocalStorage
tmp = tempfile.mkdtemp(prefix="pp_parity_")
local = LocalStorage(root=tmp)
with local._conn() as conn:
    # Fresh DBs enforce one vote per match, but the SQL explicitly supports
    # legacy multi-vote rows — drop the index to exercise that rule.
    conn.execute("DROP INDEX IF EXISTS idx_votes_match_id")
    for m in MATCHES:
        conn.execute(
            "INSERT INTO matches (id, model_a, model_b, flip, status, voted,"
            " created, match_length, ranking_eligible)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (m["id"], m["model_a"], m["model_b"], int(m["flip"]), "done", 1,
             m["created"], m["match_length"],
             (None if m["ranking_eligible"] is None
              else int(m["ranking_eligible"]))))
    for i, v in enumerate(VOTES):
        conn.execute("INSERT INTO votes (id, match_id, choice, created)"
                     " VALUES (?,?,?,?)",
                     (f"v{i}", v["match_id"], v["choice"], v["created"]))
exp_pairs = sorted(preference_pairs_from_votes(local.preference_pairs()))
got_pairs = sorted(preference_pairs_from_votes(make_store()[0].preference_pairs()))
check("parity: identical BT pairs to LocalStorage", got_pairs == exp_pairs,
      f"\n got={got_pairs}\n exp={exp_pairs}")
check("parity: ineligible m3 excluded on both",
      all("A" not in (a, b) or (a, b) != ("A", "C") for a, b, _ in got_pairs)
      and ("A", "B", 1.0) in got_pairs, got_pairs)

# ------------------------------------------------- 5. eligibility gate
base = {"model_a": "A", "model_b": "B", "flip": False, "choice": "a"}
def gate(val, missing=False):
    r = dict(base)
    if not missing:
        r["ranking_eligible"] = val
    return preference_pairs_from_votes([r])

check("elig: False excluded", gate(False) == [])
check("elig: 0 excluded (SQLite ints)", gate(0) == [])
check("elig: True included", gate(True) == [("A", "B", 1.0)])
check("elig: 1 included", gate(1) == [("A", "B", 1.0)])
check("elig: None included (back-compat)", gate(None) == [("A", "B", 1.0)])
check("elig: missing key included (back-compat)", gate(None, missing=True) == [("A", "B", 1.0)])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("all preference_pairs supabase checks passed")
