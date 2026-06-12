"""LLM brains (GPT / Gemini) + scripted mock fighters.

Each brain receives a JSON game state and must return:
  {"thought": "...", "action": <ACTIONS>, "footwork": <FOOTWORK>}
"""
import json
import random
import re
import threading
import config as C
from moves import ACTIONS, FOOTWORK, ACTION_ZONE

SYSTEM_PROMPT = """You are a stickman swordsman in a physics-based duel (like Toribash).
Each turn you pick ONE action and ONE footwork; physics then runs for 3 seconds.

WEAPON RULES (critical): only these sword zones are SHARP and deal real damage: {sharp}.
All other zones are blunt (tiny chip damage at best). Zone each action leads with:
  thrust->tip | overhead_slash->edge | horizontal_slash->edge | rising_slash->back_edge | pommel_strike->pommel
A fast SHARP hit to the head is an INSTANT KILL. Blunt hits mostly just push.

Actions: {actions}
Footwork: {footwork}
  lunge = explosive forward burst (good for closing + thrust power)
  hop_back = jump backward (escape pressure)

Distance guide: <70 = clinch range, 70-150 = strike range, 150-260 = closing range, >260 = far.

Reply with ONLY a JSON object, no markdown:
{{"thought": "<your tactical reasoning, max 30 words>", "action": "...", "footwork": "..."}}"""


def build_state(me, foe, turn, max_turns, last_events):
    d = (foe.pos() - me.pos()).length
    rel = []
    for e in last_events:
        rel.append({"by": e["attacker"], "zone": e["zone"], "hit_part": e["part"],
                    "damage": e["damage"], "was_sharp": e["sharp"]})
    return {
        "turn": turn, "turns_left": max_turns - turn,
        "my_hp": round(me.hp, 1), "enemy_hp": round(foe.hp, 1),
        "distance": round(d),
        "my_height": "knocked_down" if me.pos().y < me.stand_torso_y - 30 else "standing",
        "enemy_height": "knocked_down" if foe.pos().y < foe.stand_torso_y - 30 else "standing",
        "enemy_last_action": foe.last_action,
        "my_last_action": me.last_action,
        "enemy_sword_tip_distance_to_me": round((foe.tip_pos() - me.pos()).length),
        "last_turn_hits": rel,
    }


def _extract_json(text):
    text = re.sub(r"```(json)?", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json")
    return json.loads(m.group(0))


def _sanitize(d):
    a = d.get("action", "ready")
    f = d.get("footwork", "hold")
    if a not in ACTIONS:
        a = "ready"
    if f not in FOOTWORK:
        f = "hold"
    t = str(d.get("thought", ""))[:160]
    return {"action": a, "footwork": f, "thought": t}


class Brain:
    label = "BASE"

    def __init__(self, sharp_zones, mode="macro"):
        self.sharp = sharp_zones
        self.mode = mode
        if mode == "joint":
            from joint_mode import build_joint_system_prompt
            self.sys = build_joint_system_prompt(sharp_zones)
        else:
            self.sys = SYSTEM_PROMPT.format(
                sharp=", ".join(sharp_zones).upper(),
                actions=", ".join(ACTIONS), footwork=", ".join(FOOTWORK))
        self.history = []

    def _clean(self, raw):
        """Mode-aware sanitization of a parsed LLM reply."""
        if self.mode == "joint":
            from joint_mode import sanitize_joint_reply
            return sanitize_joint_reply(raw)
        return _sanitize(raw)

    def decide(self, state):
        """Blocking; called from worker thread. Returns sanitized dict."""
        raise NotImplementedError

    def decide_with_timeout(self, state):
        out = {}
        def run():
            try:
                out["r"] = self.decide(state)
            except Exception as e:
                out["err"] = str(e)
        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(C.LLM_TIMEOUT)
        if "r" in out:
            return out["r"]
        if self.mode == "joint":
            from joint_mode import MockJointBrain
            fb = MockJointBrain(self.sharp).decide(state)
        else:
            fb = MockBrain(self.sharp, "duelist").decide(state)
        fb["thought"] = f"[{self.label} fallback: {out.get('err','timeout')[:60]}] " + fb["thought"]
        return fb


# ---------------------------------------------------------------- mock AI
PERSONALITIES = {
    "duelist":  "patient counter-fighter",
    "berserker": "relentless aggression",
}


class MockBrain(Brain):
    def __init__(self, sharp_zones, personality="duelist", label=None):
        super().__init__(sharp_zones, "macro")
        self.p = personality
        self.label = label or f"Mock-{personality}"

    def _sharp_attacks(self):
        atk = [a for a, z in ACTION_ZONE.items() if z in self.sharp]
        return atk or ["thrust"]

    def decide(self, state):
        d = state["distance"]
        hits_on_me = [h for h in state["last_turn_hits"] if h["by"] != self.label]
        atk = self._sharp_attacks()
        if state["my_height"] == "knocked_down":
            return _sanitize({"action": "guard_high", "footwork": "hop_back",
                              "thought": "I'm down — cover up and create space."})
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
        return _sanitize(mv)


# ---------------------------------------------------------------- real LLMs
class GPTBrain(Brain):
    label = "GPT"

    def __init__(self, sharp_zones, model=C.OPENAI_MODEL, mode="macro"):
        super().__init__(sharp_zones, mode)
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


class GeminiBrain(Brain):
    label = "GEMINI"

    def __init__(self, sharp_zones, model=C.GEMINI_MODEL, mode="macro"):
        super().__init__(sharp_zones, mode)
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
                max_output_tokens=150, response_mime_type="application/json"))
        txt = r.text
        self.convo.append({"role": "model", "parts": [{"text": txt}]})
        return self._clean(_extract_json(txt))


class OpenRouterBrain(Brain):
    """Any model on OpenRouter via the OpenAI-compatible chat endpoint.

    model: e.g. 'meta-llama/llama-3.3-70b-instruct:free' or 'openai/gpt-4o-mini'
    """

    def __init__(self, sharp_zones, model, label=None, mode="macro"):
        super().__init__(sharp_zones, mode)
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
        r = self._client.post("/chat/completions", json={
            "model": self.model, "messages": msgs,
            "temperature": 0.8, "max_tokens": 200,
        })
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
        self.history += [{"role": "user", "content": user},
                         {"role": "assistant", "content": txt}]
        return self._clean(_extract_json(txt))


def make_brain(kind, sharp_zones, mode="macro"):
    kind = kind.lower()

    def _mock(personality="duelist", label=None):
        if mode == "joint":
            from joint_mode import MockJointBrain
            return MockJointBrain(sharp_zones, label=label)
        return MockBrain(sharp_zones, personality, label=label)

    # explicit mock personality: "mock:duelist" / "mock:berserker"
    if kind.startswith("mock:"):
        p = kind.split(":", 1)[1]
        return _mock(p if p in PERSONALITIES else "duelist")
    # OpenRouter model id (contains "/"), e.g. meta-llama/llama-3.3-70b:free
    if "/" in kind:
        if C.OPENROUTER_API_KEY:
            try:
                return OpenRouterBrain(sharp_zones, kind, mode=mode)
            except Exception as e:
                print(f"[brains] OpenRouter init failed ({e}); using mock.")
        else:
            print(f"[brains] No OPENROUTER_API_KEY — '{kind}' slot uses mock.")
        label = kind.split("/")[-1].replace(":free", "")[:20] + "(mock)"
        return _mock("duelist", label=label)
    if kind == "gpt":
        if C.OPENAI_API_KEY:
            try:
                return GPTBrain(sharp_zones, mode=mode)
            except Exception as e:
                print(f"[brains] GPT init failed ({e}); using mock.")
        else:
            print("[brains] No OPENAI_API_KEY — GPT slot uses mock.")
        return _mock("duelist", label="GPT(mock)")
    if kind == "gemini":
        if C.GEMINI_API_KEY:
            try:
                return GeminiBrain(sharp_zones, mode=mode)
            except Exception as e:
                print(f"[brains] Gemini init failed ({e}); using mock.")
        else:
            print("[brains] No GEMINI_API_KEY — Gemini slot uses mock.")
        return _mock("berserker", label="GEMINI(mock)")
    return _mock(kind if kind in PERSONALITIES else "duelist")
