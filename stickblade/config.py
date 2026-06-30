"""Global configuration for STICKBLADE ARENA."""
import os

# ---------------- Window ----------------
WIDTH, HEIGHT = 1280, 720
FPS = 60
FLOOR_Y = 64            # pymunk y of floor surface (y-up world)

# ---------------- Physics ----------------
GRAVITY = (0, -1150.0)
DT = 1.0 / 120.0        # physics substep
SUBSTEPS = 2            # substeps per rendered frame
SPACE_DAMPING = 0.99

# ---------------- Match rules ----------------
TURN_SECONDS = 3.0      # physics burst per turn ("long" pacing)
MAX_TURNS = 24
START_HP = 100.0
LLM_TIMEOUT = 30.0      # seconds before falling back to scripted move

# Damage model
SHARP_SPEED_MIN = 150.0     # below this, even a sharp zone only scratches
KILL_HEAD_SPEED = 660.0     # sharp hit to head at/above this speed = instant kill
DMG_SCALE = 0.055
DMG_CAP = 38.0
BLUNT_SPEED_MIN = 260.0
BLUNT_CAP = 6.0
HIT_COOLDOWN = 0.35         # s between damage ticks for same sword->part pair
SWING_COOLDOWN = 0.55       # s between ANY two damage events by one attacker

PART_MULT = {"head": 1.9, "torso": 1.25, "arm": 0.7, "leg": 0.8}

# ---------------- Sword geometry (local coords, +Y = blade direction) ----
SWORD_POMMEL = -34.0
SWORD_HANDLE = -26.0    # grip anchor
SWORD_TIP = 52.0
SWORD_TIP_FRAC = 0.72   # local-y above handle+frac*length counts as tip
SWORD_R = 2.6

ALL_ZONES = ["tip", "edge", "back_edge", "pommel"]

# ---------------- LLM API ----------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_MODEL = os.environ.get("STICKBLADE_OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.environ.get("STICKBLADE_GEMINI_MODEL", "gemini-2.0-flash")

# OpenRouter: one key -> 100+ models (https://openrouter.ai/keys)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# Models offered in the web arena (id -> display name).
# ":free" variants cost $0 (list verified live against the OpenRouter catalog
# 2026-06; the free pool rotates, so refresh occasionally).
ARENA_MODELS = {
    # ---- free ($0 with any OpenRouter key) — verified live 2026-06-22 ----
    # Cross-checked against https://openrouter.ai/api/v1/models — every id below
    # was on the live free roster the day this was committed. If a fight 404s,
    # the free pool has rotated; refresh by running tools/verify_models.py.
    "meta-llama/llama-3.3-70b-instruct:free":     "Llama 3.3 70B (free)",
    "meta-llama/llama-3.2-3b-instruct:free":      "Llama 3.2 3B (free)",
    "qwen/qwen3-next-80b-a3b-instruct:free":      "Qwen3 Next 80B (free)",
    "qwen/qwen3-coder:free":                      "Qwen3 Coder 480B (free)",
    "openai/gpt-oss-120b:free":                   "GPT-OSS 120B (free)",
    "openai/gpt-oss-20b:free":                    "GPT-OSS 20B (free)",
    "google/gemma-4-31b-it:free":                 "Gemma 4 31B (free)",
    "google/gemma-4-26b-a4b-it:free":             "Gemma 4 26B A4B (free)",
    "nousresearch/hermes-3-llama-3.1-405b:free":  "Hermes 3 405B (free)",
    "nvidia/nemotron-3-super-120b-a12b:free":     "Nemotron 3 Super 120B (free)",
    "nvidia/nemotron-3-ultra-550b-a55b:free":     "Nemotron 3 Ultra 550B (free)",
    "nvidia/nemotron-3-nano-30b-a3b:free":        "Nemotron 3 Nano 30B (free)",
    "nvidia/nemotron-nano-9b-v2:free":            "Nemotron Nano 9B (free)",
    # nex-agi/nex-n2-pro:free — pulled by OpenRouter (404 as of 2026-06-30)
    "poolside/laguna-m.1:free":                   "Poolside Laguna M.1 (free)",
    "poolside/laguna-xs.2:free":                  "Poolside Laguna XS.2 (free)",
    "cohere/north-mini-code:free":                "Cohere North Mini Code (free)",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "Dolphin Venice 24B (free)",
    "liquid/lfm-2.5-1.2b-instruct:free":          "LiquidAI LFM2.5 1.2B (free)",
    # ---- paid (cheap, billed via OpenRouter credits) ----
    "openai/gpt-4o-mini":                         "GPT-4o mini",
    # anthropic/claude-3.5-haiku — pulled by OpenRouter (404 as of 2026-06-30)
    # ---- no API needed ----
    "mock:duelist":                               "Mock Duelist (no API)",
    "mock:berserker":                             "Mock Berserker (no API)",
}

# ---------------- Colors (Toribash-ish dark arena) ----------------
C_BG_TOP = (16, 18, 26)
C_BG_BOT = (38, 42, 58)
C_FLOOR = (52, 56, 74)
C_FLOOR_LINE = (74, 80, 104)
C_P1 = (86, 220, 130)      # green  (GPT side default)
C_P2 = (90, 160, 255)      # blue   (Gemini side default)
C_P1_DARK = (40, 120, 66)
C_P2_DARK = (42, 80, 140)
C_BLADE = (214, 218, 230)
C_SHARP = (255, 70, 70)
C_GUARD = (212, 175, 96)
C_BLOOD = (190, 24, 36)
C_TEXT = (232, 234, 244)
C_DIM = (150, 154, 172)
C_HP_BACK = (60, 24, 28)
