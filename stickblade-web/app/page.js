"use client";
import { useEffect, useId, useRef, useState } from "react";
import ModelPicker, { CUSTOM } from "@/components/ModelPicker";
import ReplayPlayer from "@/components/ReplayPlayer";
import LeaderboardTable from "@/components/LeaderboardTable";
import { getModels, createMatch, getMatch, getReplay, postVote,
         getLeaderboard } from "@/lib/api";

const WEAPON_ZONES = {
  sword: ["tip", "edge", "back_edge", "pommel"],
  flail: ["ball", "spikes", "chain", "handle"],
  bow: ["arrowhead", "arrow_shaft", "bow_limb"],
};
const WEAPONS = [["sword", "🗡 SWORD"], ["flail", "⛓ FLAIL"], ["bow", "🏹 BOW"]];
const ZONES = ["tip", "edge", "back_edge", "pommel"]; // leaderboard tabs (sword legacy)

export default function FightPage() {
  const [models, setModels] = useState([]);
  const [selA, setSelA] = useState("");
  const [selB, setSelB] = useState("");
  const [customA, setCustomA] = useState("");
  const [customB, setCustomB] = useState("");
  const [sharp, setSharp] = useState(["tip"]);
  const [mode, setMode] = useState("macro");
  const [weapon, setWeapon] = useState("sword");

  const pickWeapon = (w) => {
    setWeapon(w);
    setSharp([WEAPON_ZONES[w][0]]);
  };
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [matchId, setMatchId] = useState(null);
  const [replay, setReplay] = useState(null);
  const [canVote, setCanVote] = useState(false);
  const [reveal, setReveal] = useState(null);
  const [lb, setLb] = useState([]);
  const [lbSharp, setLbSharp] = useState("");
  const pollRef = useRef(null);
  const lbSelectId = useId();

  useEffect(() => {
    getModels().then((ms) => {
      setModels(ms);
      setSelA(ms[0]?.id || "");
      setSelB(ms[1]?.id || ms[0]?.id || "");
    }).catch((e) => setStatus("✖ backend unreachable: " + e.message));
  }, []);
  useEffect(() => {
    getLeaderboard(lbSharp || undefined).then(setLb).catch(() => {});
  }, [lbSharp, reveal]);
  useEffect(() => () => clearTimeout(pollRef.current), []);

  const toggleZone = (z) =>
    setSharp((s) => {
      const next = s.includes(z) ? s.filter((x) => x !== z) : [...s, z];
      return next.length ? next : s;
    });

  const modelOf = (sel, custom) => (sel === CUSTOM ? custom.trim() : sel);

  async function fight() {
    setBusy(true);
    setReveal(null);
    setCanVote(false);
    setStatus("⚙ queuing match…");
    try {
      const { match_id } = await createMatch({
        model_a: modelOf(selA, customA),
        model_b: modelOf(selB, customB),
        sharp, blind: true, mode, weapon,
      });
      setMatchId(match_id);
      setStatus("🧠 simulating — LLMs are fighting…");
      poll(match_id);
    } catch (e) {
      setStatus("✖ " + e.message);
      setBusy(false);
    }
  }
  function poll(id) {
    clearTimeout(pollRef.current);
    pollRef.current = setTimeout(async () => {
      try {
        const s = await getMatch(id);
        if (s.status === "done") {
          const r = await getReplay(id);
          setReplay(r);
          setCanVote(!s.voted);
          setStatus("");
          setBusy(false);
          return;
        }
        if (s.status === "error") {
          setStatus("✖ simulation error: " + (s.error || ""));
          setBusy(false);
          return;
        }
        poll(id);
      } catch (e) {
        setStatus("✖ " + e.message);
        setBusy(false);
      }
    }, 1500);
  }
  async function vote(choice) {
    setCanVote(false);
    try {
      const r = await postVote(matchId, choice);
      setReveal(r);
    } catch (e) {
      setStatus("✖ " + e.message);
    }
  }

  const shareUrl = matchId && typeof window !== "undefined"
    ? `${window.location.origin}/replay?id=${matchId}` : null;

  return (
    <>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        two LLM swordsmen · you set the sharp zone · physics decides · you vote blind
      </p>
      <div className="row">
        <div className="panel" style={{ flex: 1, minWidth: 300,
             display: "flex", flexDirection: "column", gap: 10 }}>
          <ModelPicker label="Fighter A (green)" accent="var(--green)"
            models={models} value={selA} custom={customA}
            onChange={setSelA} onCustomChange={setCustomA} />
          <ModelPicker label="Fighter B (blue)" accent="var(--blue)"
            models={models} value={selB} custom={customB}
            onChange={setSelB} onCustomChange={setCustomB} />
          <div>
            <label className="lbl">Weapon</label>
            <div className="zones">
              {WEAPONS.map(([w, label]) => (
                <div key={w} className={"zone" + (weapon === w ? " on" : "")}
                  onClick={() => pickWeapon(w)}>{label}</div>
              ))}
            </div>
          </div>
          <div>
            <label className="lbl">Control mode</label>
            <div className="zones">
              <div className={"zone" + (mode === "macro" ? " on" : "")}
                title="LLM picks tactical moves; engine executes clean swordplay"
                onClick={() => setMode("macro")}>🎯 MACRO</div>
              <div className={"zone" + (mode === "joint" ? " on" : "")}
                title="LLM drives every joint raw — emergent, chaotic, true Toribash"
                onClick={() => setMode("joint")}>🧠 JOINT</div>
            </div>
          </div>
          <div>
            <label className="lbl">Dangerous zones — the twist</label>
            <div className="zones">
              {WEAPON_ZONES[weapon].map((z) => (
                <div key={z}
                  className={"zone" + (sharp.includes(z) ? " on" : "")}
                  onClick={() => toggleZone(z)}>
                  {z.replace("_", " ").toUpperCase()}
                </div>
              ))}
            </div>
          </div>
          <button className="fight-btn" onClick={fight} disabled={busy}>
            ⚔ FIGHT
          </button>
          <div className="status">{status}</div>
        </div>

        <div className="panel lb-panel" style={{ flex: 1, minWidth: 300 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "center", marginBottom: 8 }}>
            <label htmlFor={lbSelectId} className="lbl" style={{ margin: 0 }}>
              Leaderboard (Elo by vote)
            </label>
            <select
              id={lbSelectId}
              aria-label="Leaderboard sharp-zone filter"
              style={{ width: "auto", padding: "4px 8px", fontSize: 12 }}
              value={lbSharp}
              onChange={(e) => setLbSharp(e.target.value)}
            >
              <option value="">overall</option>
              {ZONES.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          <LeaderboardTable rows={lb} compact />
        </div>
      </div>

      {replay && (
        <div style={{ width: "100%", marginTop: 10 }}>
          <ReplayPlayer replay={replay} />
          {shareUrl && (
            <div className="share">
              share this duel: <a href={shareUrl}>{shareUrl}</a>
            </div>
          )}
        </div>
      )}

      {canVote && (
        <div className="vote-row">
          <button className="vote-a" onClick={() => vote("a")}>
            🗳 Fighter A fought better
          </button>
          <button className="vote-draw" onClick={() => vote("draw")}>Draw</button>
          <button className="vote-b" onClick={() => vote("b")}>
            Fighter B fought better 🗳
          </button>
        </div>
      )}

      {reveal && (
        <div className="panel reveal">
          🎭 Reveal — Fighter A was <b>{reveal.names[reveal.model_a]}</b>
          {" "}({fmtElo(reveal.elo_change?.[reveal.model_a])}) ·
          Fighter B was <b>{reveal.names[reveal.model_b]}</b>
          {" "}({fmtElo(reveal.elo_change?.[reveal.model_b])}) ·
          engine result: {reveal.engine_winner_side === "draw"
            ? "draw"
            : `Fighter ${reveal.engine_winner_side.toUpperCase()} won`}{" "}
          by {reveal.method}
        </div>
      )}
    </>
  );
}

const fmtElo = (v) =>
  v === undefined ? "" : `${v >= 0 ? "+" : ""}${v} Elo`;
