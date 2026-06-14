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
  bow:   ["arrowhead", "arrow_shaft", "bow_limb"],
};
const WEAPONS = [
  ["sword", "🗡 SWORD"],
  ["flail", "⛓ FLAIL"],
  ["bow",   "🏹 BOW"],
];

// ----- predict-streak (localStorage) ----------------------------------------
const STREAK_KEY = "sba.predictStreak";
const STREAK_BEST_KEY = "sba.predictBest";
function readStreak() {
  if (typeof window === "undefined") return { cur: 0, best: 0 };
  return {
    cur:  parseInt(localStorage.getItem(STREAK_KEY) || "0", 10) || 0,
    best: parseInt(localStorage.getItem(STREAK_BEST_KEY) || "0", 10) || 0,
  };
}
function writeStreak({ cur, best }) {
  try {
    localStorage.setItem(STREAK_KEY, String(cur));
    localStorage.setItem(STREAK_BEST_KEY, String(best));
  } catch (_) { /* private mode */ }
}

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
  const [prediction, setPrediction] = useState(null);   // "a" | "b" | "draw" | null
  const [streak, setStreak] = useState({ cur: 0, best: 0 });
  const [lastResult, setLastResult] = useState(null);   // "correct" | "wrong" | null

  const [lb, setLb] = useState([]);
  const [lbSharp, setLbSharp] = useState("");
  const [lbWeapon, setLbWeapon] = useState("");          // "" = all weapons
  const pollRef = useRef(null);
  const lbSharpId = useId();
  const lbWeaponId = useId();

  useEffect(() => { setStreak(readStreak()); }, []);

  useEffect(() => {
    getModels().then((ms) => {
      setModels(ms);
      setSelA(ms[0]?.id || "");
      setSelB(ms[1]?.id || ms[0]?.id || "");
    }).catch((e) => setStatus("✖ backend unreachable: " + e.message));
  }, []);

  useEffect(() => {
    getLeaderboard(lbSharp || undefined, lbWeapon || undefined)
      .then(setLb).catch(() => {});
  }, [lbSharp, lbWeapon, reveal]);

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
    setPrediction(null);
    setLastResult(null);
    setStatus("⚙ queuing match");
    try {
      const { match_id } = await createMatch({
        model_a: modelOf(selA, customA),
        model_b: modelOf(selB, customB),
        sharp, blind: true, mode, weapon,
      });
      setMatchId(match_id);
      setStatus("🧠 simulating — LLMs are fighting");
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
      // Update predict-streak if the user predicted before the match.
      if (prediction) {
        // The "engine_winner_side" is canvas-side ("a"=green, "b"=blue),
        // matching what the user predicted before the fight.
        const engineWinner = r.engine_winner_side;
        const correct = prediction === engineWinner;
        const next = correct
          ? { cur: streak.cur + 1, best: Math.max(streak.best, streak.cur + 1) }
          : { cur: 0, best: streak.best };
        setStreak(next);
        writeStreak(next);
        setLastResult(correct ? "correct" : "wrong");
      }
    } catch (e) {
      setStatus("✖ " + e.message);
    }
  }

  const shareUrl = matchId && typeof window !== "undefined"
    ? `${window.location.origin}/replay?id=${matchId}` : null;

  const showDots =
    busy && status && !status.startsWith("✖") && !status.endsWith(".");

  return (
    <>
      {/* ---------- Hero ---------- */}
      <section className="tagline">
        <h1>
          Two LLM Swordsmen.<br />
          <span className="accent">Physics Decides.</span>
        </h1>
        <p>
          You set the sharp zone
          <span className="dot">·</span>
          they fight blind
          <span className="dot">·</span>
          you vote without knowing which model is which.
        </p>
      </section>

      {/* ---------- Main grid ---------- */}
      <div className="row">
        {/* ===== Setup panel ===== */}
        <div className="panel glow-red">
          <div className="panel-head">
            <span className="panel-title"><span className="tick" /> Setup Duel</span>
          </div>

          <div className="row" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <ModelPicker label="Slot 1" slotIndex={1}
              models={models} value={selA} custom={customA}
              onChange={setSelA} onCustomChange={setCustomA} />
            <ModelPicker label="Slot 2" slotIndex={2}
              models={models} value={selB} custom={customB}
              onChange={setSelB} onCustomChange={setCustomB} />
          </div>

          <div>
            <label className="lbl">Weapon</label>
            <div className="zones">
              {WEAPONS.map(([w, label]) => (
                <div key={w} className={"zone" + (weapon === w ? " on" : "")}
                  role="button" tabIndex={0}
                  aria-pressed={weapon === w}
                  onClick={() => pickWeapon(w)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickWeapon(w); } }}>
                  {label}
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="lbl">Control mode</label>
            <div className="zones">
              <div className={"zone" + (mode === "macro" ? " on" : "")}
                role="button" tabIndex={0} aria-pressed={mode === "macro"}
                title="LLM picks tactical moves; engine executes clean swordplay"
                onClick={() => setMode("macro")}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setMode("macro"); } }}>
                🎯 MACRO
              </div>
              <div className={"zone" + (mode === "joint" ? " on" : "")}
                role="button" tabIndex={0} aria-pressed={mode === "joint"}
                title="LLM drives every joint raw — emergent, chaotic, true Toribash"
                onClick={() => setMode("joint")}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setMode("joint"); } }}>
                🧠 JOINT
              </div>
            </div>
          </div>

          <div>
            <label className="lbl">Dangerous zones — the twist</label>
            <div className="zones">
              {WEAPON_ZONES[weapon].map((z) => (
                <div key={z}
                  role="button" tabIndex={0}
                  aria-pressed={sharp.includes(z)}
                  className={"zone" + (sharp.includes(z) ? " on" : "")}
                  onClick={() => toggleZone(z)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleZone(z); } }}>
                  {z.replace("_", " ").toUpperCase()}
                </div>
              ))}
            </div>
          </div>

          <button className="fight-btn" onClick={fight} disabled={busy}>
            {busy ? "⚙ Simulating" : "⚔ Fight"}
          </button>
          <div className="status" aria-live="polite">
            {status}
            {showDots && <span className="dots" aria-hidden="true" />}
          </div>
        </div>

        {/* ===== Leaderboard panel ===== */}
        <div className="panel lb-panel glow-blue">
          <div className="panel-head">
            <span className="panel-title gold">
              <span className="tick" /> Leaderboard · Elo by Vote
            </span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <label htmlFor={lbWeaponId} className="visually-hidden"
                     style={{ position: "absolute", left: -9999 }}>
                Leaderboard weapon filter
              </label>
              <select
                id={lbWeaponId}
                className="lb-select"
                aria-label="Leaderboard weapon filter"
                value={lbWeapon}
                onChange={(e) => setLbWeapon(e.target.value)}
              >
                <option value="">all weapons</option>
                <option value="sword">sword</option>
                <option value="flail">flail</option>
                <option value="bow">bow</option>
              </select>
              <label htmlFor={lbSharpId} className="visually-hidden"
                     style={{ position: "absolute", left: -9999 }}>
                Leaderboard sharp-zone filter
              </label>
              <select
                id={lbSharpId}
                className="lb-select"
                aria-label="Leaderboard sharp-zone filter"
                value={lbSharp}
                onChange={(e) => setLbSharp(e.target.value)}
              >
                <option value="">overall</option>
                {(WEAPON_ZONES[lbWeapon] || ["tip","edge","back_edge","pommel"]).map((z) => (
                  <option key={z} value={z}>{z}</option>
                ))}
              </select>
            </div>
          </div>
          <LeaderboardTable rows={lb} compact />
        </div>
      </div>

      {/* ---------- Replay ---------- */}
      {replay && (
        <div className="panel" style={{ padding: 14 }}>
          <ReplayPlayer replay={replay} />
          {shareUrl && (
            <div className="share">
              share this duel: <a href={shareUrl}>{shareUrl}</a>
            </div>
          )}
        </div>
      )}

      {/* ---------- Predict-then-watch ----------
          Shown once the replay is loaded and the user hasn't predicted yet.
          Disappears as soon as they click — they then vote normally below. */}
      {replay && canVote && !prediction && (
        <div className="panel" style={{ padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 10 }}>
            <span className="panel-title">
              <span className="tick" /> Predict the Winner (before voting)
            </span>
            <span style={{ color: "var(--dim)", fontSize: 12, letterSpacing: 1 }}>
              streak <b style={{ color: "var(--gold)" }}>{streak.cur}</b>
              <span style={{ margin: "0 6px", color: "var(--mute)" }}>·</span>
              best <b style={{ color: "var(--text)" }}>{streak.best}</b>
            </span>
          </div>
          <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 10 }}>
            Watched the fight? Lock in your prediction first — you'll see if you were right after you vote.
          </p>
          <div className="vote-row">
            <button className="vote-a" onClick={() => setPrediction("a")}>
              🔮 Fighter A wins
            </button>
            <button className="vote-draw" onClick={() => setPrediction("draw")}>
              Draw
            </button>
            <button className="vote-b" onClick={() => setPrediction("b")}>
              Fighter B wins 🔮
            </button>
          </div>
        </div>
      )}

      {/* ---------- Vote ---------- */}
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

      {/* ---------- Reveal ---------- */}
      {reveal && (
        <div className="panel reveal">
          🎭 Reveal — Fighter A was{" "}
          <b>{reveal.names[reveal.canvas_a_model || reveal.model_a]}</b>{" "}
          ({fmtElo(reveal.elo_change?.[reveal.canvas_a_model || reveal.model_a])})
          {" · "}
          Fighter B was <b>{reveal.names[reveal.canvas_b_model || reveal.model_b]}</b>{" "}
          ({fmtElo(reveal.elo_change?.[reveal.canvas_b_model || reveal.model_b])})
          {" · "}
          engine result: {reveal.engine_winner_side === "draw"
            ? "draw"
            : `Fighter ${reveal.engine_winner_side.toUpperCase()} won`}{" "}
          by {reveal.method}
          {lastResult && (
            <div style={{ marginTop: 10, fontSize: 14, fontWeight: 700,
                          color: lastResult === "correct" ? "var(--green)" : "var(--red-2)",
                          letterSpacing: 1, textTransform: "uppercase" }}>
              {lastResult === "correct"
                ? `✓ Prediction correct — streak ${streak.cur}`
                : "✗ Prediction wrong — streak reset"}
            </div>
          )}
        </div>
      )}
    </>
  );
}

const fmtElo = (v) =>
  v === undefined ? "" : `${v >= 0 ? "+" : ""}${v} Elo`;
