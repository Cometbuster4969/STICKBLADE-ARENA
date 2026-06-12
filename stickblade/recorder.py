"""Replay recorder: captures a headless match into compact JSON + a
self-contained HTML viewer (canvas player). This is the bridge between the
Python physics engine (server-side) and the future web frontend.

Replay format (v1):
{
  "v": 1,
  "meta": { width, height, floor_y, fps, sharp, winner, result,
            p1: {name, color, dark, facing}, p2: {...} },
  "frames": [ [hp1, hp2, turn, over, x,y,a * 11 bodies * 2 fighters], ... ],
  "events": [ {f, k:"hit"|"clash", x, y, d, s, l, part}, ... ],
  "thoughts": [ {f, turn, a, b}, ... ]
}
Body order per fighter: torso, head, uarm, farm, off_uarm, off_farm,
thigh_f, shin_f, thigh_b, shin_b, sword.
"""
import json
import os

import config as C
from render import FX

BODY_ORDER = ["torso", "head", "uarm", "farm", "off_uarm", "off_farm",
              "thigh_f", "shin_f", "thigh_b", "shin_b", "sword"]


def _css(rgb):
    return "#%02x%02x%02x" % rgb


class RecordingFX(FX):
    """FX subclass that also logs hit/clash events with replay frame index."""

    def __init__(self, recorder):
        super().__init__()
        self.rec = recorder

    def hit(self, p, dmg, sharp, lethal, part):
        super().hit(p, dmg, sharp, lethal, part)
        self.rec.add_event("hit", p, dmg=dmg, sharp=sharp, lethal=lethal, part=part)

    def clash(self, p):
        super().clash(p)
        self.rec.add_event("clash", p)


class ReplayRecorder:
    def __init__(self, every=2):
        """every=2 -> sample at 30 fps from the 60 fps loop."""
        self.every = every
        self.frames = []
        self.events = []
        self.thoughts = []
        self._n = 0
        self._logged = 0
        self.match = None

    def attach(self, match):
        self.match = match

    # ------------------------------------------------------------ capture
    def add_event(self, kind, p, dmg=0, sharp=False, lethal=False, part=""):
        self.events.append({"f": len(self.frames), "k": kind,
                            "x": round(p[0], 1), "y": round(p[1], 1),
                            "d": round(dmg, 1), "s": int(bool(sharp)),
                            "l": int(bool(lethal)), "part": part})

    def tick(self):
        """Call once per 60fps loop iteration, after match.update()."""
        m = self.match
        if m.phase == m.PH_THINK or m.phase == m.PH_BANNER:
            return                       # skip idle LLM-waiting frames
        self._n += 1
        if self._n % self.every:
            return
        # new turn decided? capture both thoughts
        if len(m.log) > self._logged:
            self._logged = len(m.log)
            t = m.log[-1]
            self.thoughts.append({"f": len(self.frames), "turn": t["turn"],
                                  "a": t[m.f1.name]["thought"],
                                  "b": t[m.f2.name]["thought"]})
        row = [round(m.f1.hp, 1), round(m.f2.hp, 1), m.turn,
               1 if m.phase == m.PH_OVER else 0]
        for f in (m.f1, m.f2):
            for bname in BODY_ORDER:
                b = f.bodies[bname]
                row += [round(b.position.x, 1), round(b.position.y, 1),
                        round(b.angle, 3)]
        self.frames.append(row)

    # ------------------------------------------------------------ output
    def build(self):
        m = self.match
        return {
            "v": 1,
            "meta": {
                "width": C.WIDTH, "height": C.HEIGHT, "floor_y": C.FLOOR_Y,
                "fps": 60 // self.every, "sharp": m.sharp,
                "winner": m.winner, "result": m.result,
                "p1": {"name": m.f1.name, "color": _css(m.f1.color),
                       "dark": _css(m.f1.dark), "facing": m.f1.facing},
                "p2": {"name": m.f2.name, "color": _css(m.f2.color),
                       "dark": _css(m.f2.dark), "facing": m.f2.facing},
            },
            "frames": self.frames,
            "events": self.events,
            "thoughts": self.thoughts,
        }

    def save_json(self, path):
        with open(path, "w") as f:
            json.dump(self.build(), f, separators=(",", ":"))
        return path

    def save_html(self, path, template_path=None):
        here = os.path.dirname(os.path.abspath(__file__))
        template_path = template_path or os.path.join(here, "viewer_template.html")
        with open(template_path) as f:
            html = f.read()
        with open(os.path.join(here, "player.js")) as f:
            player_js = f.read()
        data = json.dumps(self.build(), separators=(",", ":"))
        html = html.replace("/*__PLAYER_JS__*/", player_js)
        html = html.replace("/*__REPLAY_DATA__*/null", data)
        with open(path, "w") as f:
            f.write(html)
        return path
