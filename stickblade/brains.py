"""LLM brains (GPT / Gemini) + scripted mock fighters.

Each brain receives a JSON game state and must return:
  {"thought": "...", "action": <ACTIONS>, "footwork": <FOOTWORK>}
"""
import json
import random
import re
import threading
import time as _time
from collections import deque
import config as C
from moves import ACTIONS, FOOTWORK, ACTION_ZONE


# Ring buffer of recent brain failures. Exposed via /api/debug/brain_errors
# so we can diagnose 'why is every match falling back?' without HF logs auth.
# Each entry: {"t": unix_ts, "label": brain.label, "model": model_id or "",
#              "attempt": idx+1, "of": total_attempts, "err": err_str[:200]}
_RECENT_ERRORS = deque(maxlen=80)


def _log_brain_err(label, model, attempt, total, err):
    _RECENT_ERRORS.append({
        "t": int(_time.time()),
        "label": label, "model": model or "",
        "attempt": attempt, "of": total,
        "err": str(err)[:200],
    })

SYSTEM_PROMPT = """You are a stickman fighter in a physics-based duel (like Toribash).
Your weapon: a {weapon}. Each turn you pick ONE action and ONE footwork; physics then runs for 3 seconds.

WEAPON RULES (critical): only these weapon zones are DANGEROUS and deal real damage: {sharp}.
All other zones are blunt (tiny chip damage at best).
Zone geometry: {zone_hint}
Zone each action leads with: {zone_map}
A fast DANGEROUS-zone hit to the head is an INSTANT KILL. Blunt hits mostly just push.

Actions: {actions}
Footwork: {footwork}
  lunge = explosive forward burst | hop_back = jump backward (escape pressure)

SPATIAL AWARENESS: each turn you receive world coordinates of both fighters'
torso and head (`me`, `enemy`) plus relative geometry under `relative`
(dx, dy, head_dx, head_dy, enemy_is left/right/in_front, enemy_height_relative
higher/lower/level, facing_enemy true/false). +x is right, +y is up.
If `relative.facing_enemy` is false you are looking the WRONG WAY — your
strike will whiff; use the next turn to reorient (your engine will auto-flip
if you simply walk past them).
For ranged shots, `ranged_hint.aim_at_enemy_head` is the world point to aim
at and `vertical_drop_to_compensate` tells you how much the arrow will fall.

Distance guide: <70 = clinch range, 70-150 = strike range, 150-260 = closing range, >260 = far.
{range_hint}
ARENA MODIFIER (state.arena): `normal` = standard stone floor; `ice` = ~3x
less foot friction AND much lower air drag — lunges overshoot, recoveries
keep sliding, and a missed swing can carry you past the enemy (prefer
`advance`/`hold` over `lunge`, and `hop_back` slides further than usual);
`low_gravity` = gravity is ~35% normal — jumps float, arrows drop less so
aim flatter, knockdowns take longer to recover from.
Reply with ONLY a JSON object, no markdown:
{{"thought": "<your tactical reasoning, max 30 words>", "action": "...", "footwork": "..."}}"""

RANGE_HINTS = {
    "sword": "",
    "flail": "Your flail outranges a clinch — mid range (90-170) is your kill zone; spin_up first for spike-speed.\n",
    "bow": "You are a RANGED fighter: keep distance >260 and shoot; if the enemy closes, hop_back or bow_bash.\n",
}


def _xy(v):
    """Round a pymunk Vec2d to ints for a compact JSON payload."""
    return [int(round(v.x)), int(round(v.y))]


def _vel(body):
    """Round a body velocity to int px/s."""
    v = body.velocity
    return [int(round(v.x)), int(round(v.y))]


def build_state(me, foe, turn, max_turns, last_events, arena="normal"):
    """Game state handed to the LLM each turn.

    Now includes full spatial awareness: torso + head positions (and velocities)
    for both fighters in world coordinates, weapon-tip / off-hand positions,
    relative geometry (Δx, Δy, who's above whom, who's facing the enemy), plus
    a few derived ranged-combat hints (line-of-sight clearance, vertical lead
    needed for an arrow shot, etc.). All values rounded to ints so the JSON
    payload stays small.
    """
    me_torso = me.pos()
    foe_torso = foe.pos()
    me_head = me.head_pos()
    foe_head = foe.head_pos()

    d = (foe_torso - me_torso).length
    dx = foe_torso.x - me_torso.x
    dy = foe_torso.y - me_torso.y

    head_dx = foe_head.x - me_head.x
    head_dy = foe_head.y - me_head.y
    head_dist = (foe_head - me_head).length

    # Are we actually pointing the right way? (facing is +1 right, -1 left)
    facing_enemy = (dx > 0 and me.facing > 0) or (dx < 0 and me.facing < 0)

    # Off-hand (the bow-string hand for bows; the second fist otherwise)
    off_hand = me.bodies["off_farm"].local_to_world((0, -12))

    # Weapon tip / business end
    weapon = getattr(me, "weapon", "sword")
    if weapon == "bow":
        # bow "tip" not meaningful — give the off-hand draw point instead
        weapon_tip = off_hand
    else:
        weapon_tip = me.tip_pos()

    # Velocities (helpful so the LLM can predict where to aim)
    me_vel = _vel(me.bodies["torso"])
    foe_vel = _vel(foe.bodies["torso"])

    # Ranged shot helper: how much arrow flight time at a typical 700 px/s
    # speed, and the vertical drop that should be compensated for.
    flight_t = round(d / 700.0, 2)
    gravity_drop = round(0.5 * abs(C.GRAVITY[1]) * flight_t * flight_t)

    rel = []
    for e in last_events:
        rel.append({"by": e["attacker"], "zone": e["zone"], "hit_part": e["part"],
                    "damage": e["damage"], "was_sharp": e["sharp"]})

    return {
        # core combat
        "turn": turn, "turns_left": max_turns - turn,
        "arena": arena,                       # normal | ice | low_gravity
        "my_hp": round(me.hp, 1), "enemy_hp": round(foe.hp, 1),
        "distance": round(d),
        "my_height": "knocked_down" if me_torso.y < me.stand_torso_y - 30 else "standing",
        "enemy_height": "knocked_down" if foe_torso.y < foe.stand_torso_y - 30 else "standing",
        "enemy_last_action": foe.last_action,
        "my_last_action": me.last_action,
        "enemy_sword_tip_distance_to_me": round((foe.tip_pos() - me_torso).length),
        "last_turn_hits": rel,

        # ---------- NEW: spatial awareness ----------
        # All positions are absolute world coordinates: +x = right, +y = up.
        "me": {
            "torso": _xy(me_torso),
            "head":  _xy(me_head),
            "weapon_tip": _xy(weapon_tip),
            "off_hand":   _xy(off_hand),
            "facing": me.facing,         # +1 right, -1 left
            "velocity": me_vel,           # px/s
        },
        "enemy": {
            "torso": _xy(foe_torso),
            "head":  _xy(foe_head),
            "facing": foe.facing,
            "velocity": foe_vel,
        },
        # Relative geometry (enemy minus me, signed in world coords).
        "relative": {
            "dx": int(round(dx)),
            "dy": int(round(dy)),
            "head_dx": int(round(head_dx)),
            "head_dy": int(round(head_dy)),
            "head_to_head_distance": int(round(head_dist)),
            # quick categorical hints so even tiny models can use this:
            "enemy_is": ("right" if dx > 8 else "left" if dx < -8 else "in_front"),
            "enemy_height_relative": (
                "higher" if dy > 18 else "lower" if dy < -18 else "level"),
            "facing_enemy": bool(facing_enemy),
        },
        # Ranged combat helpers (mostly useful for bow / flail leads).
        "ranged_hint": {
            "arrow_flight_time_s": flight_t,
            "vertical_drop_to_compensate": gravity_drop,
            # aim point if you want to hit the enemy HEAD with a flat arrow
            "aim_at_enemy_head": _xy(foe_head),
        },
    }


def _extract_json(text):
    # Defensive against None/empty (some providers return empty body on a
    # silent rate-limit; we want a clean ValueError that decide_with_timeout's
    # retry loop catches, not a TypeError from re.sub(None)).
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")
    text = re.sub(r"```(json)?", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json in response")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        # Most JSON parse failures are trailing commas / unescaped quotes
        # from small models. Try one cleanup pass before giving up so the
        # retry loop only sees genuinely-broken responses.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", m.group(0))   # trailing commas
        return json.loads(cleaned)


def _sanitize(d, allowed=None):
    allowed = allowed or ACTIONS
    a = d.get("action", "ready")
    f = d.get("footwork", "hold")
    if a not in allowed:
        a = "ready"
    if f not in FOOTWORK:
        f = "hold"
    t = str(d.get("thought", ""))[:160]
    return {"action": a, "footwork": f, "thought": t}


def _trim(text, max_words=25):
    """Clamp model output to <= max_words and strip stray punctuation."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip('"\'`')
    words = text.split(" ")
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return text[:280]


# ============================================================
# Resilience: buddy-model pools + adaptive timeouts
# ============================================================
# When the LLM originally chosen for a turn fails, decide_with_timeout()
# tries 1-2 BUDDY models from the same capability tier before giving up
# and using a scripted mock. Goal: keep the match feeling real even when
# the OpenRouter free pool has a hiccup or one provider is down.
#
# Buddies are SAME-TIER alternates. We don't downgrade a 405B model to a
# 3B model — that would tank match quality silently. Pools below are
# grouped by rough capability + speed so the swap is invisible to the user.
#
# Refresh against `https://openrouter.ai/api/v1/models` if the free pool
# rotates (see tools/verify_models.py).

_BUDDY_POOLS = {
    # Large / slow / strong. Order = preference: vanilla-first because they
    # emit shorter, faster, and are more likely to JSON cleanly on the first
    # try. Reasoning models (gpt-oss, nemotron-super) still work since we
    # now always send reasoning:{exclude:true}, but they're slightly more
    # latency-variable, so try them after.
    "large": [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "qwen/qwen3-coder:free",
        "openai/gpt-oss-120b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ],
    # Mid / balanced (fast enough for 15s budget).
    "mid": [
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "openai/gpt-oss-20b:free",
    ],
    # Small / fast (good for snap-shot scenarios where speed matters)
    "small": [
        "meta-llama/llama-3.2-3b-instruct:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "nvidia/nemotron-nano-9b-v2:free",
    ],
}

# Map each model to its tier so buddies come from the right pool.
_MODEL_TIER = {}
for tier, ids in _BUDDY_POOLS.items():
    for mid in ids:
        _MODEL_TIER[mid] = tier
# Paid models map to "mid" as a reasonable buddy tier (we don't burn paid
# budget on retries of free-tier failures; if a paid model fails we fall
# back to free mid-tier).
_MODEL_TIER.update({
    "openai/gpt-4o-mini":         "mid",
})


# ----------------------------------------------------------------------
# Per-model reasoning policy
# ----------------------------------------------------------------------
# Hand-curated from OpenRouter's GET /api/v1/models catalog (the 'reasoning'
# block on each model entry). Three categories:
#
#   None       → omit the `reasoning` param entirely. Either the model has
#                no reasoning capability at all, OR it's mandatory-reasoning
#                and rejects any attempt to disable (sending `enabled:false`
#                makes gpt-oss-* 400 the request).
#   {disable}  → safe to disable; we send `enabled: false, exclude: true`.
#                Non-reasoning models silently ignore, reasoning models that
#                allow disable actually turn off CoT.
#
# This map is verified against the live catalog on 2026-06-30. Any model id
# not listed defaults to "try to disable, fall back gracefully if rejected"
# — see _reasoning_policy().
#
# Rationale: previous attempts used substring matching on the model id
# ("gpt-oss", "nemotron", "thinking", etc.) which silently missed gemma-4,
# poolside-laguna, cohere-north and a bunch of others, AND mis-handled
# gpt-oss (mandatory-reasoning — disabling it errors). Catalog-driven is
# the only correct approach.
_REASONING_DISABLE = {"enabled": False, "exclude": True}

# Models where sending the reasoning param at all is wrong:
#   - mandatory-reasoning (will 400 if we ask to disable)
#   - vanilla non-reasoning (no-op, just cleaner to omit)
_REASONING_OMIT = {
    # vanilla non-reasoning (no reasoning block in catalog)
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "qwen/qwen3-coder:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "openai/gpt-4o-mini",
}

# Mandatory-reasoning models. These reject `enabled: false` (400) and will
# ALWAYS do hidden CoT no matter what we send. Best we can do is use the
# lowest supported effort and exclude reasoning from response. Listed
# separately so callers can also know to grant more max_tokens headroom.
_REASONING_MANDATORY = {
    "openai/gpt-oss-120b:free":  {"effort": "low", "exclude": True},
    "openai/gpt-oss-20b:free":   {"effort": "low", "exclude": True},
}


def _reasoning_policy(model_id: str):
    """Return the `reasoning` request block for a given model, or None
    if the param should be omitted entirely. Catalog-driven; see comment
    above for the curation rules.
    """
    if not model_id:
        return None
    if model_id in _REASONING_OMIT:
        return None
    if model_id in _REASONING_MANDATORY:
        return dict(_REASONING_MANDATORY[model_id])
    # Default: try to disable. Covers the catalog-listed reasoning models
    # that DO allow disable (gemma-4-*, nemotron-3-*, laguna-*, cohere-north,
    # nemotron-nano-*) plus any future model not yet in our curated set.
    return dict(_REASONING_DISABLE)


def _max_tokens_for(model_id: str, joint_mode: bool) -> int:
    """Adaptive output token cap. Mandatory-reasoning models need ~3x the
    headroom because they always do CoT; we can only ask for `effort: low`
    which still uses ~20%% of the cap on thinking."""
    base = 1200 if joint_mode else 800
    if model_id in _REASONING_MANDATORY:
        return base * 3  # 2400 macro / 3600 joint
    return base


def _buddies_for(brain, k=2):
    """Return up to k buddy model ids from the same tier as `brain.model`,
    excluding the original AND any model currently in 429 cooldown.
    Prefers buddies from a DIFFERENT provider host than the original, since
    the most common failure mode is 'upstream provider throttled' (free
    Llama-family models mostly go to Venice; if Venice is 429ing on one
    Llama, the other Llamas will be too — no point retrying them).
    Returns [] for non-OpenRouter brains.
    """
    model_id = getattr(brain, "model", None)
    if not model_id or "/" not in model_id:
        return []
    if not C.OPENROUTER_API_KEY:
        return []                           # no key, can't construct buddies
    tier = _MODEL_TIER.get(model_id, "mid") # unknown ids default to mid tier
    pool = [m for m in _BUDDY_POOLS.get(tier, []) if m != model_id]
    # Remove cooling-down models (429'd recently, upstream still throttled)
    now = _time.time()
    pool = [m for m in pool if _COOLDOWN.get(m, 0) < now]
    # Reorder: put buddies with a DIFFERENT provider host first. When the
    # original 429s it's almost always because that specific provider is
    # throttling globally, so a same-provider buddy will 429 too. Falling
    # back to a different provider is the only way to recover.
    origin_prov = _PROVIDER_HOST.get(model_id, "")
    if origin_prov:
        pool.sort(key=lambda m: _PROVIDER_HOST.get(m, "") == origin_prov)
    return pool[:k]


# ----------------------------------------------------------------------
# Per-model 429 circuit breaker
# ----------------------------------------------------------------------
# OpenRouter reports the upstream provider's Retry-After. If a model 429s,
# we blacklist it for `Retry-After` seconds (default 15s if header missing)
# so subsequent turns in the same match don't waste API calls / stall the
# retry ladder waiting for the throttle to clear on its own.
_COOLDOWN = {}  # {model_id: unix_ts_ready_at}
_COOLDOWN_LOCK = threading.Lock()


def _mark_cooldown(model_id, seconds):
    if not model_id:
        return
    with _COOLDOWN_LOCK:
        _COOLDOWN[model_id] = _time.time() + max(1.0, min(float(seconds), 60.0))


# ----------------------------------------------------------------------
# Provider host map (hand-curated from OpenRouter catalog, 2026-07-02).
# When a model 429s, we prefer buddies from a DIFFERENT provider — since
# the throttle almost always originates at the upstream host, not at OR.
# ----------------------------------------------------------------------
_PROVIDER_HOST = {
    # Venice hosts most Llama-family and Nous free models
    "meta-llama/llama-3.3-70b-instruct:free":       "venice",
    "meta-llama/llama-3.2-3b-instruct:free":        "venice",
    "nousresearch/hermes-3-llama-3.1-405b:free":    "venice",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "venice",
    # Google AI Studio hosts Gemma
    "google/gemma-4-31b-it:free":                   "google",
    "google/gemma-4-26b-a4b-it:free":               "google",
    # OpenInference hosts gpt-oss + some nvidia + qwen-coder
    "openai/gpt-oss-120b:free":                     "openinference",
    "openai/gpt-oss-20b:free":                      "openinference",
    "qwen/qwen3-coder:free":                        "openinference",
    "qwen/qwen3-next-80b-a3b-instruct:free":        "alibaba",
    # Nvidia self-hosts nemotron
    "nvidia/nemotron-3-super-120b-a12b:free":       "nvidia",
    "nvidia/nemotron-3-ultra-550b-a55b:free":       "nvidia",
    "nvidia/nemotron-3-nano-30b-a3b:free":          "nvidia",
    "nvidia/nemotron-nano-9b-v2:free":              "nvidia",
    # Others
    "poolside/laguna-m.1:free":                     "poolside",
    "poolside/laguna-xs.2:free":                    "poolside",
    "cohere/north-mini-code:free":                  "cohere",
    "liquid/lfm-2.5-1.2b-instruct:free":            "liquid",
    # Paid (OR routes to Azure/Anthropic/etc; unlikely to be free-tier-throttled)
    "openai/gpt-4o-mini":                           "azure",
}


def _timeout_for(model_id):
    """Adaptive per-model timeout. Tiny models that take >10s are stuck
    (their inference is fast), while reasoning models genuinely need 25-30s
    on a complex prompt. Flat 30s was killing reasoning chains too early
    AND waiting too long on tiny stuck models."""
    if not model_id:
        return C.LLM_TIMEOUT
    mid = model_id.lower()
    # Small fast models
    if any(t in mid for t in ("3b", "1.2b", "9b", "nano", "lfm", "small")):
        return 10.0
    # Large reasoning models
    if any(t in mid for t in ("120b", "405b", "550b", "deepseek-r1", "thinking", "reasoning")):
        return min(C.LLM_TIMEOUT, 25.0)
    # Default mid-tier
    return min(C.LLM_TIMEOUT, 18.0)


class Brain:
    label = "BASE"

    def __init__(self, sharp_zones, mode="macro", weapon="sword"):
        from weapons import (WEAPON_ACTIONS, WEAPON_ACTION_ZONE, WEAPON_HINTS)
        self.sharp = sharp_zones
        self.mode = mode
        self.weapon = weapon
        self.actions = WEAPON_ACTIONS.get(weapon, ACTIONS)
        if mode == "joint":
            from joint_mode import build_joint_system_prompt
            self.sys = build_joint_system_prompt(sharp_zones, weapon)
        else:
            zmap = " | ".join(f"{a}->{z}" for a, z in
                              WEAPON_ACTION_ZONE.get(weapon, {}).items())
            self.sys = SYSTEM_PROMPT.format(
                weapon=weapon,
                sharp=", ".join(sharp_zones).upper(),
                zone_hint=WEAPON_HINTS.get(weapon, ""),
                zone_map=zmap,
                actions=", ".join(self.actions), footwork=", ".join(FOOTWORK),
                range_hint=RANGE_HINTS.get(weapon, ""))
        self.history = []

    def _clean(self, raw):
        """Mode-aware sanitization of a parsed LLM reply."""
        if self.mode == "joint":
            from joint_mode import sanitize_joint_reply
            return sanitize_joint_reply(raw)
        return _sanitize(raw, self.actions)

    def decide(self, state):
        """Blocking; called from worker thread. Returns sanitized dict."""
        raise NotImplementedError

    # ---------- free-form chat (trash talk / commentary) -----------------
    def chat(self, system, user, max_tokens=80, temperature=0.95):
        """Stateless one-shot completion. Override in concrete brains.
        Default: a small library of canned trash talk so the mocks aren't
        dead silent. Returns a plain string."""
        return ""

    def chat_with_timeout(self, system, user, max_tokens=80,
                          temperature=0.95, fallback=""):
        out = {}
        def run():
            try:
                out["r"] = self.chat(system, user, max_tokens=max_tokens,
                                     temperature=temperature)
            except Exception as e:
                out["err"] = str(e)[:80]
        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(min(C.LLM_TIMEOUT, 15))   # quips shouldn't block long
        return _trim(out.get("r") or fallback)

    def decide_with_timeout(self, state):
        """Resilient decide() with retry, buddy-model fallback, and adaptive
        timeout — only resorts to the scripted mock as a true last resort.

        Failure ladder (each step takes <2s extra wall clock):
          1. Original model, 1st attempt, adaptive timeout for its size
          2. Original model, 2nd attempt with +50% timeout (handles transient
             rate-limits, empty responses, JSON parse errors, network blips)
          3. Buddy model #1 (similar capability tier, different provider)
          4. Buddy model #2 (further-removed alternate)
          5. Scripted mock (last resort, banner shown to user)
        """
        import time as _t

        # Step 1+2: retry the originally-chosen model first — UNLESS it's
        # in the 429 cooldown map from a recent throttle. If so, skip
        # straight to buddies (no point burning a 15s wait for a model
        # we know is currently blocked upstream).
        own_model = getattr(self, "model", "")
        in_cooldown = _COOLDOWN.get(own_model, 0) > _t.time()
        attempts = []
        if not in_cooldown:
            attempts = [
                (self, _timeout_for(own_model)),
                (self, _timeout_for(own_model) * 1.5),
            ]

        # Steps 3+4: try up to 2 buddy models if the original keeps failing.
        # Buddies only apply to OpenRouter brains (same client, same key, just
        # a different model id). GPT/Gemini brains use different clients and
        # don't have an equivalent — they get the same model retried twice.
        # _buddies_for() already filters out cooling-down buddies and orders
        # by provider diversity (different upstream host first).
        for buddy_id in _buddies_for(self, k=3 if in_cooldown else 2):
            try:
                buddy = OpenRouterBrain(self.sharp, buddy_id,
                                        label=self.label + "→buddy",
                                        mode=self.mode, weapon=self.weapon)
                attempts.append((buddy, _timeout_for(buddy_id)))
            except Exception:
                # OpenRouter not configured / brain init failed — skip silently
                pass

        # If EVERYTHING is cooling down (rare — every buddy 429'd recently)
        # give the original ONE shot with big timeout; it might be back.
        if not attempts:
            attempts = [(self, _timeout_for(own_model) * 1.5)]

        last_err = "no attempts"
        for idx, (brain, timeout_s) in enumerate(attempts):
            out = {}
            def _run():
                try:
                    out["r"] = brain.decide(state)
                except Exception as e:
                    out["err"] = str(e)[:200]
            th = threading.Thread(target=_run, daemon=True)
            th.start()
            th.join(timeout_s)

            if "r" in out and out["r"]:
                if idx > 0:
                    print(f"[brain] {self.label} recovered on attempt {idx+1} "
                          f"using {getattr(brain,'model',brain.label)}")
                return out["r"]

            last_err = out.get("err") or f"timeout({timeout_s:.0f}s)"
            print(f"[brain] {self.label} attempt {idx+1}/{len(attempts)} "
                  f"failed: {last_err[:120]}")
            _log_brain_err(self.label,
                           getattr(brain, "model", ""),
                           idx + 1, len(attempts), last_err)

            # FAST-FAIL on reasoning_burnout: the model just spent its entire
            # token budget on hidden CoT. Retrying with +50% budget might
            # work but usually doesn't — and a buddy from a different family
            # almost always does. Skip the redundant 2nd attempt on the same
            # model and jump to the first buddy (idx 2) immediately.
            if idx == 0 and "reasoning_burnout" in last_err and len(attempts) > 2:
                # Drop attempt #2 (same-model retry); buddies stay queued.
                attempts.pop(1)

            # Tiny backoff between attempts so we don't immediately re-hit a
            # rate-limit window. Capped at 2s so total recovery stays under
            # ~10s extra wall clock in the worst case.
            if idx < len(attempts) - 1:
                _t.sleep(min(0.5 * (idx + 1), 2.0))

        # ---------------- All attempts exhausted → scripted fallback --------
        # Pick a personality based on the brain's label so when BOTH fighters
        # fall back in the same match they don't produce identical sequences.
        personality = "berserker" if (hash(self.label) & 1) else "duelist"
        if self.mode == "joint":
            from joint_mode import MockJointBrain
            fb = MockJointBrain(self.sharp, weapon=self.weapon).decide(state)
        else:
            # CRITICAL: pass weapon=self.weapon so the mock fallback picks
            # weapon-appropriate actions. Without this it defaults to 'sword'
            # and a bow fighter ends up swinging the bow like a sword instead
            # of shooting arrows (and a flail fighter ignores spin_up etc.).
            fb = MockBrain(self.sharp, personality,
                           weapon=self.weapon).decide(state)

        print(f"[brain] {self.label} ALL {len(attempts)} attempts failed, "
              f"using mock {personality}: {last_err[:80]}")
        fb["thought"] = "[fallback] " + fb["thought"]
        fb["_fallback"] = True
        return fb


# ---------------------------------------------------------------- mock AI
PERSONALITIES = {
    "duelist":  "patient counter-fighter",
    "berserker": "relentless aggression",
}


_MOCK_QUIPS = {
    "berserker": [
        "I don't fence. I delete.",
        "Hope your save file is recent.",
        "Stand still. It'll hurt less.",
        "Three swings. None of them yours.",
    ],
    "duelist": [
        "Patience always wins. I've already won.",
        "I read your intent two turns ago.",
        "Come closer. I dare you.",
        "Your zone is bad and you should feel bad.",
    ],
}


class MockBrain(Brain):
    def __init__(self, sharp_zones, personality="duelist", label=None,
                 weapon="sword"):
        super().__init__(sharp_zones, "macro", weapon)
        self.p = personality
        self.label = label or f"Mock-{personality}"

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        # Mocks don't actually call any model — pick a personality-appropriate
        # canned line. Works for both pre-fight quips and the commentary
        # roast (commentator role plays a generic "duelist" pool).
        pool = _MOCK_QUIPS.get(self.p, _MOCK_QUIPS["duelist"])
        return random.choice(pool)

    def _sharp_attacks(self):
        atk = [a for a in self.actions
               if ACTION_ZONE.get(a) and ACTION_ZONE[a] in self.sharp]
        fallback = {"sword": ["thrust"], "flail": ["wide_swing"],
                    "bow": ["draw_shot"]}
        return atk or fallback.get(self.weapon, ["thrust"])

    def decide(self, state):
        d = state["distance"]
        hits_on_me = [h for h in state["last_turn_hits"] if h["by"] != self.label]
        atk = self._sharp_attacks()
        if state["my_height"] == "knocked_down":
            return _sanitize({"action": "guard_high", "footwork": "hop_back",
                              "thought": "I'm down — cover up and create space."})
        if self.weapon == "bow":
            # Always prefer SHOOTING over melee with a bow. The previous logic
            # had bow_bash as a 50% pick at clinch range which looked weird —
            # archers don't beat people with their bow when an arrow at 0 ft
            # still works. Only bash if literally on top of the enemy.
            if d > 280:
                mv = {"action": random.choice(["draw_shot", "high_arc_shot"]),
                      "footwork": "hold",
                      "thought": "Long range — full draw, loose."}
            elif d > 120:
                mv = {"action": "quick_shot", "footwork": "retreat",
                      "thought": "He's closing — snap shot and give ground."}
            elif d > 50:
                # close but not clinched — still shoot, just hop back first
                mv = {"action": "quick_shot", "footwork": "hop_back",
                      "thought": "Point-blank shot, then create distance."}
            else:
                # in actual physical contact — only NOW use the bow as a club
                mv = {"action": "bow_bash", "footwork": "hop_back",
                      "thought": "He's on top of me — bash and jump away."}
            return _sanitize(mv, self.actions)
        if self.p == "berserker":
            if d > 200:
                mv = {"action": random.choice(atk), "footwork": "lunge",
                      "thought": "Close the gap hard, swing on arrival."}
            elif d > 90:
                mv = {"action": random.choice(atk), "footwork": "advance",
                      "thought": "In range next step — commit to the kill zone."}
            else:
                mv = {"action": random.choice(atk + atk + ["pommel_strike"]),
                      "footwork": "advance", "thought": "Point blank. Overwhelm."}
        else:
            if hits_on_me and state["my_hp"] < 50:
                mv = {"action": "guard_high", "footwork": "hop_back",
                      "thought": "Taking damage — reset distance, defend high line."}
            elif d > 240:
                # Bow is handled by the early-return above; only melee reaches
                # this branch, so no need to special-case it here.
                mv = {"action": "ready", "footwork": "advance",
                      "thought": "Walk in behind guard, no wasted swings."}
            elif d > 130:
                mv = {"action": random.choice(atk), "footwork": "lunge",
                      "thought": "Perfect entry distance — explosive sharp attack."}
            elif d < 70:
                mv = {"action": random.choice(atk), "footwork": "hop_back",
                      "thought": "Too close, cut on the way out."}
            else:
                mv = {"action": random.choice(atk), "footwork": random.choice(["hold", "advance"]),
                      "thought": "Strike range. Aim the sharp zone at his head."}
        # Pass self.actions so weapon-specific moves (wide_swing / spin_up
        # for flail, thrust_over for spear, etc.) survive sanitization. The
        # default ACTIONS list is sword-only; without this a flail mock's
        # 'wide_swing' silently downgraded to 'ready' and the fighter just
        # stood there whenever the API fell back to the mock brain.
        return _sanitize(mv, self.actions)


# ---------------------------------------------------------------- real LLMs
class GPTBrain(Brain):
    label = "GPT"

    def __init__(self, sharp_zones, model=C.OPENAI_MODEL, mode="macro", weapon="sword"):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        from openai import OpenAI
        self.client = OpenAI(api_key=C.OPENAI_API_KEY)

    def decide(self, state):
        msgs = [{"role": "system", "content": self.sys}]
        msgs += self.history[-6:]
        user = json.dumps(state)
        msgs.append({"role": "user", "content": user})
        r = self.client.chat.completions.create(
            model=self.model, messages=msgs, temperature=0.8, max_tokens=150,
            response_format={"type": "json_object"})
        txt = r.choices[0].message.content
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            temperature=temperature, max_tokens=max_tokens)
        return r.choices[0].message.content or ""


class GeminiBrain(Brain):
    label = "GEMINI"

    def __init__(self, sharp_zones, model=C.GEMINI_MODEL, mode="macro", weapon="sword"):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        from google import genai
        self.client = genai.Client(api_key=C.GEMINI_API_KEY)
        self.convo = []

    def decide(self, state):
        from google.genai import types
        self.convo.append({"role": "user", "parts": [{"text": json.dumps(state)}]})
        r = self.client.models.generate_content(
            model=self.model,
            contents=self.convo[-7:],
            config=types.GenerateContentConfig(
                system_instruction=self.sys, temperature=0.8,
                max_output_tokens=450 if self.mode == 'joint' else 200, response_mime_type="application/json"))
        txt = r.text
        self.convo.append({"role": "model", "parts": [{"text": txt}]})
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        from google.genai import types
        r = self.client.models.generate_content(
            model=self.model,
            contents=[{"role": "user", "parts": [{"text": user}]}],
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens))
        return r.text or ""


class OpenRouterBrain(Brain):
    """Any model on OpenRouter via the OpenAI-compatible chat endpoint.

    model: e.g. 'meta-llama/llama-3.3-70b-instruct:free' or 'openai/gpt-4o-mini'
    """

    def __init__(self, sharp_zones, model, label=None, mode="macro", weapon="sword"):
        super().__init__(sharp_zones, mode, weapon)
        self.model = model
        self.label = label or model.split("/")[-1].replace(":free", "")[:24]
        import httpx
        self._client = httpx.Client(
            base_url=C.OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {C.OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://stickblade.arena",
                "X-Title": "Stickblade Arena",
            },
            timeout=C.LLM_TIMEOUT,
        )

    def decide(self, state):
        user = json.dumps(state)
        msgs = [{"role": "system", "content": self.sys}]
        msgs += self.history[-6:]
        msgs.append({"role": "user", "content": user})
        payload = {
            "model": self.model, "messages": msgs,
            "temperature": 0.8,
            "max_tokens": _max_tokens_for(self.model, self.mode == "joint"),
        }
        # Per-model reasoning policy (see _reasoning_policy / catalog notes
        # above). Only attach the `reasoning` block when the policy returns
        # one — sending `enabled: false` to a mandatory-reasoning model
        # (gpt-oss-*) makes it 400 the request; sending it to a
        # no-reasoning model is a silent no-op but cleaner to just omit.
        rp = _reasoning_policy(self.model)
        if rp:
            payload["reasoning"] = rp
        r = self._client.post("/chat/completions", json=payload)
        # Surface OpenRouter's actual error text instead of httpx's generic
        # 'Client error N for url ...'. OR returns {"error": {"message":...}}
        # on 4xx/5xx; we want that message bubbling into [brain] log lines
        # so we know *why* a retry/buddy is firing.
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                # OR nests upstream Retry-After under error.metadata
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            # 429 = throttled. Mark this model in cooldown so subsequent
            # turns in this or any other match don't waste API calls on
            # a model we KNOW is throttled. Retry-After is usually 5-30s.
            if r.status_code == 429:
                _mark_cooldown(self.model,
                               retry_after or 15)  # default 15s if header absent
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        txt = msg.get("content")
        finish = choice.get("finish_reason", "")
        # Reasoning-burnout signature: content is null/empty AND finish_reason
        # is 'length' (model hit the cap mid-think). Raise a distinct error
        # so decide_with_timeout's retry ladder skips to a buddy fast instead
        # of pointlessly re-querying the same model.
        if (not txt) and finish == "length":
            raise ValueError(f"reasoning_burnout: {self.model} spent entire "
                             f"budget on hidden CoT (finish=length, content=null)")
        if not txt:
            raise ValueError(f"empty response (finish={finish or 'unknown'})")
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        # Same per-model reasoning policy as decide(). Floor max_tokens at
        # 400 so any model that still does CoT (mandatory-reasoning) has
        # room for it + the short trash-talk line.
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": user}],
            "temperature": temperature,
            "max_tokens": max(max_tokens, 400),
        }
        rp = _reasoning_policy(self.model)
        if rp:
            payload["reasoning"] = rp
        r = self._client.post("/chat/completions", json=payload)
        if r.status_code >= 400:
            err = ""
            retry_after = 0
            try:
                j = r.json()
                err_obj = j.get("error") or {}
                err = err_obj.get("message", "")[:200]
                meta = err_obj.get("metadata") or {}
                retry_after = meta.get("retry_after_seconds") or 0
            except Exception:
                err = r.text[:200] if r.text else ""
            if r.status_code == 429:
                _mark_cooldown(self.model, retry_after or 15)
            raise ValueError(f"http_{r.status_code}: {err or r.reason_phrase}")
        return r.json()["choices"][0]["message"]["content"] or ""


# ============================================================
# Trash talk + post-fight commentary
# ============================================================
QUIP_SYS = (
    "You are a stickman sword/flail/bow fighter about to enter a physics-based "
    "duel against another AI model. Reply with ONE line of in-character "
    "trash talk, maximum 18 words. No emojis. No quotation marks. No 'As an AI'. "
    "Be cocky, witty, specific to the matchup."
)


def pre_fight_quip(brain, opponent_label, weapon="sword"):
    """Ask the brain for a single trash-talk line. Falls back to a canned
    quip if the model is slow or errors out."""
    user = (f"You are fighting a model called '{opponent_label}'. "
            f"Your weapon: {weapon}. Give your one line of pre-fight trash "
            "talk. Just the line, nothing else.")
    fallback = random.choice(_MOCK_QUIPS["berserker"] + _MOCK_QUIPS["duelist"])
    return brain.chat_with_timeout(QUIP_SYS, user, max_tokens=60,
                                   temperature=1.0, fallback=fallback)


COMMENTATOR_SYS = (
    "You are a snarky e-sports commentator for an AI sword-fighting arena. "
    "Given the result of a duel between two LLMs, write a SHORT post-fight "
    "summary (2 sentences, max 45 words total). Sentence 1: what happened. "
    "Sentence 2: a playful roast of the LOSER. Stay in character, do not "
    "mention being an AI. No emojis. No quotation marks."
)


def commentator_roast(commentator_brain, winner_name, loser_name, method,
                      turns, weapon, sharp, final_hp,
                      fallback="A clean kill. Better luck next patch."):
    """Ask a third brain to write 2-sentence post-fight commentary."""
    user = (
        f"Weapon: {weapon}. Sharp zones: {', '.join(sharp)}.\n"
        f"Winner: {winner_name}. Loser: {loser_name}.\n"
        f"Method: {method}. Turns: {turns}.\n"
        f"Final HP — winner: {final_hp.get(winner_name, '?')}, "
        f"loser: {final_hp.get(loser_name, '?')}.\n"
        "Write your 2-sentence summary + roast now."
    )
    return commentator_brain.chat_with_timeout(
        COMMENTATOR_SYS, user, max_tokens=120, temperature=1.0,
        fallback=fallback)


def make_brain(kind, sharp_zones, mode="macro", weapon="sword"):
    kind = kind.lower()

    def _mock(personality="duelist", label=None):
        if mode == "joint":
            from joint_mode import MockJointBrain
            return MockJointBrain(sharp_zones, label=label, weapon=weapon)
        return MockBrain(sharp_zones, personality, label=label, weapon=weapon)

    # explicit mock personality: "mock:duelist" / "mock:berserker"
    if kind.startswith("mock:"):
        p = kind.split(":", 1)[1]
        return _mock(p if p in PERSONALITIES else "duelist")
    # OpenRouter model id (contains "/"), e.g. meta-llama/llama-3.3-70b:free
    if "/" in kind:
        if C.OPENROUTER_API_KEY:
            try:
                return OpenRouterBrain(sharp_zones, kind, mode=mode, weapon=weapon)
            except Exception as e:
                print(f"[brains] OpenRouter init failed ({e}); using mock.")
        else:
            print(f"[brains] No OPENROUTER_API_KEY — '{kind}' slot uses mock.")
        label = kind.split("/")[-1].replace(":free", "")[:20] + "(mock)"
        return _mock("duelist", label=label)
    if kind == "gpt":
        if C.OPENAI_API_KEY:
            try:
                return GPTBrain(sharp_zones, mode=mode, weapon=weapon)
            except Exception as e:
                print(f"[brains] GPT init failed ({e}); using mock.")
        else:
            print("[brains] No OPENAI_API_KEY — GPT slot uses mock.")
        return _mock("duelist", label="GPT(mock)")
    if kind == "gemini":
        if C.GEMINI_API_KEY:
            try:
                return GeminiBrain(sharp_zones, mode=mode, weapon=weapon)
            except Exception as e:
                print(f"[brains] Gemini init failed ({e}); using mock.")
        else:
            print("[brains] No GEMINI_API_KEY — Gemini slot uses mock.")
        return _mock("berserker", label="GEMINI(mock)")
    return _mock(kind if kind in PERSONALITIES else "duelist")
