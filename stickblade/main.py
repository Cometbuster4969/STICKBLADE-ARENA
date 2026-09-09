"""STICKBLADE ARENA — LLM vs LLM physics sword duel (Toribash-style turns).

Usage:
    python main.py                         # interactive setup in terminal
    python main.py --p1 gpt --p2 gemini --sharp tip
    python main.py --p1 berserker --p2 duelist --sharp edge,tip   # mock vs mock
Keys in game:  SPACE pause | F fast-forward | R rematch | ESC quit
"""
import argparse
import json
import sys
import threading
import time

import pygame
import pymunk

import config as C
from ragdoll import Fighter, make_ground


def _empty_telemetry():
    """Per-fighter accumulator for the per-match provenance record."""
    return {"turns": 0, "latency_ms_total": 0.0, "latency_ms_max": 0.0,
            "fallback_turns": 0, "invalid_actions": 0,
            "invalid_action_examples": [], "models_used": {},
            "providers_used": {}, "last_model_used": "",
            "last_provider_used": "",
            # §33: billed tokens, as reported by the provider. Accumulated
            # per fighter so cost per match is measured, not estimated.
            "prompt_tokens": 0, "completion_tokens": 0, "api_calls": 0}
from moves import MoveController
from combat import CombatSystem
from brains import make_brain, build_state
from render import Renderer, FX


# ------------------------------------------------------------------ setup
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", default=None, help="gpt | gemini | duelist | berserker")
    ap.add_argument("--p2", default=None)
    ap.add_argument("--sharp", default=None,
                    help="comma list of: tip,edge,back_edge,pommel")
    ap.add_argument("--mode", default="macro", choices=["macro", "joint"],
                    help="macro = tactician picks moves; joint = raw "
                         "Toribash-style joint control")
    ap.add_argument("--weapon", default="sword",
                    choices=["sword", "dagger", "spear", "flail", "bow"])
    ap.add_argument("--arena", default="normal",
                    choices=["normal", "ice", "low_gravity"])
    ap.add_argument("--length", default="full",
                    choices=["sprint", "standard", "full"],
                    help="match length: sprint=4 turns, standard=12, full=24")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed the RNG + scripted brains for a "
                         "reproducible match")
    ap.add_argument("--fallback-policy", default="operational",
                    choices=["strict", "operational", "demo"],
                    help="strict = any fallback makes the match "
                         "ranking-ineligible")
    ap.add_argument("--json-out", default=None,
                    help="write match provenance + result as JSON here")
    return ap.parse_args()


def interactive_setup(args):
    def ask(prompt, valid, default):
        try:
            v = input(f"{prompt} [{default}]: ").strip().lower()
        except EOFError:
            v = ""
        return v if v else default

    p1 = args.p1 or ask("Player 1 brain (gpt/gemini/duelist/berserker)", None, "gpt")
    p2 = args.p2 or ask("Player 2 brain (gpt/gemini/duelist/berserker)", None, "gemini")
    sharp_in = args.sharp or ask("Sharpened zone(s) tip/edge/back_edge/pommel, comma-sep", None, "tip")
    sharp = [z.strip() for z in sharp_in.split(",") if z.strip()] or ["tip"]
    return p1, p2, sharp


# ------------------------------------------------------------------ match
class Match:
    PH_THINK, PH_SIM, PH_BANNER, PH_OVER = "THINKING", "SIM", "BANNER", "OVER"

    def __init__(self, p1_kind, p2_kind, sharp, fx, log_path=None,
                 mode="macro", weapon="sword", arena="normal", api_key=None,
                 blindfolded=False, seed=None, match_length="full",
                 max_turns=None, fallback_policy="operational"):
        from weapons import WEAPONS, WEAPON_ZONES
        from benchmark import (max_turns_for, MATCH_LENGTHS,
                               DEFAULT_MATCH_LENGTH, DEFAULT_FALLBACK_POLICY,
                               FALLBACK_POLICIES)
        self.weapon = weapon if weapon in WEAPONS else "sword"
        # keep only zones valid for this weapon; default to first zone
        zs = [z for z in sharp if z in WEAPON_ZONES[self.weapon]]
        self.sharp = zs or [WEAPON_ZONES[self.weapon][0]]
        self.fx = fx
        self.log_path = log_path
        self.mode = mode if mode in ("macro", "joint") else "macro"
        # ---- benchmark v1.0 knobs -------------------------------------
        # seed: makes physics + every scripted brain reproducible, so a
        # stored action log can be replayed bit-identically. Also seeds
        # Python's global RNG (which the scripted fallback brains draw
        # from) — restored on match end so the rest of the process is
        # unaffected.
        self.seed = seed
        self.match_length = (match_length or DEFAULT_MATCH_LENGTH).lower()
        if self.match_length not in MATCH_LENGTHS:
            self.match_length = DEFAULT_MATCH_LENGTH
        self.max_turns = int(max_turns) if max_turns else \
            max_turns_for(self.match_length)
        self.fallback_policy = (fallback_policy
                                if fallback_policy in FALLBACK_POLICIES
                                else DEFAULT_FALLBACK_POLICY)
        self._prev_random_state = None
        if seed is not None:
            import random as _random
            self._prev_random_state = _random.getstate()
            _random.seed(int(seed))
        # Per-fighter telemetry + the deterministic action log (spec §8).
        self.telemetry = {
            1: _empty_telemetry(), 2: _empty_telemetry(),
            "turns": [], "started": time.time(),
        }
        self.action_log = []
        # ---- arena modifier ----
        self.arena = arena if arena in ("normal", "ice", "low_gravity") else "normal"
        # Tier S #3: blindfolded variant — build_state() strips derived
        # spatial hints, forcing the model to reason from raw coords.
        self.blindfolded = bool(blindfolded)
        self.space = pymunk.Space()
        if self.arena == "low_gravity":
            self.space.gravity = (C.GRAVITY[0], C.GRAVITY[1] * 0.35)  # moon-ish
        else:
            self.space.gravity = C.GRAVITY
        self.space.damping = C.SPACE_DAMPING
        # Ice floor: pass a friction multiplier into make_ground; also
        # reduce limb friction so fighters actually slide on impact, AND
        # raise space damping toward 1.0 so the slide isn't instantly
        # killed by the global air-drag (was 0.99 → ~45% horizontal vel
        # loss per second, which made ice and stone feel identical).
        ground_friction_mult = 0.10 if self.arena == "ice" else 1.0
        make_ground(self.space, friction_mult=ground_friction_mult)
        if self.arena == "ice":
            self.space.damping = 0.996   # slides last ~2x longer than normal
            # (0.99 → ~45% horizontal-vel loss/s; 0.996 → ~21%/s)
        self.f1 = Fighter(self.space, 430, 1, C.C_P1, C.C_P1_DARK,
                          p1_kind.upper(), 1, weapon=self.weapon)
        self.f2 = Fighter(self.space, C.WIDTH - 430, -1, C.C_P2, C.C_P2_DARK,
                          p2_kind.upper(), 2, weapon=self.weapon)
        if self.arena == "ice":
            # shins are pinned at 1.6 in ragdoll._build — override here so
            # contact friction (sqrt(a.f * b.f)) actually drops on ice.
            # 1.6 * 0.15 → 0.49; 0.2 * 0.15 → 0.17 (≈3x more slippery).
            for f in (self.f1, self.f2):
                for nm in ("shin_f", "shin_b"):
                    f.shapes[nm].friction = 0.2
        self.f1.enemy, self.f2.enemy = self.f2, self.f1
        self.combat = CombatSystem(self.space, {1: self.f1, 2: self.f2},
                                   self.sharp, fx)
        # arrows (bow only)
        from weapons import ArrowManager
        self.arrows = {1: ArrowManager(self.space, self.f1),
                       2: ArrowManager(self.space, self.f2)} \
            if self.weapon == "bow" else None
        # api_key: per-match BYOK OpenRouter key. Threaded down into both
        # brains so their retry+buddy failover ladders also use it. Never
        # stored on self — only lives inside the Brain instances' HTTP
        # clients for the duration of this Match's lifetime.
        # What the caller ASKED for, before any buddy-model/fallback swap.
        # Reported as model_requested_* in the provenance record.
        self._requested = {1: p1_kind, 2: p2_kind}
        self.b1 = make_brain(p1_kind, self.sharp, mode=self.mode,
                             weapon=self.weapon, api_key=api_key,
                             seed=None if seed is None else int(seed))
        self.b2 = make_brain(p2_kind, self.sharp, mode=self.mode,
                             weapon=self.weapon, api_key=api_key,
                             seed=None if seed is None else int(seed) + 1)
        if self.b1.label == self.b2.label:          # mirror match: disambiguate
            self.b1.label += " #1"
            self.b2.label += " #2"
        self.f1.name, self.f2.name = self.b1.label, self.b2.label
        self.turn = 0
        self.turn_distance = 0     # torso separation at the start of this turn
        self.phase = Match.PH_BANNER
        self.phase_t = 1.2
        self.sim_t = 0.0
        self.ctrl = (None, None)
        self.thoughts = ["", ""]
        self.last_events = []
        self.pending = None
        self.winner = None
        self.result = None
        self.log = []

    # ---------- LLM querying (background thread so UI stays alive) ----------
    def _start_thinking(self):
        # fighters crossed during the last exchange? turn them around so
        # poses/strikes face the enemy again (footwork already self-corrects)
        for f in (self.f1, self.f2):
            dx = f.enemy.pos().x - f.pos().x
            if abs(dx) > 2 and (1 if dx > 0 else -1) != f.facing:
                f.turn_around()
        self.turn += 1
        # Distance at decision time, straight from the physics. Captured for
        # the per-turn decision log (below) — the {action, footwork, distance}
        # triple that makes "why did this fighter not move?" answerable from
        # the replay JSON instead of by re-running the match.
        self.turn_distance = round((self.f2.pos() - self.f1.pos()).length)
        s1 = build_state(self.f1, self.f2, self.turn, self.max_turns,
                         self.last_events, arena=self.arena,
                         blindfolded=self.blindfolded)
        s2 = build_state(self.f2, self.f1, self.turn, self.max_turns,
                         self.last_events, arena=self.arena,
                         blindfolded=self.blindfolded)
        self.pending = {}
        self._turn_t0 = time.time()
        self._turn_started_at = {"1": self._turn_t0, "2": self._turn_t0}

        def work(key, brain, state):
            # One thread PER FIGHTER. The two API calls are independent, so
            # running them concurrently halves per-turn wall clock — the
            # single biggest latency win available (action-plan §17).
            # Safe because each brain owns its own HTTP client and the only
            # shared state touched is the cooldown map (dict writes are
            # atomic under the GIL).
            t0 = time.time()
            try:
                reply = brain.decide_with_timeout(state)
            except Exception as e:                       # pragma: no cover
                reply = {"action": "ready", "footwork": "hold",
                         "thought": f"[error] {str(e)[:60]}",
                         "_fallback": True, "_provider_used": "error"}
            self.pending[key] = (reply, (time.time() - t0) * 1000.0)

        # Scripted-vs-scripted matches (mock:*/bot:* — every offline test,
        # the demo replay, and balance sweeps) resolve INLINE. Threading
        # them would make the number of think-phase physics steps depend on
        # thread scheduling, and the think phase steps the world forward
        # once per frame while it waits — so a slow thread would silently
        # move the fighters apart before the turn began. Seeded matches must
        # replay bit-for-bit (action-plan §8), so no threads here.
        if getattr(self.b1, "scripted", False) and \
                getattr(self.b2, "scripted", False):
            for key, brain, state in (("1", self.b1, s1), ("2", self.b2, s2)):
                work(key, brain, state)
        else:
            for key, brain, state in (("1", self.b1, s1), ("2", self.b2, s2)):
                threading.Thread(target=work, args=(key, brain, state),
                                 daemon=True).start()
        self.phase = Match.PH_THINK

    # ---------------- telemetry + deterministic action log ----------------
    def _record_turn(self, r1, r2, lat1_ms, lat2_ms):
        """Stamp one turn's provenance onto self.telemetry + action_log.

        Side keys are FIGHTER ids (1 = left/green = canvas "a",
        2 = right/blue = canvas "b"); server.py maps them to canvas
        sides when persisting, so the flip logic stays in one place.
        """
        for fid, reply, lat in ((1, r1, lat1_ms), (2, r2, lat2_ms)):
            t = self.telemetry[fid]
            t["turns"] += 1
            t["latency_ms_total"] += float(lat or 0.0)
            t["latency_ms_max"] = max(t["latency_ms_max"], float(lat or 0.0))
            if reply.get("_fallback"):
                t["fallback_turns"] += 1
            if reply.get("_invalid_action") or reply.get("_invalid_footwork"):
                t["invalid_actions"] += 1
            if reply.get("_invalid_action"):
                t["invalid_action_examples"].append(reply["_invalid_action"])
            model_used = reply.get("_model_used") or ""
            provider = reply.get("_provider_used") or ""
            if model_used:
                t["models_used"][model_used] = t["models_used"].get(model_used, 0) + 1
            if provider:
                t["providers_used"][provider] = t["providers_used"].get(provider, 0) + 1
            t["last_model_used"] = model_used or t["last_model_used"]
            t["last_provider_used"] = provider or t["last_provider_used"]
            # Provider-reported token usage for this turn (§33). The brain
            # accumulates it across retries and buddy fallbacks, so a match
            # that fell back still reports what it actually burned.
            use = reply.get("_usage") or {}
            try:
                t["prompt_tokens"] += int(use.get("prompt_tokens") or 0)
                t["completion_tokens"] += int(use.get("completion_tokens") or 0)
                t["api_calls"] += int(use.get("calls") or 0)
            except (TypeError, ValueError):
                pass
        def _turn_model(fid, reply):
            m = reply.get("_model_used") or ""
            if m in ("Fighter A", "Fighter B") or not m:
                # Blind-alias or unreported (scripted baseline): the roster
                # id the user picked is the auditable answer.
                return self._req_kind(fid) or m
            return m

        self.telemetry["turns"].append({
            "turn": self.turn,
            "a": {"latency_ms": round(lat1_ms, 1),
                  "fallback": bool(r1.get("_fallback")),
                  "invalid": bool(r1.get("_invalid_action")
                                  or r1.get("_invalid_footwork")),
                  "model": _turn_model(1, r1),
                  "provider": r1.get("_provider_used", "")},
            "b": {"latency_ms": round(lat2_ms, 1),
                  "fallback": bool(r2.get("_fallback")),
                  "invalid": bool(r2.get("_invalid_action")
                                  or r2.get("_invalid_footwork")),
                  "model": _turn_model(2, r2),
                  "provider": r2.get("_provider_used", "")},
        })
        # Deterministic replay log: the exact decisions, in order. Together
        # with the seed + physics version this is what makes a published
        # result reproducible (spec §8).
        entry = {"turn": self.turn,
                 "a": {"action": r1.get("action"), "footwork": r1.get("footwork")},
                 "b": {"action": r2.get("action"), "footwork": r2.get("footwork")}}
        if self.mode == "joint":
            entry["a"]["joints"] = r1.get("joints")
            entry["b"]["joints"] = r2.get("joints")
            entry["a"]["fire"] = bool(r1.get("fire"))
            entry["b"]["fire"] = bool(r2.get("fire"))
        self.action_log.append(entry)

    def build_provenance(self):
        """Per-match provenance record (benchmark spec v1.0 §1)."""
        from benchmark import provenance
        # Blind matches rename both fighters to "Fighter A"/"Fighter B"
        # (server.py) so no model name can leak into a pre-vote payload.
        # Scripted brains carry no `.model`, so _model_id_of() falls back to
        # that alias — which would write "Fighter B" into the dataset as the
        # model that actually played. The requested roster id is the truth
        # whenever the reported id is a blind alias or missing.
        def _resolve(fid, reported):
            if reported and reported not in ("Fighter A", "Fighter B"):
                return reported
            return self._req_kind(fid) or reported

        def _sum(fid):
            t = self.telemetry[fid]
            n = max(1, t["turns"])
            return {
                "model_used": _resolve(fid, t["last_model_used"]),
                "provider_used": t["last_provider_used"],
                "models_used": t["models_used"],
                "providers_used": t["providers_used"],
                "latency_ms": round(t["latency_ms_total"] / n, 1),
                "latency_ms_max": round(t["latency_ms_max"], 1),
                "fallback_turns": t["fallback_turns"],
                "invalid_actions": t["invalid_actions"],
                "prompt_tokens": t["prompt_tokens"],
                "completion_tokens": t["completion_tokens"],
                "api_calls": t["api_calls"],
            }
        a, b = _sum(1), _sum(2)
        fb_used = bool(a["fallback_turns"] or b["fallback_turns"])
        return provenance(
            model_requested_a=self._req_kind(1),
            model_requested_b=self._req_kind(2),
            model_used_a=a["model_used"], model_used_b=b["model_used"],
            provider_used_a=a["provider_used"], provider_used_b=b["provider_used"],
            fallback_used=fb_used,
            latency_ms_a=a["latency_ms"], latency_ms_b=b["latency_ms"],
            seed=self.seed, match_length=self.match_length,
            fallback_policy=self.fallback_policy,
            invalid_actions_a=a["invalid_actions"],
            invalid_actions_b=b["invalid_actions"],
            prompt_tokens_a=a["prompt_tokens"],
            completion_tokens_a=a["completion_tokens"],
            prompt_tokens_b=b["prompt_tokens"],
            completion_tokens_b=b["completion_tokens"],
            api_calls_a=a["api_calls"], api_calls_b=b["api_calls"],
            latency_ms_max_a=a["latency_ms_max"],
            latency_ms_max_b=b["latency_ms_max"],
            models_used_a=a["models_used"], models_used_b=b["models_used"],
            providers_used_a=a["providers_used"],
            providers_used_b=b["providers_used"],
            turns=self.turn, weapon=self.weapon, arena=self.arena,
            mode=self.mode, blindfolded=self.blindfolded,
            sharp=",".join(self.sharp),
        )

    def _req_kind(self, fid):
        """The model id the user asked for (before buddy/fallback swaps)."""
        return self._requested.get(fid, "")

    def _pending_latency(self, key):
        """Latency (ms) recorded by the fighter's decision thread."""
        try:
            return float(self.pending.get(key, (None, 0.0))[1])
        except (TypeError, ValueError):
            return 0.0

    def _begin_sim(self, r1, r2):
        # A mock STANDING IN for a model the user actually picked (no API
        # key configured, or brain init failed) is a degraded turn exactly
        # like a timeout is. Stamping the same flag here makes every
        # downstream consumer honest in one place: the live wait-screen tick
        # (server._live_publish_turn -> fallback_a/b), recorder.fallback_turns
        # (the "scripted fallback in use" banner), and the per-side
        # fallback_turns_a/b that feed the reveal card's integrity row and the
        # leaderboard's fallback_rate. Declared baselines (bot:*/mock:*) are
        # never tagged by brains.make_brain, so they stay "clean" — they were
        # never claimed to be models in the first place.
        for _brain, _reply in ((self.b1, r1), (self.b2, r2)):
            if getattr(_brain, "mock_substitute", False):
                _reply.setdefault("_fallback", True)
        lat1 = self._pending_latency("1")
        lat2 = self._pending_latency("2")
        self._record_turn(r1, r2, lat1, lat2)
        self.thoughts = [r1["thought"], r2["thought"]]
        am1 = self.arrows[1] if self.arrows else None
        am2 = self.arrows[2] if self.arrows else None
        if self.mode == "joint":
            from joint_mode import JointController

            def _ctrl(f, r, enemy, am):
                # JointController needs r["joints"]. The scripted baselines
                # (every bot:* — see bots.py, which has no joint support at
                # all) return macro-shaped replies, so a joint match against
                # one of them used to die with KeyError('joints') and
                # status="error". Drive that fighter through the macro
                # executor instead, and record the fact on the reply so the
                # turn log doesn't claim it was joint-controlled.
                if "joints" in r:
                    return JointController(f, r["joints"], r["footwork"],
                                           fire=r.get("fire", False),
                                           arrow_mgr=am, enemy=enemy)
                r["_macro_in_joint"] = True
                return MoveController(f, r.get("action", "ready"),
                                      r.get("footwork", "hold"),
                                      arrow_mgr=am, enemy=enemy)

            self.ctrl = (_ctrl(self.f1, r1, self.f2, am1),
                         _ctrl(self.f2, r2, self.f1, am2))
        else:
            self.ctrl = (MoveController(self.f1, r1["action"], r1["footwork"],
                                        arrow_mgr=am1, enemy=self.f2),
                         MoveController(self.f2, r2["action"], r2["footwork"],
                                        arrow_mgr=am2, enemy=self.f1))
        self.log.append({"turn": self.turn,
                         self.f1.name: r1, self.f2.name: r2,
                         # Decision audit trail: canvas-side key ("a" = the
                         # green fighter1, "b" = blue fighter2) so consumers
                         # don't have to know the blind name mapping. This is
                         # what makes the "bow agents stopped repositioning"
                         # class of bug diagnosable after the fact — you can
                         # read {action, footwork, distance} for every turn
                         # and see the footwork going statue.
                         "decision": {"a": self._decision_ctx(r1),
                                      "b": self._decision_ctx(r2)}})
        self.sim_t = 0.0
        self.phase = Match.PH_SIM

    def _decision_ctx(self, r):
        """Compact {action, footwork, distance, fallback} for the turn log."""
        return {"action": r.get("action")
                        or ("joints" if r.get("joints") else "ready"),
                "footwork": r.get("footwork", "hold"),
                "distance": self.turn_distance,
                "fallback": bool(r.get("_fallback")),
                # Set when a macro-only brain (bot:*) fought inside a joint
                # match and was driven by the macro executor instead of
                # JointController. Keeps "this turn was joint-controlled"
                # from being implied by the match mode alone.
                "macro_in_joint": bool(r.get("_macro_in_joint"))}

    # ---------- physics ----------
    def step_physics(self, dt):
        self.combat.sim_time += dt
        for f in (self.f1, self.f2):
            f.update(dt)
        if self.arrows:
            self.arrows[1].update(dt)
            self.arrows[2].update(dt)
        self.space.step(dt)

    def update(self, frame_dt, fast):
        if self.phase == Match.PH_BANNER:
            self.phase_t -= frame_dt
            if self.phase_t <= 0:
                self._start_thinking()
        elif self.phase == Match.PH_THINK:
            # idle physics while brains think (fighters hold stance)
            for _ in range(C.SUBSTEPS):
                self.step_physics(C.DT)
            if self.pending and "1" in self.pending and "2" in self.pending:
                r1, _ = self.pending["1"]
                r2, _ = self.pending["2"]
                self._begin_sim(r1, r2)
        elif self.phase == Match.PH_SIM:
            scale = self.fx.time_scale()
            steps = C.SUBSTEPS * (3 if fast else 1)
            for _ in range(steps):
                dt = C.DT * scale
                t_frac = self.sim_t / C.TURN_SECONDS
                for c in self.ctrl:
                    c.update(min(1.0, t_frac))
                self.step_physics(dt)
                self.sim_t += dt
                if self.sim_t >= C.TURN_SECONDS:
                    break
            if self.sim_t >= C.TURN_SECONDS:
                self.last_events = self.combat.drain_events()
                for e in self.last_events:
                    self.log[-1].setdefault("hits", []).append(e)
                if self.f1.dead or self.f2.dead or self.turn >= self.max_turns:
                    self._finish()
                else:
                    self._start_thinking()
        elif self.phase == Match.PH_OVER:
            for _ in range(C.SUBSTEPS):
                self.step_physics(C.DT * self.fx.time_scale())

    def _finish(self):
        if self.f1.dead and self.f2.dead:
            self.winner = "DRAW — mutual destruction"
            self.result = {"winner": None, "method": "mutual_destruction"}
        elif self.f2.dead:
            self.winner = f"{self.f1.name} WINS"
            self.result = {"winner": self.f1.name, "method": "kill"}
        elif self.f1.dead:
            self.winner = f"{self.f2.name} WINS"
            self.result = {"winner": self.f2.name, "method": "kill"}
        else:
            if abs(self.f1.hp - self.f2.hp) < 0.5:
                self.winner = "DRAW — time out"
                self.result = {"winner": None, "method": "timeout_draw"}
            else:
                w = self.f1 if self.f1.hp > self.f2.hp else self.f2
                self.winner = f"{w.name} WINS on points"
                self.result = {"winner": w.name, "method": "points"}
        self.result.update({
            "turns": self.turn,
            "final_hp": {self.f1.name: round(self.f1.hp, 1),
                         self.f2.name: round(self.f2.hp, 1)},
        })
        self.phase = Match.PH_OVER
        fn = self.log_path or f"battle_log_{int(time.time())}.json"
        with open(fn, "w") as fp:
            json.dump({"sharp": self.sharp, "winner": self.winner,
                       "result": self.result, "turns": self.log,
                       # benchmark spec v1.0 — provenance + deterministic
                       # action log so a published result can be audited.
                       "provenance": self.build_provenance(),
                       "action_log": self.action_log}, fp, indent=2)
        # Restore the global RNG so seeding one match doesn't leak into
        # unrelated code (queue flips, FX jitter, other matches).
        if self._prev_random_state is not None:
            import random as _random
            _random.setstate(self._prev_random_state)
            self._prev_random_state = None
        if not self.log_path:   # tournament runner prints its own summary
            print(f"[match] {self.winner}  — full reasoning log saved to {fn}")


def _write_json_out(path, match):
    """Dump result + provenance + action log (used by tools/run_batch)."""
    import benchmark
    data = {"winner": match.winner, "result": match.result,
            "provenance": match.build_provenance(),
            "action_log": match.action_log,
            "integrity": benchmark.verify_replay(
                {"meta": {"provenance": match.build_provenance(),
                          "total_turns": match.turn},
                 "frames": []})}
    with open(path, "w") as fp:
        json.dump(data, fp, indent=2)
    print(f"[match] wrote {path}")


# ------------------------------------------------------------------ main
def main():
    args = parse_args()
    p1, p2, sharp = interactive_setup(args)
    print(f"\n=== STICKBLADE ARENA ===\n{p1.upper()}  vs  {p2.upper()}"
          f"   |   sharp zones: {', '.join(sharp)}\n")

    pygame.init()
    screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
    pygame.display.set_caption("STICKBLADE ARENA — LLM Duel")
    clock = pygame.time.Clock()
    rend = Renderer(screen)
    fx = FX()
    match = Match(p1, p2, sharp, fx, mode=args.mode, weapon=args.weapon)

    paused = False
    fast = False
    running = True
    while running:
        frame_dt = clock.tick(C.FPS) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_f:
                    fast = not fast
                elif ev.key == pygame.K_r:
                    fx = FX()
                    match = Match(p1, p2, sharp, fx, mode=args.mode,
                                  weapon=args.weapon, arena=args.arena,
                                  seed=args.seed, match_length=args.length,
                                  fallback_policy=args.fallback_policy)
                    if args.json_out:
                        _write_json_out(args.json_out, match)

        if not paused:
            match.update(frame_dt, fast)
            fx.update(frame_dt)

        # ---------------- draw ----------------
        import random as _r
        off = (_r.uniform(-fx.shake, fx.shake), _r.uniform(-fx.shake, fx.shake)) \
            if fx.shake > 0.3 else (0, 0)
        screen.blit(rend.bg, (0, 0))
        rend.draw_fx(screen, fx, off)
        for f in (match.f1, match.f2):
            rend.draw_fighter(screen, f, off)
            rend.draw_weapon(screen, f, match.sharp, off,
                             arrows=match.arrows[f.fid] if match.arrows else None)
        rend.draw_hud(screen, match.f1, match.f2, match.turn, match.max_turns, sharp,
                      {"THINKING": "🧠 LLMs are thinking…", "SIM": "",
                       "BANNER": "FIGHT!", "OVER": ""}.get(match.phase, ""))
        rend.draw_thought(screen, match.f1, match.thoughts[0], 0)
        rend.draw_thought(screen, match.f2, match.thoughts[1], 1)

        if fx.flash > 0:
            fl = pygame.Surface((C.WIDTH, C.HEIGHT))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(200 * fx.flash))
            screen.blit(fl, (0, 0))
        if match.phase == Match.PH_OVER and args.json_out and \
                not getattr(match, "_json_written", False):
            match._json_written = True
            _write_json_out(args.json_out, match)

        if match.phase == Match.PH_OVER:
            txt = rend.f_big.render(match.winner, True, (255, 220, 90))
            screen.blit(txt, (C.WIDTH // 2 - txt.get_width() // 2, C.HEIGHT // 2 - 60))
            sub = rend.f_sm.render("Press R for rematch — ESC to quit", True, C.C_DIM)
            screen.blit(sub, (C.WIDTH // 2 - sub.get_width() // 2, C.HEIGHT // 2 - 8))
        if paused:
            pt = rend.f_big.render("PAUSED", True, C.C_TEXT)
            screen.blit(pt, (C.WIDTH // 2 - pt.get_width() // 2, C.HEIGHT // 2))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
