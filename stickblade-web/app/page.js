"use client";
import { useEffect, useId, useState } from "react";
import ModelPicker, { CUSTOM } from "@/components/ModelPicker";
import ReplayPlayer from "@/components/ReplayPlayer";
import LeaderboardTable from "@/components/LeaderboardTable";
import WaitPanel from "@/components/WaitPanel";
import ByokPanel from "@/components/ByokPanel";
import OnboardingCard from "@/components/OnboardingCard";
import ShareButton from "@/components/ShareButton";
import FAQ from "@/components/FAQ";
import { readByokKey, readByokEnabled } from "@/lib/byok";
import { getModels, createMatch, getMatch, getReplay, postVote,
         getLeaderboard, startKeepalive } from "@/lib/api";

const WEAPON_ZONES = {
  sword:  ["tip", "edge", "back_edge", "pommel"],
  dagger: ["tip", "edge", "back_edge", "pommel"],
  spear:  ["tip", "shaft", "butt"],
  flail:  ["ball", "spikes", "chain", "handle"],
  bow:    ["arrowhead", "arrow_shaft", "bow_limb"],
};
const WEAPONS = [
  ["sword",  "🗡 SWORD"],
  ["dagger", "🔪 DAGGER"],
  ["spear",  "⊥ SPEAR"],
  ["flail",  "⛓ FLAIL"],
  ["bow",    "🏹 BOW"],
];
const ARENAS = [
  ["normal",      "🏟 NORMAL"],
  ["ice",         "❄ ICE"],
  ["low_gravity", "🌙 LOW G"],
];

// ----- predict-streak + accuracy (localStorage) -----------------------------
// Two counters:
//   sba.predictStreak / sba.predictBest — current + all-time-best streak
//   sba.predictWins   / sba.predictTotal — lifetime accuracy denominator
// Accuracy is stored separately from streak so a wrong prediction doesn't
// wipe historical hit-rate — just resets the current streak.
const STREAK_KEY = "sba.predictStreak";
const STREAK_BEST_KEY = "sba.predictBest";
const PREDICT_WINS_KEY = "sba.predictWins";
const PREDICT_TOTAL_KEY = "sba.predictTotal";
function readStreak() {
  if (typeof window === "undefined")
    return { cur: 0, best: 0, wins: 0, total: 0 };
  return {
    cur:   parseInt(localStorage.getItem(STREAK_KEY) || "0", 10) || 0,
    best:  parseInt(localStorage.getItem(STREAK_BEST_KEY) || "0", 10) || 0,
    wins:  parseInt(localStorage.getItem(PREDICT_WINS_KEY) || "0", 10) || 0,
    total: parseInt(localStorage.getItem(PREDICT_TOTAL_KEY) || "0", 10) || 0,
  };
}
function writeStreak({ cur, best, wins, total }) {
  try {
    localStorage.setItem(STREAK_KEY, String(cur));
    localStorage.setItem(STREAK_BEST_KEY, String(best));
    localStorage.setItem(PREDICT_WINS_KEY, String(wins));
    localStorage.setItem(PREDICT_TOTAL_KEY, String(total));
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
  const [arena, setArena] = useState("normal");

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
  const [streak, setStreak] = useState({ cur: 0, best: 0, wins: 0, total: 0 });
  const [lastResult, setLastResult] = useState(null);   // "correct" | "wrong" | null

  const [lb, setLb] = useState([]);
  const [lbSharp, setLbSharp] = useState("");
  const [lbWeapon, setLbWeapon] = useState("");          // "" = all weapons
  const lbSharpId = useId();
  const lbWeaponId = useId();

  useEffect(() => { setStreak(readStreak()); }, []);

  // Keep the HF Space backend warm while a user is on the page.
  // Without this, the Space sleeps after ~10 min of no traffic and the
  // next match takes 30-60s to wake the container — which the brain
  // layer reads as a timeout and falls back to a mock. Five-minute
  // health pings keep it hot for free.
  useEffect(() => startKeepalive(), []);

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

  const toggleZone = (z) =>
    setSharp((s) => {
      const next = s.includes(z) ? s.filter((x) => x !== z) : [...s, z];
      return next.length ? next : s;
    });

  const modelOf = (sel, custom) => (sel === CUSTOM ? custom.trim() : sel);

  async function fight() {
    setBusy(true);
    setReplay(null);
    setReveal(null);
    setCanVote(false);
    setPrediction(null);
    setLastResult(null);
    setStatus("");
    setMatchId(null);
    try {
      // BYOK: include the user's own OpenRouter key ONLY if they've
      // enabled it via the ByokPanel. Backend uses it in place of its
      // env var for THIS match only, then discards. Never persisted.
      const body = {
        model_a: modelOf(selA, customA),
        model_b: modelOf(selB, customB),
        sharp, blind: true, mode, weapon, arena,
      };
      if (readByokEnabled()) {
        const k = readByokKey();
        if (k) body.api_key = k;
      }
      const { match_id } = await createMatch(body);
      setMatchId(match_id);
      // Polling + status display are now owned by <WaitPanel>. It calls
      // onWaitReady(mid) when the match is done or (mid=null, err) if
      // simulation failed — we do the replay hand-off from there.
    } catch (e) {
      setStatus("✖ " + e.message);
      setBusy(false);
    }
  }

  async function onWaitReady(id, err) {
    if (err || !id) {
      setStatus("✖ " + (err || "unknown error"));
      setBusy(false);
      return;
    }
    try {
      const [s, r] = await Promise.all([getMatch(id), getReplay(id)]);
      setReplay(r);
      setCanVote(!s.voted);
      setStatus("");
      setBusy(false);
    } catch (e) {
      setStatus("✖ " + e.message);
      setBusy(false);
    }
  }

  async function vote(choice) {
    setCanVote(false);
    try {
      const r = await postVote(matchId, choice);
      setReveal(r);
      // Update predict-streak + lifetime accuracy if the user predicted
      // before the match. Accuracy denominator (`total`) is incremented
      // on every predicted vote regardless of outcome; wins tracks the
      // numerator. Current streak resets on a miss but best-streak and
      // accuracy persist forever.
      if (prediction) {
        // The "engine_winner_side" is canvas-side ("a"=green, "b"=blue),
        // matching what the user predicted before the fight.
        const engineWinner = r.engine_winner_side;
        const correct = prediction === engineWinner;
        const nextCur   = correct ? streak.cur + 1 : 0;
        const nextBest  = Math.max(streak.best, nextCur);
        const nextWins  = streak.wins + (correct ? 1 : 0);
        const nextTotal = streak.total + 1;
        const next = { cur: nextCur, best: nextBest,
                       wins: nextWins, total: nextTotal };
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

  return (
    <>
      {/* ---------- Hero ---------- */}
      <OnboardingCard />
      <section className="tagline">
        <h1>
          Two LLMs make real API calls to<br />
          <span className="accent">decide sword-fight moves.</span>
        </h1>
        <p>
          You vote on who fought smarter.
        </p>
        <p style={{ fontSize: 12.5, color: "var(--dim)", fontStyle: "italic",
                    marginTop: 2, maxWidth: 640 }}>
          This is a research tool, not a game — each match is live inference,
          not a scripted battle.{" "}
          <a href="#how-it-works" style={{ color: "var(--gold, #d4b962)",
                                            textDecoration: "underline",
                                            textDecorationStyle: "dotted" }}>
            How it works ↓
          </a>
        </p>
      </section>

      {/* --- Progressive-disclosure explainer --- inline `<details>` so
          normies get one line + can expand for context. Curious readers
          expand; the researcher audience doesn't need the expansion
          because the hero already answered "what am I looking at". */}
      <details id="how-it-works" style={{
        margin: "6px auto 12px", maxWidth: 720, padding: "10px 14px",
        border: "1px solid var(--line)", borderRadius: 6,
        background: "rgba(255,255,255,0.015)", fontSize: 13.5,
      }}>
        <summary style={{ cursor: "pointer", color: "var(--text)",
                          fontWeight: 600, letterSpacing: 0.3, listStyle: "none" }}>
          ▸ What's actually happening here (30-sec read)
        </summary>
        <div style={{ marginTop: 10, color: "var(--text-2)", lineHeight: 1.55 }}>
          <p style={{ marginBottom: 8 }}>
            Two language models each control a stickman in a 2D physics
            simulation. Every 3 seconds of simulated combat, each model
            gets its current state (HP, position, opponent's last move,
            weapon, arena) and picks its next action. They fight until
            one dies or 24 turns pass.
          </p>
          <p style={{ marginBottom: 8 }}>
            You watch, vote blind on who fought smarter, then find out
            which model was which. Per-model Elo tracks it over time,
            segmented by weapon, sharp-zone, control mode, and arena.
          </p>
          <p style={{ marginBottom: 0, color: "var(--dim)" }}>
            <b>Why physics?</b> Text-only benchmarks (MMLU, GPQA,
            Arena-Hard) can't test whether a model plans under physical
            constraints. This does. <b>Why does it take a minute?</b>{" "}
            Each turn is a real LLM API call (~5-15s of inference per model)
            plus 3s of physics. It's slow because it's real, not pre-recorded.
          </p>
        </div>
      </details>

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
            <label className="lbl">Arena</label>
            <div className="zones">
              {ARENAS.map(([a, label]) => (
                <div key={a}
                  role="button" tabIndex={0}
                  aria-pressed={arena === a}
                  className={"zone" + (arena === a ? " on" : "")}
                  title={a === "ice" ? "Slippery floor — fighters slide on impact"
                       : a === "low_gravity" ? "Moon-ish gravity — bigger arcs, slower falls"
                       : "Standard arena"}
                  onClick={() => setArena(a)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setArena(a); } }}>
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

          <ByokPanel />

          <button className="fight-btn" onClick={fight} disabled={busy}>
            {busy ? "⚙ Simulating" : "⚔ Fight"}
          </button>
          {status && (
            <div className="status" aria-live="polite">{status}</div>
          )}
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
                <option value="dagger">dagger</option>
                <option value="spear">spear</option>
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

      {/* ---------- Wait screen (visible while a match is in flight) ----------
          Replaces the old status-dots-only spinner with quips + queue pos +
          live combat ticker + head-to-head + recent duels. Owns its own
          poll loop; when done, calls onWaitReady which hands off to the
          replay panel below. */}
      {busy && matchId && (
        <WaitPanel
          matchId={matchId}
          modelA={modelOf(selA, customA)}
          modelB={modelOf(selB, customB)}
          onReady={onWaitReady}
        />
      )}

      {/* ---------- Replay ---------- */}
      {replay && (
        <div className="panel" style={{ padding: 14 }}>
          <ReplayPlayer replay={replay} />
          {shareUrl && (
            <div className="share" style={{ display: "flex",
                    alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ color: "var(--dim)", fontSize: 13 }}>
                share this duel:
              </span>
              <ShareButton url={shareUrl} />
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

      {/* ---------- Vote ----------
          The vote IS the reward gate. Everything the user actually wants
          to know — which model each fighter was, Elo change, whether
          their prediction was right — stays hidden until they click.
          Copy makes the trade explicit; without this ~70% of visitors
          skip voting because they don't realize the reveal is locked
          behind it (the prediction dopamine already fired, they leave). */}
      {canVote && (
        <div className="panel" style={{ padding: 14, textAlign: "center",
                                        borderColor: "var(--gold, #d4b962)",
                                        borderStyle: "solid" }}>
          <div style={{ fontSize: 11, letterSpacing: 2, fontWeight: 700,
                        color: "var(--gold, #d4b962)", textTransform: "uppercase",
                        marginBottom: 8 }}>
            🔒 Models hidden — vote to reveal
          </div>
          <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12,
                      maxWidth: 520, marginLeft: "auto", marginRight: "auto" }}>
            Voting unlocks: <b style={{ color: "var(--text)" }}>model names</b>,
            {" "}<b style={{ color: "var(--text)" }}>Elo change</b>
            {prediction ? <>, and <b style={{ color: "var(--text)" }}>whether
              your prediction was right</b>.</> : "."}
            {" "}It's blind on purpose — your vote counts most before you know.
          </p>
          <div className="vote-row">
            <button className="vote-a" onClick={() => vote("a")}>
              👑 Fighter A
            </button>
            <button className="vote-draw" onClick={() => vote("draw")}>Draw</button>
            <button className="vote-b" onClick={() => vote("b")}>
              Fighter B 👑
            </button>
          </div>
          {streak.total > 0 && (
            <div style={{ marginTop: 10, fontSize: 12, color: "var(--dim)",
                          letterSpacing: 1 }}>
              your predictions:
              {" "}<b style={{ color: "var(--gold)" }}>{streak.wins}</b>/{streak.total}
              {" "}({Math.round((streak.wins / streak.total) * 100)}%)
              <span style={{ margin: "0 6px", color: "var(--mute)" }}>·</span>
              streak <b style={{ color: "var(--gold)" }}>{streak.cur}</b>
              <span style={{ margin: "0 6px", color: "var(--mute)" }}>·</span>
              best <b style={{ color: "var(--text)" }}>{streak.best}</b>
            </div>
          )}
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
          {reveal.commentary && (
            /* Standalone bordered quote card. Only renders when the
               commentator LLM actually produced text — empty/null
               commentary just shows nothing (per spec). */
            <div style={{
              marginTop: 18, padding: "16px 20px", maxWidth: 720,
              marginLeft: "auto", marginRight: "auto",
              borderRadius: 8, border: "1px solid var(--gold, #d4b962)",
              background: "linear-gradient(135deg, rgba(212,185,98,0.06), rgba(0,0,0,0.25))",
              textAlign: "left",
            }}>
              <div style={{
                fontSize: 11, letterSpacing: 2, color: "var(--gold, #d4b962)",
                textTransform: "uppercase", marginBottom: 10, fontWeight: 700,
                display: "flex", alignItems: "center", gap: 8,
              }}>
                🎙️ Post-fight analysis
              </div>
              <blockquote style={{
                margin: 0, padding: 0,
                fontFamily: "var(--font-display), 'Rajdhani', ui-serif, serif",
                fontStyle: "italic", fontSize: 17, lineHeight: 1.5,
                color: "var(--text)", quotes: "\"“\" \"”\"",
              }}>
                {reveal.commentary}
              </blockquote>
              <div style={{
                marginTop: 10, textAlign: "right",
                fontSize: 12, color: "var(--dim)", letterSpacing: 1,
              }}>
                — the commentator
              </div>
            </div>
          )}
        </div>
      )}

      {/* --- FAQ (bottom of the fight page, below reveal) ---
          Real user questions from the friend-feedback session. Lives on
          the fight page (not a separate /about) so first-time visitors
          who scroll past the vote find answers without a route change.
          A dedicated /about page can come later as the canonical
          explainer to link from HN/Twitter/README. */}
      <FAQ />
    </>
  );
}

const fmtElo = (v) =>
  v === undefined ? "" : `${v >= 0 ? "+" : ""}${v} Elo`;
