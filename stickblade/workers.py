"""Match + tournament workers.

`run_simulation` is the only place a match is actually fought: it builds the
`Match`, streams blind turns into `runtime.LIVE_STATE`, records the replay and
persists the result. `worker_loop` and `tournament_worker_loop` are the two
daemon threads that drain their queues.

Split out of server.py so the HTTP layer is routes-and-validation only. The
threads are deliberately NOT started here — `server` starts them after import,
so importing this module from a test or a tool never spawns a thread.
"""
from __future__ import annotations

import os
import threading

import config as C

from runtime import (
    store, jobs, tournament_jobs, MATCH_MODES, MATCH_FLIP, MATCH_API_KEYS,
    BLIND_NAMES, _obs_bump, _obs_error, _obs_latency, _row_get, _safe_err,
    _live_init, _live_set, _live_clear, _live_publish_turn,
)


def run_simulation(mid):
    """Worker: run one headless match and store the replay (names hidden)."""
    import time as _t
    import pygame
    from main import Match
    from recorder import ReplayRecorder, RecordingFX

    m = store.get_match(mid)
    if m is None:
        raise RuntimeError(f"match row {mid} not found in storage")
    store.set_status(mid, "running")
    _live_init(mid)          # wait-screen listeners start seeing turn/quip updates
    _live_set(mid, queue_pos=0)  # by definition — we just dequeued this one
    try:
        if not pygame.get_init():
            pygame.init()
            pygame.display.set_mode((C.WIDTH, C.HEIGHT))
        sharp = m["sharp"].split(",")
        rec = ReplayRecorder(every=2)
        fx = RecordingFX(rec)

        # Random A↔green/B↔blue assignment for true blind voting. If the
        # caller didn't pre-pick (legacy match rows), pick now.
        import random as _r
        flip = MATCH_FLIP.pop(mid, None)
        if flip is None:
            flip = _r.random() < 0.5
        # Persist so the worker, reveal endpoint and replay all agree.
        store.set_flip(mid, flip)

        # If flipped, swap which model the engine assigns to fighter1 vs fighter2
        # (fighter1 is rendered GREEN on the left, fighter2 BLUE on the right).
        if flip:
            slot_left, slot_right = m["model_b"], m["model_a"]
        else:
            slot_left, slot_right = m["model_a"], m["model_b"]
        mm = MATCH_MODES.get(mid, {})
        # BYOK: consume the per-match key (if any) and pass into Match.
        # Popping here (not in finally) means we never re-read the key
        # even if the sim somehow got restarted for the same mid.
        byok = MATCH_API_KEYS.pop(mid, None)
        mode = mm.get("mode") or m.get("mode") or "macro"
        weapon = mm.get("weapon") or m.get("weapon") or "sword"
        arena = mm.get("arena") or m.get("arena") or "normal"
        blindfolded = mm.get("blindfolded") if "blindfolded" in mm else m.get("blindfolded", False)
        # ---- benchmark spec v1.0 knobs (recorded at request time) ----
        seed = mm.get("seed", None)
        if seed is None:
            seed = _row_get(m, "seed")
        match_length = mm.get("match_length") or _row_get(m, "match_length") or "full"
        fallback_policy = (mm.get("fallback_policy")
                           or _row_get(m, "fallback_policy") or "operational")
        match = Match(slot_left, slot_right, sharp, fx,
                      log_path=os.path.join(store.root, f"log_{mid}.json"),
                      mode=mode,
                      weapon=weapon,
                      arena=arena,
                      blindfolded=blindfolded,
                      api_key=byok,
                      seed=seed,
                      match_length=match_length,
                      fallback_policy=fallback_policy)
        # blind mode: hide model identity in the replay itself
        if m["blind"]:
            match.f1.name = match.b1.label = BLIND_NAMES["a"]
            match.f2.name = match.b2.label = BLIND_NAMES["b"]
        rec.attach(match)

        # ---------- pre-fight trash talk -----------------------------------
        # Each brain gets to throw one line at the OTHER model's display name.
        # Mocks return canned lines instantly; real models go through
        # chat_with_timeout (≤15s budget). Captured server-side, in canvas
        # coordinates, so the blind/flip stays consistent.
        try:
            from brains import pre_fight_quip
            name_left  = C.ARENA_MODELS.get(slot_left,  slot_left)
            name_right = C.ARENA_MODELS.get(slot_right, slot_right)
            weap = MATCH_MODES.get(mid, {}).get("weapon", "sword")
            quip_a = pre_fight_quip(match.b1, name_right, weapon=weap)
            quip_b = pre_fight_quip(match.b2, name_left,  weapon=weap)
            rec.set_quips(quip_a, quip_b)
            # Publish to the wait-screen the instant they're ready — these
            # generate BEFORE the physics loop starts, so users see the
            # trash-talk within ~5-15s instead of waiting the full 30-90s
            # for the replay JSON. Canvas-side keys (a/b), no model names.
            _live_set(mid, quips={"a": quip_a, "b": quip_b})
        except Exception as e:
            print(f"[quip] failed: {e}")
        # Budget SIM frames only — LLM thinking time must not eat the match.
        # Hard wall-clock ceiling protects against a hung brain.
        # Per-weapon deadline. Melee (sword/dagger/spear/flail) completes
        # in 60-120s for a normal 24-turn match with two real LLMs.
        # Bow matches are structurally slower: fighters fight at
        # ~450px distance (kite range), arrows miss more than melee
        # swings, and gravity + wind lead to more turns before a hit
        # lands. Live data: a 5-turn bow match hit the 3-min cap at
        # 74 vs 59 HP and got decided "on points" — user perceives
        # this as "match stopped mid-way" (see replay 1d0a73faf1d6,
        # 2026-07-28). Bumping bow to 5 min buys enough headroom for
        # a full 24-turn ranged exchange without breaking the queue-
        # DoS protection that 3-min was designed to prevent.
        # Was flat 3*60 (leftover debug value was 45*60, fixed in
        # 561a8ba).
        deadline_seconds = 5 * 60 if match.weapon == "bow" else 3 * 60
        deadline = _t.time() + deadline_seconds
        sim_frames = 0
        # Live wait-screen ticker: publish each turn to LIVE_STATE the moment
        # it finalizes (hits appended). Rule: match.log[i] is finalized once
        # match.log has grown past i (i.e. the NEXT turn started) OR the
        # match is over. Watching len() avoids racing with the PH_SIM ->
        # PH_THINK phase transition.
        last_published = 0
        _live_set(mid, total_turns=match.max_turns,
                  match_length=match.match_length,
                  seed=match.seed, started_at=_t.time())
        def _publish_finalized():
            nonlocal last_published
            # Everything before the last entry is guaranteed finalized.
            target = len(match.log) - 1
            if match.phase == Match.PH_OVER:
                target = len(match.log)   # include the very last entry too
            while last_published < target:
                _live_publish_turn(mid, match.log[last_published],
                                   match.f1, match.f2, flip)
                last_published += 1
        last_phase = None
        while match.phase != Match.PH_OVER and _t.time() < deadline \
                and sim_frames < 60 * 60 * 10:
            # User-initiated cancel (action-plan §13). Checked every frame
            # while we're waiting on inference; we can't interrupt an
            # in-flight HTTP call, but we never start the next turn.
            if store.is_cancelled(mid):
                store.set_status(mid, "error", "cancelled by user")
                _obs_bump("matches_cancelled")
                _live_set(mid, cancelled=True)
                return
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
            _publish_finalized()
            if match.phase != last_phase:
                # Progress-timeline signal for the wait screen: THINKING =
                # "models are deciding", SIM = "physics resolving". Cheap
                # (only writes on transition) and it's the difference between
                # a progress bar the user trusts and a spinner they don't.
                last_phase = match.phase
                _live_set(mid, phase=match.phase)
            if match.phase == Match.PH_THINK:
                # Publish what the user is actually waiting for: "prompting
                # the models", not a fake progress bar (action-plan §13).
                _live_set(mid, phase="prompting",
                          thinking_s=round(_t.time() - match._turn_started_at["1"], 1))
                _t.sleep(0.02)      # don't burn CPU while LLMs think
            else:
                _live_set(mid, phase="simulating")
                sim_frames += 1
        _publish_finalized()   # flush the final turn(s)
        for _ in range(90):
            match.update(1 / 60, False)
            fx.update(1 / 60)
            rec.tick()
        if match.result is None:    # timeout/ceiling hit mid-match:
            match._finish()         # decide on points from current HP
        res = match.result
        if res["winner"] is None:
            side = "draw"
        else:
            side = "a" if res["winner"] == match.f1.name else "b"

        # ---------- post-fight commentary / roast --------------------------
        # We use whichever brain is more available (winner's by default). The
        # commentator gets the REAL model names; the public reveal only shows
        # it after the voter has cast their vote (handled by /api/vote/{id}).
        commentary = ""
        try:
            from brains import commentator_roast
            wname_real = (C.ARENA_MODELS.get(slot_left, slot_left)
                          if side == "a" else
                          C.ARENA_MODELS.get(slot_right, slot_right))
            lname_real = (C.ARENA_MODELS.get(slot_right, slot_right)
                          if side == "a" else
                          C.ARENA_MODELS.get(slot_left, slot_left))
            if side == "draw":
                wname_real = "Fighter A"; lname_real = "Fighter B"
            # Commentator = the WINNING brain (loser roasting themselves reads weird).
            commentator = match.b1 if side == "a" else match.b2
            commentary = commentator_roast(
                commentator, wname_real, lname_real, res["method"],
                res["turns"], match.weapon, sharp,
                final_hp=res.get("final_hp", {}))
        except Exception as e:
            print(f"[commentary] failed: {e}")

        replay = rec.build()
        prov = match.build_provenance()
        store.finish_match(mid, side, res["method"], res["turns"],
                           replay, commentary=commentary, provenance=prov)
        _obs_bump("matches_done")
        _obs_latency([prov.get("latency_ms_a"), prov.get("latency_ms_b")])
        if prov.get("fallback_used"):
            _obs_bump("matches_with_fallback")
    except Exception as e:
        import traceback
        traceback.print_exc()
        _obs_bump("matches_error")
        _obs_error(e, "run_simulation")
        store.set_status(mid, "error", _safe_err(e))
    finally:
        # Free the per-match config dict now that the sim is done. Without
        # this, MATCH_MODES grew unbounded for the life of the process
        # (~300 bytes/match, small but real on a long-running instance).
        # MATCH_FLIP already pops itself on line 139 above; this closes
        # the matching leak on the mode/weapon/arena side.
        MATCH_MODES.pop(mid, None)
        # Defensive: normally MATCH_API_KEYS[mid] is popped BEFORE Match()
        # is constructed. If an exception fired between the request handler
        # stashing the key and the worker consuming it, the entry would
        # linger — this keeps the map bounded regardless of failure path.
        MATCH_API_KEYS.pop(mid, None)
        # Give clients a beat to fetch the final tick before the state
        # disappears (their poll is every 1.5s; a 3s window covers it).
        # Then wipe LIVE_STATE so long-running processes don't accumulate.
        def _delayed_clear(_mid=mid):
            _t.sleep(3.0)
            _live_clear(_mid)
        threading.Thread(target=_delayed_clear, daemon=True).start()


def worker_loop():
    while True:
        mid = jobs.get()
        try:
            run_simulation(mid)
        except Exception as e:          # never let the worker die
            import traceback
            traceback.print_exc()
            try:
                store.set_status(mid, "error", _safe_err(e))
            except Exception:
                pass


# ===========================================================================
# Tournaments — single-elim brackets of 4 or 8 models.
# Each round runs every match SYNCHRONOUSLY through run_simulation so the
# bracket state machine is dead simple. Tournaments live in their own queue
# / worker so they don't starve the single-match queue.
# ===========================================================================


def _adjust_round_seeding(round_models):
    """Standard tournament bracket order so 1 vs N, 2 vs N-1, etc.
    For an 8-tournament: [s1,s2,s3,s4,s5,s6,s7,s8] -> [s1,s8,s4,s5,s3,s6,s2,s7].
    For a 4-tournament:  [s1,s2,s3,s4]            -> [s1,s4,s2,s3]."""
    n = len(round_models)
    if n == 8:
        order = [0, 7, 3, 4, 2, 5, 1, 6]
    elif n == 4:
        order = [0, 3, 1, 2]
    else:                                         # arbitrary even N
        order = []
        for i in range(n // 2):
            order += [i, n - 1 - i]
    return [round_models[i] for i in order]


def _run_one_tournament_match(t, round_n, slot, model_a, model_b):
    """Queue a single tournament fight via the normal storage/sim path,
    wait for it, then return the WINNER MODEL ID (or model_a on draw — by
    seed order)."""
    sharp = t["sharp"].split(",") if isinstance(t["sharp"], str) else list(t["sharp"])
    weapon = t.get("weapon") or "sword"
    t_mode = t.get("mode", "macro")
    t_arena = t.get("arena", "normal")
    mid = store.create_match(model_a, model_b, sharp, blind=True,
                             weapon=weapon, mode=t_mode, arena=t_arena)
    # Same arena / mode for the whole tournament — MATCH_MODES is the
    # in-memory routing dict for the sim worker; the persistent match
    # row now also carries mode/arena for correct elo cell attribution.
    MATCH_MODES[mid] = {"mode": t_mode, "weapon": weapon, "arena":  t_arena}
    # Tournaments are not user-voted, so we always use flip=False — the
    # bracket viewer cares about model identity, not blind canvas slots.
    MATCH_FLIP[mid] = False
    store.bind_tournament_match(t["id"], round_n, slot, mid)
    # Run the simulation INLINE in this worker thread (not via the single-
    # match queue) so we don't deadlock if the queue is busy.
    run_simulation(mid)
    m = store.get_match(mid)
    if m["status"] != "done":
        # error / timeout — seed-1 (higher seed) advances by default
        return model_a
    winner_side = m["winner_side"]
    if winner_side == "a":  return model_a
    if winner_side == "b":  return model_b
    return model_a   # draw → higher seed advances


def run_tournament(tid):
    """Play out a single-elim bracket. Updates progress after every match."""
    t = store.get_tournament(tid)
    if not t:
        return
    store.set_tournament_status(tid, "running")
    try:
        round_models = _adjust_round_seeding(t["models"])
        round_n = 1
        max_rounds = (t["size"]).bit_length() - 1  # 4 -> 2, 8 -> 3

        # Seed all R1 matches into the bracket table up-front so the UI can
        # render the empty bracket immediately.
        for slot in range(len(round_models) // 2):
            a = round_models[slot * 2]
            b = round_models[slot * 2 + 1]
            store.add_tournament_match(tid, round_n, slot, a, b)
        store.set_tournament_round(tid, round_n)

        while round_n <= max_rounds:
            winners = []
            for slot in range(len(round_models) // 2):
                a = round_models[slot * 2]
                b = round_models[slot * 2 + 1]
                print(f"[tournament {tid}] R{round_n} slot {slot}: {a} vs {b}")
                w = _run_one_tournament_match(t, round_n, slot, a, b)
                store.set_tournament_match_winner(tid, round_n, slot, w)
                winners.append(w)
            round_n += 1
            round_models = winners
            if round_n <= max_rounds:
                store.set_tournament_round(tid, round_n)
                # Seed the next round's pending matches into the table.
                for slot in range(len(round_models) // 2):
                    a = round_models[slot * 2]
                    b = round_models[slot * 2 + 1]
                    store.add_tournament_match(tid, round_n, slot, a, b)
        # round_models now has 1 entry — the champion
        champion = round_models[0]
        store.finish_tournament(tid, champion)
        print(f"[tournament {tid}] CHAMPION: {champion}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.set_tournament_status(tid, "error", _safe_err(e))


def tournament_worker_loop():
    while True:
        tid = tournament_jobs.get()
        try:
            run_tournament(tid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                store.set_tournament_status(tid, "error", _safe_err(e))
            except Exception:
                pass


