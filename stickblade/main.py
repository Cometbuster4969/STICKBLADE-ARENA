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
                    choices=["sword", "flail", "bow"])
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
                 mode="macro", weapon="sword", arena="normal"):
        from weapons import WEAPONS, WEAPON_ZONES
        self.weapon = weapon if weapon in WEAPONS else "sword"
        # keep only zones valid for this weapon; default to first zone
        zs = [z for z in sharp if z in WEAPON_ZONES[self.weapon]]
        self.sharp = zs or [WEAPON_ZONES[self.weapon][0]]
        self.fx = fx
        self.log_path = log_path
        self.mode = mode if mode in ("macro", "joint") else "macro"
        # ---- arena modifier ----
        self.arena = arena if arena in ("normal", "ice", "low_gravity") else "normal"
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
        self.b1 = make_brain(p1_kind, self.sharp, mode=self.mode,
                             weapon=self.weapon)
        self.b2 = make_brain(p2_kind, self.sharp, mode=self.mode,
                             weapon=self.weapon)
        if self.b1.label == self.b2.label:          # mirror match: disambiguate
            self.b1.label += " #1"
            self.b2.label += " #2"
        self.f1.name, self.f2.name = self.b1.label, self.b2.label
        self.turn = 0
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
        s1 = build_state(self.f1, self.f2, self.turn, C.MAX_TURNS, self.last_events, arena=self.arena)
        s2 = build_state(self.f2, self.f1, self.turn, C.MAX_TURNS, self.last_events, arena=self.arena)
        self.pending = {}

        def work():
            r1 = self.b1.decide_with_timeout(s1)
            r2 = self.b2.decide_with_timeout(s2)
            self.pending = {"r1": r1, "r2": r2}
        threading.Thread(target=work, daemon=True).start()
        self.phase = Match.PH_THINK

    def _begin_sim(self, r1, r2):
        self.thoughts = [r1["thought"], r2["thought"]]
        am1 = self.arrows[1] if self.arrows else None
        am2 = self.arrows[2] if self.arrows else None
        if self.mode == "joint":
            from joint_mode import JointController
            self.ctrl = (
                JointController(self.f1, r1["joints"], r1["footwork"],
                                fire=r1.get("fire", False),
                                arrow_mgr=am1, enemy=self.f2),
                JointController(self.f2, r2["joints"], r2["footwork"],
                                fire=r2.get("fire", False),
                                arrow_mgr=am2, enemy=self.f1),
            )
        else:
            self.ctrl = (MoveController(self.f1, r1["action"], r1["footwork"],
                                        arrow_mgr=am1, enemy=self.f2),
                         MoveController(self.f2, r2["action"], r2["footwork"],
                                        arrow_mgr=am2, enemy=self.f1))
        self.log.append({"turn": self.turn,
                         self.f1.name: r1, self.f2.name: r2})
        self.sim_t = 0.0
        self.phase = Match.PH_SIM

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
            if self.pending and "r1" in self.pending:
                self._begin_sim(self.pending["r1"], self.pending["r2"])
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
                if self.f1.dead or self.f2.dead or self.turn >= C.MAX_TURNS:
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
                       "result": self.result, "turns": self.log}, fp, indent=2)
        if not self.log_path:   # tournament runner prints its own summary
            print(f"[match] {self.winner}  — full reasoning log saved to {fn}")


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
                    match = Match(p1, p2, sharp, fx, mode=args.mode, weapon=args.weapon)

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
        rend.draw_hud(screen, match.f1, match.f2, match.turn, C.MAX_TURNS, sharp,
                      {"THINKING": "🧠 LLMs are thinking…", "SIM": "",
                       "BANNER": "FIGHT!", "OVER": ""}.get(match.phase, ""))
        rend.draw_thought(screen, match.f1, match.thoughts[0], 0)
        rend.draw_thought(screen, match.f2, match.thoughts[1], 1)

        if fx.flash > 0:
            fl = pygame.Surface((C.WIDTH, C.HEIGHT))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(200 * fx.flash))
            screen.blit(fl, (0, 0))
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
