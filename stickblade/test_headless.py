"""Headless smoke test: run a full mock match without a window, save screenshots."""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import config as C
from main import Match
from render import Renderer, FX

pygame.init()
screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
rend = Renderer(screen)
fx = FX()
match = Match("berserker", "duelist", ["tip"], fx)

frames = 0
shots = {120: "shot_early.png", 600: "shot_mid.png", 1800: "shot_late.png"}
while match.phase != Match.PH_OVER and frames < 60 * 240:
    match.update(1 / 60, False)
    fx.update(1 / 60)
    frames += 1
    if frames in shots or (match.phase == Match.PH_OVER and "shot_end.png" not in shots.values()):
        screen.blit(rend.bg, (0, 0))
        rend.draw_fx(screen, fx, (0, 0))
        for f in (match.f1, match.f2):
            rend.draw_fighter(screen, f, (0, 0))
            rend.draw_weapon(screen, f, match.sharp, (0, 0), arrows=match.arrows[f.fid] if match.arrows else None)
        rend.draw_hud(screen, match.f1, match.f2, match.turn, C.MAX_TURNS,
                      match.sharp, match.phase)
        rend.draw_thought(screen, match.f1, match.thoughts[0], 0)
        rend.draw_thought(screen, match.f2, match.thoughts[1], 1)
        pygame.image.save(screen, shots.get(frames, "shot_end.png"))

# final screenshot
screen.blit(rend.bg, (0, 0))
rend.draw_fx(screen, fx, (0, 0))
for f in (match.f1, match.f2):
    rend.draw_fighter(screen, f, (0, 0))
    rend.draw_weapon(screen, f, match.sharp, (0, 0), arrows=match.arrows[f.fid] if match.arrows else None)
rend.draw_hud(screen, match.f1, match.f2, match.turn, C.MAX_TURNS, match.sharp, "")
pygame.image.save(screen, "shot_end.png")
print("RESULT:", match.winner, "| turns:", match.turn,
      "| hp:", round(match.f1.hp, 1), round(match.f2.hp, 1), "| frames:", frames)
