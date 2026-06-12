"""Toribash-style rendering: dark arena, chunky stickmen, blood, damage numbers."""
import math
import random
import pygame
import config as C


def to_screen(p):
    return int(p[0]), int(C.HEIGHT - p[1])


class FX:
    """Particles, damage numbers, screen shake, slow motion."""

    def __init__(self):
        self.blood = []      # [x,y,vx,vy,life,r]
        self.stains = []     # [x,y,r]
        self.sparks = []
        self.numbers = []    # [x,y,text,color,life]
        self.shake = 0.0
        self.slowmo = 0.0
        self.flash = 0.0

    def hit(self, p, dmg, sharp, lethal, part):
        x, y = p
        n = int(min(46, 6 + dmg * 1.6)) if sharp else 3
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(40, 90 + dmg * 9)
            self.blood.append([x, y, math.cos(a) * sp,
                               math.sin(a) * sp + 80, random.uniform(0.5, 1.3),
                               random.uniform(1.5, 3.6)])
        if sharp:
            self.numbers.append([x, y + 18, f"-{dmg:.0f}" if not lethal else "FATAL!",
                                 (255, 90, 90) if not lethal else (255, 220, 60), 1.4])
            self.shake = max(self.shake, min(14, 3 + dmg * 0.35))
        else:
            self.numbers.append([x, y + 18, "blunt", (170, 174, 190), 0.9])
        if lethal:
            self.slowmo = 2.2
            self.flash = 0.35
            self.shake = 16

    def clash(self, p):
        x, y = p
        for _ in range(10):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 240)
            self.sparks.append([x, y, math.cos(a) * sp, math.sin(a) * sp,
                                random.uniform(0.15, 0.4)])
        self.shake = max(self.shake, 3)

    def update(self, dt):
        for arr, g in ((self.blood, -900), (self.sparks, -400)):
            for pt in arr:
                pt[0] += pt[2] * dt
                pt[1] += pt[3] * dt
                pt[3] += g * dt
                pt[4] -= dt
                if arr is self.blood and pt[1] < C.FLOOR_Y + 3 and pt[3] < 0:
                    if len(self.stains) < 260:
                        self.stains.append([pt[0], C.FLOOR_Y + random.uniform(0, 3),
                                            pt[5] * random.uniform(0.9, 1.7)])
                    pt[4] = 0
            arr[:] = [p for p in arr if p[4] > 0]
        for nrec in self.numbers:
            nrec[1] += 34 * dt
            nrec[4] -= dt
        self.numbers = [nr for nr in self.numbers if nr[4] > 0]
        self.shake = max(0.0, self.shake - 38 * dt)
        self.slowmo = max(0.0, self.slowmo - dt)
        self.flash = max(0.0, self.flash - dt)

    def time_scale(self):
        return 0.22 if self.slowmo > 0 else 1.0


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.f_big = pygame.font.SysFont("arialblack,arial", 40)
        self.f_med = pygame.font.SysFont("arial", 21, bold=True)
        self.f_sm = pygame.font.SysFont("arial", 16)
        self.f_tiny = pygame.font.SysFont("arial", 13)
        self.bg = self._make_bg()

    def _make_bg(self):
        s = pygame.Surface((C.WIDTH, C.HEIGHT))
        for y in range(C.HEIGHT):
            t = y / C.HEIGHT
            col = [int(a + (b - a) * t) for a, b in zip(C.C_BG_TOP, C.C_BG_BOT)]
            pygame.draw.line(s, col, (0, y), (C.WIDTH, y))
        fy = C.HEIGHT - C.FLOOR_Y
        pygame.draw.rect(s, C.C_FLOOR, (0, fy, C.WIDTH, C.HEIGHT - fy))
        pygame.draw.line(s, C.C_FLOOR_LINE, (0, fy), (C.WIDTH, fy), 3)
        for x in range(0, C.WIDTH, 64):
            pygame.draw.line(s, (46, 50, 66), (x, fy + 8), (x - 30, C.HEIGHT), 2)
        # spotlight
        glow = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (255, 255, 255, 14),
                            (C.WIDTH // 2 - 430, fy - 120, 860, 280))
        s.blit(glow, (0, 0))
        return s

    # ---------------- fighters ----------------
    def draw_fighter(self, surf, f, off):
        B = f.bodies
        col = tuple(int(c * 0.45) for c in f.color) if f.dead else f.color

        def P(body, local):
            w = body.local_to_world(local)
            return (int(w.x + off[0]), int(C.HEIGHT - w.y + off[1]))

        def seg(name, half, w, color=None):
            a = P(B[name], (0, half))
            b = P(B[name], (0, -half))
            pygame.draw.line(surf, color or col, a, b, w)
            pygame.draw.circle(surf, color or col, a, w // 2)
            pygame.draw.circle(surf, color or col, b, w // 2)

        # back limbs (darker)
        seg("thigh_b", 15, 9, f.dark)
        seg("shin_b", 15, 8, f.dark)
        seg("off_uarm", 13, 8, f.dark)
        seg("off_farm", 12, 7, f.dark)
        # torso & front limbs
        seg("torso", 28, 12)
        seg("thigh_f", 15, 10)
        seg("shin_f", 15, 9)
        seg("uarm", 13, 9)
        seg("farm", 12, 8)
        # head
        hp_ = P(B["head"], (0, 0))
        pygame.draw.circle(surf, col, hp_, 12)
        pygame.draw.circle(surf, tuple(min(255, c + 35) for c in col), hp_, 12, 2)
        eye = P(B["head"], (f.facing * 5.5, 2))
        if not f.dead:
            pygame.draw.circle(surf, (15, 16, 22), eye, 2)
        else:
            pygame.draw.line(surf, (15, 16, 22), (eye[0] - 3, eye[1] - 3), (eye[0] + 3, eye[1] + 3), 2)
            pygame.draw.line(surf, (15, 16, 22), (eye[0] - 3, eye[1] + 3), (eye[0] + 3, eye[1] - 3), 2)

    def draw_weapon(self, surf, f, sharp_zones, off, arrows=None):
        w = getattr(f, "weapon", "sword")
        if w == "flail":
            self._draw_flail(surf, f, sharp_zones, off)
        elif w == "bow":
            self._draw_bow(surf, f, sharp_zones, off, arrows)
        else:
            self.draw_sword(surf, f, sharp_zones, off)

    def _draw_flail(self, surf, f, sharp, off):
        from weapons import FLAIL_HANDLE_LEN, FLAIL_LINKS, FLAIL_BALL_R, SPIKE_SPEED
        def P(body, local):
            wpt = body.local_to_world(local)
            return (int(wpt.x + off[0]), int(C.HEIGHT - wpt.y + off[1]))
        hb = f.bodies["sword"]
        hcol = C.C_SHARP if "handle" in sharp else (96, 70, 46)
        pygame.draw.line(surf, hcol, P(hb, (0, -8)), P(hb, (0, FLAIL_HANDLE_LEN)), 6)
        ccol = C.C_SHARP if "chain" in sharp else (160, 164, 178)
        for i in range(FLAIL_LINKS):
            lb = f.bodies[f"flail_link{i}"]
            pygame.draw.line(surf, ccol, P(lb, (0, 0)), P(lb, (0, 9)), 3)
        bb = f.bodies["flail_ball"]
        bp = P(bb, (0, 0))
        fast = bb.velocity.length >= SPIKE_SPEED
        ball_sharp = ("spikes" in sharp and fast) or "ball" in sharp
        bcol = C.C_SHARP if ball_sharp else (120, 124, 140)
        pygame.draw.circle(surf, bcol, bp, int(FLAIL_BALL_R))
        # spikes drawn when the spikes zone exists; glow red only when fast
        if "spikes" in sharp:
            scol = C.C_SHARP if fast else (150, 150, 162)
            for k in range(8):
                a = k * math.tau / 8 + bb.angle
                tip = (bp[0] + math.cos(a) * (FLAIL_BALL_R + 5),
                       bp[1] - math.sin(a) * (FLAIL_BALL_R + 5))
                pygame.draw.line(surf, scol, bp, tip, 2)

    def _draw_bow(self, surf, f, sharp, off, arrows):
        from weapons import BOW_LEN, ARROW_LEN
        def P(body, local):
            wpt = body.local_to_world(local)
            return (int(wpt.x + off[0]), int(C.HEIGHT - wpt.y + off[1]))
        bb = f.bodies["sword"]
        scol = C.C_SHARP if "bow_limb" in sharp else (140, 96, 50)
        top, bot = P(bb, (0, BOW_LEN)), P(bb, (0, -BOW_LEN))
        mid = P(bb, (f.facing * 7, 0))
        pygame.draw.lines(surf, scol, False, [bot, mid, top], 4)
        pygame.draw.line(surf, (210, 212, 222), top, bot, 1)   # string
        if arrows:
            head_c = C.C_SHARP if "arrowhead" in sharp else (200, 204, 214)
            shaft_c = C.C_SHARP if "arrow_shaft" in sharp else (150, 120, 80)
            for ab, _, _ in arrows.arrows:
                a0 = ab.local_to_world((0, 0))
                a1 = ab.local_to_world((0, ARROW_LEN))
                ah = ab.local_to_world((0, ARROW_LEN * 0.7))
                pygame.draw.line(surf, shaft_c,
                                 (a0.x + off[0], C.HEIGHT - a0.y + off[1]),
                                 (ah.x + off[0], C.HEIGHT - ah.y + off[1]), 2)
                pygame.draw.line(surf, head_c,
                                 (ah.x + off[0], C.HEIGHT - ah.y + off[1]),
                                 (a1.x + off[0], C.HEIGHT - a1.y + off[1]), 3)

    def draw_sword(self, surf, f, sharp_zones, off):
        sw = f.bodies["sword"]

        def P(local):
            w = sw.local_to_world(local)
            return (int(w.x + off[0]), int(C.HEIGHT - w.y + off[1]))

        span = C.SWORD_TIP - C.SWORD_HANDLE
        tip_y = C.SWORD_HANDLE + C.SWORD_TIP_FRAC * span
        # blade body
        pygame.draw.line(surf, C.C_BLADE, P((0, 0)), P((0, C.SWORD_TIP)), 5)
        # zone highlights
        def zone_line(y0, y1, dx, w):
            pygame.draw.line(surf, C.C_SHARP, P((dx, y0)), P((dx, y1)), w)
        if "edge" in sharp_zones:
            zone_line(2, tip_y, f.facing * 2.4, 2)
        if "back_edge" in sharp_zones:
            zone_line(2, tip_y, -f.facing * 2.4, 2)
        if "tip" in sharp_zones:
            pygame.draw.line(surf, C.C_SHARP, P((0, tip_y)), P((0, C.SWORD_TIP)), 5)
        # guard + grip + pommel
        g1 = sw.local_to_world((-9, -2))
        g2 = sw.local_to_world((9, -2))
        pygame.draw.line(surf, C.C_GUARD,
                         (g1.x + off[0], C.HEIGHT - g1.y + off[1]),
                         (g2.x + off[0], C.HEIGHT - g2.y + off[1]), 4)
        pygame.draw.line(surf, (96, 70, 46), P((0, -3)), P((0, C.SWORD_HANDLE)), 6)
        pom_col = C.C_SHARP if "pommel" in sharp_zones else C.C_GUARD
        pygame.draw.circle(surf, pom_col, P((0, C.SWORD_POMMEL)), 5)

    # ---------------- fx ----------------
    def draw_fx(self, surf, fx, off):
        for s in fx.stains:
            pygame.draw.circle(surf, (110, 16, 24),
                               (int(s[0] + off[0]), int(C.HEIGHT - s[1] + off[1])), int(s[2]))
        for p in fx.blood:
            pygame.draw.circle(surf, C.C_BLOOD,
                               (int(p[0] + off[0]), int(C.HEIGHT - p[1] + off[1])), int(p[5]))
        for p in fx.sparks:
            pygame.draw.circle(surf, (255, 235, 160),
                               (int(p[0] + off[0]), int(C.HEIGHT - p[1] + off[1])), 2)
        for x, y, txt, color, life in fx.numbers:
            img = self.f_med.render(txt, True, color)
            img.set_alpha(int(255 * min(1, life)))
            surf.blit(img, (x + off[0] - img.get_width() // 2, C.HEIGHT - y + off[1]))

    # ---------------- HUD ----------------
    def draw_hud(self, surf, f1, f2, turn, max_turns, sharp_zones, phase_txt):
        def bar(x, f, align_r):
            wmax = 360
            pygame.draw.rect(surf, C.C_HP_BACK, (x, 38, wmax, 20), border_radius=6)
            w = int(wmax * f.hp / C.START_HP)
            if w > 0:
                rx = x + (wmax - w) if align_r else x
                hp_col = f.color if f.hp > 35 else (235, 80, 70)
                pygame.draw.rect(surf, hp_col, (rx, 38, w, 20), border_radius=6)
            pygame.draw.rect(surf, (20, 22, 30), (x, 38, wmax, 20), 2, border_radius=6)
            name = self.f_med.render(f.name, True, f.color)
            hp = self.f_sm.render(f"{f.hp:.0f}", True, C.C_TEXT)
            if align_r:
                surf.blit(name, (x + wmax - name.get_width(), 12))
                surf.blit(hp, (x - 30, 40))
            else:
                surf.blit(name, (x, 12))
                surf.blit(hp, (x + wmax + 8, 40))
        bar(40, f1, False)
        bar(C.WIDTH - 400, f2, True)
        t = self.f_big.render(f"{turn}", True, C.C_TEXT)
        surf.blit(t, (C.WIDTH // 2 - t.get_width() // 2, 14))
        sub = self.f_tiny.render(f"TURN / {max_turns}", True, C.C_DIM)
        surf.blit(sub, (C.WIDTH // 2 - sub.get_width() // 2, 58))
        sz = self.f_sm.render("SHARP: " + " + ".join(z.upper() for z in sharp_zones),
                              True, C.C_SHARP)
        surf.blit(sz, (C.WIDTH // 2 - sz.get_width() // 2, 76))
        if phase_txt:
            ph = self.f_sm.render(phase_txt, True, (255, 214, 120))
            surf.blit(ph, (C.WIDTH // 2 - ph.get_width() // 2, 98))

    def draw_thought(self, surf, f, text, side):
        if not text:
            return
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) < 40:
                cur += (" " if cur else "") + w
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        lines = lines[:4]
        w = max(self.f_tiny.size(l)[0] for l in lines) + 20
        h = 16 * len(lines) + 14
        x = 40 if side == 0 else C.WIDTH - 40 - w
        y = 124
        box = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(box, (12, 13, 20, 215), (0, 0, w, h), border_radius=8)
        pygame.draw.rect(box, (*f.color, 160), (0, 0, w, h), 2, border_radius=8)
        surf.blit(box, (x, y))
        for i, l in enumerate(lines):
            surf.blit(self.f_tiny.render(l, True, C.C_TEXT), (x + 10, y + 7 + i * 16))
