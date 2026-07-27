"""Replay recorder: captures a headless match into compact JSON + a
self-contained HTML viewer (canvas player). This is the bridge between the
Python physics engine (server-side) and the future web frontend.

Replay format (v1):
{
  "v": 2,
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
# extra per-weapon bodies appended after BODY_ORDER (flail chain + ball)
FLAIL_EXTRA = ["flail_link0", "flail_link1", "flail_link2", "flail_ball"]


def _css(rgb):
    return "#%02x%02x%02x" % rgb


class RecordingFX(FX):
    """FX subclass that also logs hit/clash events with replay frame index."""

    def __init__(self, recorder):
        super().__init__()
        self.rec = recorder

    def hit(self, p, dmg, sharp, lethal, part, attacker=None):
        super().hit(p, dmg, sharp, lethal, part, attacker=attacker)
        self.rec.add_event("hit", p, dmg=dmg, sharp=sharp, lethal=lethal,
                           part=part, attacker=attacker)

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
        # Pre-fight trash talk per fighter (canvas-side a/b strings).
        # Populated by server.py before the simulation starts.
        self.quips = {"a": "", "b": ""}
        # How many turns in this match used a scripted fallback brain
        # (LLM timed out, errored, or returned bad JSON). Frontend uses
        # this to decide whether to show the "scripted fallback" banner.
        self.fallback_turns = 0
        self._n = 0
        self._logged = 0
        self.match = None

    def set_quips(self, quip_a, quip_b):
        self.quips = {"a": quip_a or "", "b": quip_b or ""}

    def attach(self, match):
        self.match = match

    # ------------------------------------------------------------ capture
    def add_event(self, kind, p, dmg=0, sharp=False, lethal=False, part="",
                  attacker=None):
        # `attacker` is fighter name ("Fighter A" / "Fighter B") — used
        # by the proxy-metrics rollup in build() to partition damage
        # per-side. Optional so existing callers (clash, etc.) keep
        # working; only 'hit' events actually populate it.
        ev = {"f": len(self.frames), "k": kind,
              "x": round(p[0], 1), "y": round(p[1], 1),
              "d": round(dmg, 1), "s": int(bool(sharp)),
              "l": int(bool(lethal)), "part": part}
        if attacker is not None:
            ev["by"] = attacker    # short key, JSON payload stays small
        self.events.append(ev)

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
            # Track whether either fighter fell back this turn (used by the
            # frontend to surface a small "scripted fallback in use" banner
            # so users know they're watching mock brains, not real LLMs).
            a_reply = t[m.f1.name]
            b_reply = t[m.f2.name]
            if a_reply.get("_fallback") or b_reply.get("_fallback"):
                self.fallback_turns += 1
            self.thoughts.append({"f": len(self.frames), "turn": t["turn"],
                                  "a": a_reply["thought"],
                                  "b": b_reply["thought"]})
        row = [round(m.f1.hp, 1), round(m.f2.hp, 1), m.turn,
               1 if m.phase == m.PH_OVER else 0]
        extra = FLAIL_EXTRA if m.weapon == "flail" else []
        for f in (m.f1, m.f2):
            for bname in BODY_ORDER + extra:
                b = f.bodies[bname]
                row += [round(b.position.x, 1), round(b.position.y, 1),
                        round(b.angle, 3)]
        # live arrows (bow): flat [x,y,a]*n for each fighter appended at end
        if m.weapon == "bow" and m.arrows:
            for fid in (1, 2):
                pos = m.arrows[fid].positions()
                row.append(len(pos))
                for x, y, a in pos:
                    row += [x, y, a]
        self.frames.append(row)

    # ------------------------------------------------------------ output
    def build(self):
        m = self.match
        result = m.result
        if result is None:          # match didn't finish: synthesize
            if abs(m.f1.hp - m.f2.hp) < 0.5:
                w, method = None, "incomplete_draw"
            else:
                w = m.f1.name if m.f1.hp > m.f2.hp else m.f2.name
                method = "incomplete_points"
            result = {"winner": w, "method": method, "turns": m.turn,
                      "final_hp": {m.f1.name: round(m.f1.hp, 1),
                                   m.f2.name: round(m.f2.hp, 1)}}
        winner_txt = m.winner or (f"{result['winner']} ahead" if result["winner"]
                                  else "unfinished")
        # Tier S #3: compute proxy metrics from stored events + thoughts +
        # frames. These are OBJECTIVE (physics-derived, not vote-derived)
        # so the objective-skill leaderboard can rank models without
        # needing the small-N human vote pool. Cheap: single pass over
        # events (~dozens per match) + one pass over thoughts (~24).
        metrics = self._proxy_metrics()
        return {
            "v": 2,
            "meta": {
                "width": C.WIDTH, "height": C.HEIGHT, "floor_y": C.FLOOR_Y,
                "fps": 60 // self.every, "sharp": m.sharp,
                "weapon": m.weapon,
                "arena": getattr(m, "arena", "normal"),
                "winner": winner_txt, "result": result,
                "p1": {"name": m.f1.name, "color": _css(m.f1.color),
                       "dark": _css(m.f1.dark), "facing": m.f1.facing},
                "p2": {"name": m.f2.name, "color": _css(m.f2.color),
                       "dark": _css(m.f2.dark), "facing": m.f2.facing},
                # Pre-fight trash talk (canvas-side). Player.js renders these
                # as speech bubbles over each fighter at replay start.
                "quips": self.quips,
                # how many turns used a scripted fallback brain (LLM error/timeout)
                "fallback_turns": self.fallback_turns,
                "total_turns": m.turn,
                # Tier S #3: objective proxy metrics per fighter, computed
                # from the event stream. Powers the objective-skill
                # leaderboard alongside human-vote Elo. See _proxy_metrics()
                # for definitions.
                "metrics": metrics,
            },
            "frames": self.frames,
            "events": self.events,
            "thoughts": self.thoughts,
        }

    # ---------------------------------------------- proxy metrics rollup
    def _proxy_metrics(self):
        """Roll up objective per-fighter metrics from stored events +
        thoughts + frames. All computed once at build() time — cheap,
        deterministic, replayable from the stored data.

        Definitions (locked in Tier S #3, document changes here if
        they evolve):
          damage_dealt_{a,b}   sum of `d` on hit events where by==A/B
          hits_landed_{a,b}    count of hit events with damage > 0
                               where by==A/B
          hits_attempted_{a,b} count of turns where that fighter's
                               action is a strike (not guard/ready)
          fallback_turns_{a,b} count of turns where that fighter used
                               scripted-fallback brain (LLM timed
                               out / errored / returned malformed JSON)
          avg_distance         mean over sampled frames of torso-torso
                               distance in pixels
        """
        m = self.match
        a_name = m.f1.name
        b_name = m.f2.name
        # Actions that DON'T count as attempted attacks. Anything else
        # is a strike/swing/shot attempt (whether it lands or not).
        DEFENSIVE_ACTIONS = {"guard_high", "guard_low", "ready"}

        d_a = d_b = 0.0
        h_a = h_b = 0
        for ev in self.events:
            if ev.get("k") != "hit":
                continue
            by = ev.get("by")
            dmg = float(ev.get("d", 0))
            if dmg <= 0:
                continue
            if by == a_name:
                d_a += dmg;  h_a += 1
            elif by == b_name:
                d_b += dmg;  h_b += 1

        att_a = att_b = 0
        fb_a = fb_b = 0
        # Walk the match log directly for authoritative per-side action
        # + fallback data (self.thoughts is a UI convenience mirror; the
        # raw log has per-side reply dicts with _fallback flags).
        for t in getattr(m, "log", []):
            a_reply = t.get(a_name, {}) or {}
            b_reply = t.get(b_name, {}) or {}
            a_action = a_reply.get("action")
            b_action = b_reply.get("action")
            if a_action and a_action not in DEFENSIVE_ACTIONS:
                att_a += 1
            if b_action and b_action not in DEFENSIVE_ACTIONS:
                att_b += 1
            if a_reply.get("_fallback"):
                fb_a += 1
            if b_reply.get("_fallback"):
                fb_b += 1

        # Avg torso-torso distance across sampled frames. Frame layout
        # from tick(): first 4 slots are meta, then per-fighter body
        # positions in BODY_ORDER (+ optional FLAIL_EXTRA). Torso is
        # the first body in BODY_ORDER per ragdoll.BODY_ORDER — index
        # 4 (f1 torso x), 7 (f1 torso y from BODY_ORDER order), 4+len*3
        # for f2. Safer: import BODY_ORDER and compute the offsets
        # explicitly so this doesn't rot if the frame schema changes.
        from ragdoll import BODY_ORDER
        try:
            torso_idx = BODY_ORDER.index("torso")
        except ValueError:
            torso_idx = 0   # if 'torso' isn't in BODY_ORDER anymore, fallback
        stride = len(BODY_ORDER) + (5 if m.weapon == "flail" else 0)  # FLAIL_EXTRA=5
        f1_torso_off = 4 + torso_idx * 3
        f2_torso_off = 4 + stride * 3 + torso_idx * 3
        total_d = 0.0
        n_samples = 0
        for row in self.frames:
            # Skip frames with fewer floats than expected (partial rows
            # from early match teardown — belt and braces, cheap).
            if len(row) <= f2_torso_off + 1:
                continue
            x1, y1 = row[f1_torso_off], row[f1_torso_off + 1]
            x2, y2 = row[f2_torso_off], row[f2_torso_off + 1]
            total_d += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            n_samples += 1
        avg_distance = round(total_d / n_samples, 1) if n_samples else 0.0

        return {
            "damage_dealt_a":   round(d_a, 1),
            "damage_dealt_b":   round(d_b, 1),
            "hits_landed_a":    h_a,
            "hits_landed_b":    h_b,
            "hits_attempted_a": att_a,
            "hits_attempted_b": att_b,
            "fallback_turns_a": fb_a,
            "fallback_turns_b": fb_b,
            "avg_distance":     avg_distance,
        }

    def save_json(self, path):
        with open(path, "w") as f:
            json.dump(self.build(), f, separators=(",", ":"))
        return path

    def save_html(self, path, template_path=None):
        """Bake a self-contained HTML replay (data + player inlined).

        Player source: prefers stickblade-web/public/player.js (the same
        battle-tested copy the Next.js frontend uses). Falls back to
        stickblade/player.js only if the frontend tree isn't present —
        which mirrors what server.py's /static/player.js route does.
        Prevents the drift bug where the two copies got out of sync.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        template_path = template_path or os.path.join(here, "viewer_template.html")
        with open(template_path) as f:
            html = f.read()
        player_candidates = [
            os.path.normpath(os.path.join(here, "..", "stickblade-web",
                                          "public", "player.js")),
            os.path.join(here, "player.js"),
        ]
        player_path = next((p for p in player_candidates if os.path.exists(p)),
                           None)
        if player_path is None:
            raise FileNotFoundError(
                "player.js not found in stickblade-web/public/ or "
                "stickblade/. Cannot bake standalone HTML replay.")
        with open(player_path) as f:
            player_js = f.read()
        data = json.dumps(self.build(), separators=(",", ":"))
        html = html.replace("/*__PLAYER_JS__*/", player_js)
        html = html.replace("/*__REPLAY_DATA__*/null", data)
        with open(path, "w") as f:
            f.write(html)
        return path
