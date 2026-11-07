"""Collection guard for the procedural scripts that live beside the engine.

`stickblade/` is flat, so pytest's default `test_*.py` pattern matches five
files that are NOT pytest modules — they are runnable scripts whose bodies
execute full matches at import time:

    test_bow_mobility.py          — bow footwork regression script
    test_headless.py              — headless smoke run + screenshots
    test_phases.py                — phases 2-5 verification harness
    test_model_stats_supabase.py  — Supabase model_stats regression script
    test_preference_pairs_supabase.py — Supabase preference_pairs script

Importing any of them simulates a match, writes `battle_log_*.json` into the
CWD, and (in test_bow_mobility's case) calls `sys.exit(0)`, which aborts the
whole pytest session with an INTERNALERROR.

`pytest.ini` keeps a bare `pytest` inside `tests/`, but that does not protect
an explicit `pytest stickblade/`. `collect_ignore_glob` closes that hole while
leaving `test_audit_fixes.py` — a real pytest module with 5 tests — fully
collectable.

These scripts are still runnable exactly as before:
    SDL_VIDEODRIVER=dummy python stickblade/test_bow_mobility.py
"""

collect_ignore_glob = [
    "test_bow_mobility.py",
    "test_headless.py",
    "test_phases.py",
    "test_model_stats_supabase.py",
    "test_preference_pairs_supabase.py",
]
