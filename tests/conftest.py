"""Shared test bootstrap.

The engine lives in `stickblade/` as flat modules that import each other by
bare name, so every test needs that directory on sys.path and a headless
SDL driver before it imports pygame.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "stickblade"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
# Test-friendly rate limits: the production defaults (10 queued matches,
# 50 matches/hour/IP) exist to cap LLM spend, and the end-to-end tests
# deliberately fire dozens of offline mock matches through the real API.
os.environ.setdefault("MAX_QUEUE", "200")
os.environ.setdefault("RL_MATCHES_PER_HOUR", "10000")
os.environ.setdefault("RL_VOTES_PER_HOUR", "10000")
os.environ.setdefault("RL_REQS_PER_MIN", "100000")
os.environ.setdefault("MAX_MATCHES_PER_DAY", "100000")
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))


def init_pygame():
    """Idempotent headless pygame init (needed before any Match runs)."""
    import pygame
    if not pygame.get_init():
        pygame.init()
    try:
        pygame.display.set_mode((10, 10))
    except Exception:
        pass
    return pygame
