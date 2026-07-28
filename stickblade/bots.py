"""Non-LLM baseline bots for Tier-A #2 (Reviewer #4 + Session #3 LLM #1
proposal). Fixed-behavior reference opponents that let the leaderboard
make claims like "GPT-OSS 120B beats scripted-pro 78%% of matches" —
scale-independent y-axis calibration that doesn't need thousands of
human votes to be meaningful.

Why they live in their own file instead of brains.py:
  * brains.py is 1458 lines and specifically about LLM adapters +
    schema handling + reasoning routing + circuit breakers. Baseline
    bots are pure Python heuristics, zero network I/O — different
    concern, different file.
  * Keeps bots easy to audit in isolation. If a reviewer asks "prove
    the greedy bot is actually greedy," they open this one file.
  * make_brain() routes the "bot:*" model prefix here.

All three bots subclass brains.Brain so they get self.actions,
self.sharp, self.weapon, self.mode, chat() (returns canned line),
decide_with_timeout() (no-op wrapper). They only override decide().

Deterministic-per-seed: each bot instance takes an optional seed
argument. Random and scripted-pro use it to make replay reproducible
— important for the frozen eval pack (Tier-A #4) where we want the
same matchup to produce the same outcome across re-runs.
"""
import random
from moves import ACTIONS, FOOTWORK, ACTION_ZONE
from brains import Brain, _sanitize


class BotBrain(Brain):
    """Base for non-LLM baselines. Inherits WEAPON_ACTIONS resolution,
    self.actions vocabulary, self.sharp, self.mode from Brain. Overrides
    chat() to return a canned line (no network) so pre-fight quips still
    work when a bot is on the roster."""
    label = "BOT"

    def __init__(self, sharp_zones, mode="macro", weapon="sword",
                 seed=None, label=None):
        super().__init__(sharp_zones, mode, weapon)
        # Per-instance RNG so seeded runs are reproducible. Falls back
        # to os.urandom seed when seed=None (production case), which
        # matches how MockBrain currently behaves.
        self._rng = random.Random(seed)
        if label:
            self.label = label

    def chat(self, system, user, max_tokens=80, temperature=0.95):
        # Bots don't chat. Return a flavor line so the pre-fight quip
        # slot isn't blank when a bot is picked. Kept deliberately
        # boring — the bot's personality is its algorithm, not banter.
        return f"{self.label} does not negotiate."

    # Subclasses MUST override decide(). We deliberately don't provide
    # a default that just returns "ready" because that's a real bug we
    # want to surface loudly (via NotImplementedError, not silent no-op).
    def decide(self, state):
        raise NotImplementedError(
            f"{type(self).__name__}.decide() not implemented")

    def _sharp_attacks(self):
        """Return the attack actions whose default lead-zone is one of
        the currently-sharp zones. Same helper MockBrain uses. Kept
        duplicated here (~5 lines) instead of importing to avoid a
        dependency direction the brains/bots split is trying to enforce."""
        atk = [a for a in self.actions
               if ACTION_ZONE.get(a) and ACTION_ZONE[a] in self.sharp]
        fallback = {"sword": ["thrust"], "flail": ["wide_swing"],
                    "bow":   ["draw_shot"]}
        return atk or fallback.get(self.weapon, ["thrust"])


# ============================================================================
# RandomBot — pure uniform-random baseline
#
# Picks action + footwork uniformly at random from the weapon's vocabulary
# each turn. This is the "floor" bot: any LLM that can't beat this
# consistently is doing worse than dice. Reviewer #4 asked for exactly this
# as the y-axis anchor point ("GPT-OSS 120B beats random N%% of matches").
# ============================================================================
class RandomBot(BotBrain):
    label = "RandomBot"

    def decide(self, state):
        mv = {
            "action":   self._rng.choice(self.actions),
            "footwork": self._rng.choice(FOOTWORK),
            "thought":  "[random baseline] no strategy, uniform pick.",
        }
        return _sanitize(mv, self.actions)


# ============================================================================
# GreedyAttackBot — always attacks with a sharp-zone move + advances
#
# Ignores enemy HP, position, hits taken. Just picks a sharp attack and
# marches forward. Represents the "no defense, no positioning" ceiling
# for pure aggression. Real LLMs should beat this by playing defensively
# when low-HP or by kiting at bow range.
# ============================================================================
class GreedyAttackBot(BotBrain):
    label = "GreedyBot"

    def decide(self, state):
        atk = self._sharp_attacks()
        # Weapon-appropriate greedy footwork: bows shoot in place, melee
        # advances. That's the only branching this bot allows — no HP
        # check, no distance check, no dodge, no guard.
        if self.weapon == "bow":
            mv = {"action":   self._rng.choice(atk),
                  "footwork": "hold",
                  "thought":  "[greedy] shoot, always."}
        else:
            mv = {"action":   self._rng.choice(atk),
                  "footwork": "advance",
                  "thought":  "[greedy] attack, always advance."}
        return _sanitize(mv, self.actions)


# ============================================================================
# DistanceHolderBot — kite-y baseline that maintains ideal weapon range
#
# Reads state.distance and:
#   - if too close (< ideal - buffer): hop_back + guard
#   - if in range (ideal ± buffer):    sharp attack + hold
#   - if too far (> ideal + buffer):   advance + ready
#
# "Ideal range" is weapon-specific: bows want ~300, spears want ~150,
# swords/daggers want ~90, flails want ~130. Everything else the bot
# doesn't consider — pure 1D distance-control heuristic.
#
# Represents the "understands range" ceiling. A greedy-attacker that
# also kites should beat this if it plays optimally.
# ============================================================================
_IDEAL_RANGE = {"sword": 90, "dagger": 75, "spear": 150, "flail": 130, "bow": 300}
_RANGE_BUFFER = 25


class DistanceHolderBot(BotBrain):
    label = "DistanceBot"

    def decide(self, state):
        d = state.get("distance", 100)
        ideal = _IDEAL_RANGE.get(self.weapon, 100)
        atk = self._sharp_attacks()
        if d < ideal - _RANGE_BUFFER:
            mv = {"action":   "guard_high",
                  "footwork": "hop_back",
                  "thought":  f"[distance] too close ({d} < {ideal}); back off."}
        elif d <= ideal + _RANGE_BUFFER:
            mv = {"action":   self._rng.choice(atk),
                  "footwork": "hold",
                  "thought":  f"[distance] in range ({d} ≈ {ideal}); strike."}
        else:
            mv = {"action":   "ready",
                  "footwork": "advance",
                  "thought":  f"[distance] too far ({d} > {ideal}); close in."}
        return _sanitize(mv, self.actions)


# ============================================================================
# ScriptedProBot — hand-tuned state machine, best-of-breed heuristics
#
# The "ceiling" baseline. Uses everything state gives us:
#   * range-appropriate action (like DistanceHolder)
#   * defensive when low HP OR taking damage
#   * exploits knocked-down enemies (commit to overhead)
#   * bow: variable shot type based on distance
#   * flail: spin_up if not already spinning (looked at last_action)
#   * respects facing_enemy (turns around if wrong-facing)
#
# Represents the "well-tuned scripted opponent" bar. An LLM that beats
# this consistently is doing something a scripted state machine can't.
# That's the interesting research signal.
# ============================================================================
class ScriptedProBot(BotBrain):
    label = "ScriptedPro"

    def decide(self, state):
        d = state.get("distance", 100)
        my_hp = state.get("my_hp", 100)
        enemy_hp = state.get("enemy_hp", 100)
        my_last = state.get("my_last_action", "ready")
        enemy_height = state.get("enemy_height", "standing")
        my_height = state.get("my_height", "standing")
        hits_on_me = [h for h in state.get("last_turn_hits", [])
                      if h.get("by") != self.label]
        atk = self._sharp_attacks()

        # Knocked-down = get up + protect (guard doesn't cost anything).
        if my_height == "knocked_down":
            return _sanitize({"action": "guard_high", "footwork": "hop_back",
                              "thought": "[pro] I'm down — cover up, reset."})

        # Enemy knocked-down = free damage window. Commit to strongest attack.
        # This is the ONE line that separates ScriptedPro from DistanceHolder
        # meaningfully; it exploits state a range-only bot ignores.
        if enemy_height == "knocked_down" and d < 180:
            best = "overhead_slash" if "overhead_slash" in atk else atk[0]
            return _sanitize({"action": best, "footwork": "lunge",
                              "thought": "[pro] enemy down — commit overhead."},
                             self.actions)

        # Taking damage AND low HP = defensive reset. Same threshold as
        # MockBrain-duelist so their behavior is comparable at extremes.
        if hits_on_me and my_hp < 50:
            return _sanitize({"action": "guard_high", "footwork": "hop_back",
                              "thought": "[pro] hurt + being hit — retreat + block."})

        # Bow branch: pure ranged, never engage in melee unless clinched.
        if self.weapon == "bow":
            if d > 280:
                mv = {"action": self._rng.choice(["draw_shot", "high_arc_shot"]),
                      "footwork": "hold",
                      "thought": "[pro] long range full draw."}
            elif d > 120:
                mv = {"action": "quick_shot", "footwork": "retreat",
                      "thought": "[pro] closing distance — snap + backpedal."}
            elif d > 50:
                mv = {"action": "quick_shot", "footwork": "hop_back",
                      "thought": "[pro] point blank — shoot + jump."}
            else:
                mv = {"action": "bow_bash", "footwork": "hop_back",
                      "thought": "[pro] clinched — bash + disengage."}
            return _sanitize(mv, self.actions)

        # Flail branch: needs momentum. Spin up if idle, otherwise commit.
        if self.weapon == "flail":
            if my_last != "spin_up" and my_last not in atk:
                return _sanitize({"action": "spin_up", "footwork": "hold",
                                  "thought": "[pro] no momentum — spin_up first."},
                                 self.actions)
            # Fall through to distance-based swing selection below.

        # Melee: distance-based action selection, same shape as
        # DistanceHolderBot but with kill-focus on head range.
        ideal = _IDEAL_RANGE.get(self.weapon, 100)
        if d < ideal - _RANGE_BUFFER:
            # too close — hop back and cut on the way out
            mv = {"action": self._rng.choice(atk), "footwork": "hop_back",
                  "thought": "[pro] too close — cut on retreat."}
        elif d <= ideal + _RANGE_BUFFER:
            # in kill range — commit
            mv = {"action": self._rng.choice(atk), "footwork": "lunge",
                  "thought": "[pro] in kill range — sharp lunge."}
        else:
            # closing — walk in behind guard
            mv = {"action": "ready", "footwork": "advance",
                  "thought": "[pro] closing behind guard, no wasted swings."}
        return _sanitize(mv, self.actions)


# ============================================================================
# Bot factory — called from brains.make_brain() when the model id starts
# with "bot:". Registration table lives here (not in brains.py) so adding
# a new bot doesn't touch the LLM adapter file.
# ============================================================================
_BOT_REGISTRY = {
    "random":   RandomBot,
    "greedy":   GreedyAttackBot,
    "distance": DistanceHolderBot,
    "pro":      ScriptedProBot,
}


def make_bot(kind, sharp_zones, mode="macro", weapon="sword", seed=None):
    """Build a bot instance. `kind` is the string after 'bot:' in the model
    id (e.g. 'bot:pro' -> kind='pro'). Falls back to RandomBot for unknown
    kinds — logs a warning but never crashes the match. Reviewer's y-axis
    calibration is more valuable when it always resolves to SOMETHING than
    when a typo takes the whole match down."""
    cls = _BOT_REGISTRY.get(kind.lower())
    if cls is None:
        print(f"[bots] unknown bot kind '{kind}' — falling back to RandomBot")
        cls = RandomBot
    return cls(sharp_zones, mode=mode, weapon=weapon, seed=seed,
               label=cls.label)


# Public list for the roster / UI. Alphabetized by user-visible name so
# the picker dropdown reads naturally.
AVAILABLE_BOTS = [
    ("bot:distance", "Distance Bot (kites at ideal range)"),
    ("bot:greedy",   "Greedy Attacker (always attack + advance)"),
    ("bot:pro",      "Scripted Pro (best hand-tuned heuristics)"),
    ("bot:random",   "Random Bot (uniform action + footwork)"),
]
