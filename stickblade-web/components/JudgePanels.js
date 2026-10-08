"use client";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "@/lib/motion";
import ShareButton from "@/components/ShareButton";

/* Judge stage: optional prediction -> blind vote -> reveal (review items 11-15).

   Three separate questions that used to share one control and one vocabulary:
     1. PREDICT (optional, engagement only): "who will win?" — a physics
        question with a right answer. Skippable, and skipping costs nothing.
     2. VOTE (the research data): "who made the better decisions?" — a
        judgement question. This is what feeds Human-Voted Elo.
     3. REVEAL: who they actually were, plus everything the vote unlocked.

   Blind discipline: nothing in the prediction or vote stage names a model,
   a provider, or a canvas colour beyond the A/B labels the replay already
   uses. The reveal is the first place a model name appears. */

const SHARE_ORIGIN = typeof window !== "undefined" ? window.location.origin : "";

export function PredictPanel({ prediction, onPredict, streak }) {
  if (prediction) return null;
  return (
    <div className="panel" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="panel-title"><span className="tick" /> Optional · predict the winner</span>
        <span style={{ color: "var(--dim)", fontSize: 12, letterSpacing: 1 }}>
          streak <b style={{ color: "var(--gold)" }}>{streak.cur}</b>
          <span style={{ margin: "0 6px", color: "var(--mute)" }}>·</span>
          best <b>{streak.best}</b>
        </span>
      </div>
      <p className="vote-sub" style={{ margin: "8px auto 12px" }}>
        Who do you predict will <b>win the fight</b>? This is a physics
        question, separate from the vote below — and entirely optional.
      </p>
      <div className="vote-row">
        {[["a", "vote-a", "Fighter A wins"],
          ["draw", "vote-draw", "Draw"],
          ["b", "vote-b", "Fighter B wins"]].map(([side, cls, label]) => (
          <button key={side} className={cls} onClick={() => onPredict(side)}
            data-press style={{ "--hy": "-3px", "--ph": "1.01", "--pt": "0.97" }}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function VotePanel({ onVote, predictionLocked, integrityNote }) {
  return (
    <div className="panel" style={{ padding: 18, borderColor: "var(--gold)",
                                    borderStyle: "solid" }}>
      <div style={{ fontSize: 12, letterSpacing: 0.3, fontWeight: 700,
                    color: "var(--gold)",
                    textAlign: "center", marginBottom: 10 }}>
        🔒 Blind vote · models hidden until you answer
      </div>
      <div className="vote-q">Who made the better decisions?</div>
      <p className="vote-sub" style={{ marginTop: 8 }}>
        Not who won — who <b style={{ color: "var(--text)" }}>fought smarter</b>.
        A fighter can lose on physics and still out-think the other one.
        {predictionLocked && " Your prediction above is locked in; this vote is a separate question."}
      </p>
      {integrityNote && (
        <p className="vote-sub" style={{ marginTop: 8, color: "var(--gold)" }}>
          {integrityNote}
        </p>
      )}
      <div className="vote-row" style={{ marginTop: 14 }}>
        <button className="vote-a" onClick={() => onVote("a")}>
          Fighter A played better
        </button>
        <button className="vote-draw" onClick={() => onVote("draw")}>
          Too close to call
        </button>
        <button className="vote-b" onClick={() => onVote("b")}>
          Fighter B played better
        </button>
      </div>
      <p className="vote-sub" style={{ marginTop: 12, fontSize: 12 }}>
        Voting unlocks model names, Elo change and the decisive event.
        Ties count: they are recorded as draws, not discarded.
      </p>
    </div>
  );
}

export function RevealPanel({ result, replay, voteChoice, prediction,
                              predictionCorrect, streak, matchId }) {
  if (!result) return null;
  const nameA = result.names?.[result.canvas_a_model] || result.canvas_a_model;
  const nameB = result.names?.[result.canvas_b_model] || result.canvas_b_model;
  const eloA = result.elo_change?.[result.canvas_a_model];
  const eloB = result.elo_change?.[result.canvas_b_model];
  const winnerSide = result.engine_winner_side;      // "a" | "b" | "draw"
  const winnerName = winnerSide === "a" ? nameA : winnerSide === "b" ? nameB : null;
  const votedSide = voteChoice === "draw" ? null : voteChoice;
  const disagreement = winnerSide !== "draw" && votedSide && votedSide !== winnerSide;

  // Decisive event = last lethal hit, else the biggest single hit.
  const events = replay?.events || [];
  const decisive = events.slice().reverse().find((e) => e.k === "hit" && e.l)
    || events.slice().reverse().find((e) => e.k === "hit");
  const integrity = replay?.meta?.evaluation_integrity
    || (replay?.meta?.fallback_turns != null
      ? { fully_llm_controlled: !replay.meta.fallback_turns,
          fallback_turns_a: 0, fallback_turns_b: 0,
          total_turns: replay.meta.total_turns }
      : null);
  const fallbackTurns = (integrity?.fallback_turns_a || 0) + (integrity?.fallback_turns_b || 0);

  const fmtElo = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v}`);

  return (
    <div
      className="panel reveal enter-scale"
      style={{ position: "relative", overflow: "hidden" }}
    >
      {/* One-shot flash as the identities land — the payoff of a blind vote. */}
      <RevealFlash />
      <span className="panel-title gold"><span className="tick" /> Reveal — who they were</span>

      {prediction && (
        <div className="disagree"
             style={{ borderLeftColor: predictionCorrect ? "var(--green)" : "var(--red)" }}>
          {predictionCorrect ? "🎯 Prediction correct." : "❌ Prediction missed."}{" "}
          You predicted{" "}
          <b>{prediction === "draw" ? "a draw" : `Fighter ${prediction.toUpperCase()}`}</b>
          {streak.total > 0 && (
            <> — lifetime {streak.wins}/{streak.total}
              {" "}({Math.round((streak.wins / streak.total) * 100)}%),
              streak {streak.cur}</>
          )}
        </div>
      )}

      {result.commentary && (
        <div style={{ padding: "10px 14px", borderRadius: 6,
                      background: "rgba(255, 197, 71, 0.07)",
                      border: "1px dashed var(--gold)", fontSize: 13, lineHeight: 1.55 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5,
                        color: "var(--gold)", marginBottom: 4 }}>
            AI commentator
          </div>
          “{result.commentary}”
        </div>
      )}

      <div className="reveal-grid">
        <div className="reveal-cell reveal-from-left"
          style={{ "--ed": "0.18s", position: "relative" }}
        >
          <div className="side" style={{ color: "var(--green)" }}>Fighter A was</div>
          <div className="who"><ScrambleText text={nameA} delay={0.35} /></div>
          <div style={{ fontSize: 12, color: "var(--dim)", marginTop: 6 }}>
            Human-Voted Elo <EloDelta value={eloA} />
            {winnerSide === "a" && <b style={{ color: "var(--gold)" }}> · won the fight</b>}
            {votedSide === "a" && <b style={{ color: "var(--green)" }}> · your vote</b>}
          </div>
        </div>
        <div className="reveal-cell reveal-from-right"
          style={{ "--ed": "0.26s", position: "relative" }}
        >
          <div className="side" style={{ color: "var(--blue)" }}>Fighter B was</div>
          <div className="who"><ScrambleText text={nameB} delay={0.5} /></div>
          <div style={{ fontSize: 12, color: "var(--dim)", marginTop: 6 }}>
            Human-Voted Elo <EloDelta value={eloB} />
            {winnerSide === "b" && <b style={{ color: "var(--gold)" }}> · won the fight</b>}
            {votedSide === "b" && <b style={{ color: "var(--blue)" }}> · your vote</b>}
          </div>
        </div>
      </div>

      {disagreement && (
        <div className="disagree">
          <b>Fighter {votedSide.toUpperCase()}</b> lost the fight on physics but
          earned your vote for better tactics. That disagreement is the
          interesting signal — Human-Voted Elo rates decisions, not damage.
        </div>
      )}

      <div className="reveal-rows enter-up" style={{ "--ed": "0.5s" }}>
        <div>
          Physical winner:{" "}
          <b>{winnerSide == null ? "Unknown" : winnerSide === "draw" ? "Draw"
            : `Fighter ${String(winnerSide).toUpperCase()}${winnerName ? ` (${winnerName})` : ""}`}</b>
          {" "}· method <b>{result.method}</b>
        </div>
        {voteChoice != null && (
          <div>
            Your vote:{" "}
            <b>{voteChoice === "draw" ? "Too close to call"
              : `Fighter ${String(voteChoice).toUpperCase()} played better`}</b>
          </div>
        )}
        {decisive && (
          <div>
            Decisive event:{" "}
            <b>
              T{String(replay?.thoughts?.filter((t) => t.f <= decisive.f).length || 0).padStart(2, "0")}
              {" "}{decisive.by === replay?.meta?.p1?.name ? "A" : "B"}→{decisive.part}
              {" "}{decisive.d} dmg{decisive.l ? " · LETHAL" : decisive.s ? " · sharp" : ""}
            </b>
          </div>
        )}
        <div>
          Match integrity:{" "}
          <b>{integrity?.fully_llm_controlled ? "fully model-controlled"
            : `${fallbackTurns}/${integrity?.total_turns || "?"} turns used the scripted fallback`}</b>
        </div>
        <div style={{ color: "var(--mute)", fontSize: 11.5 }}>
          Human-Voted Elo reflects human judgements of tactical decision
          quality, not only match wins.
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <ShareButton
          url={`${SHARE_ORIGIN}/replay?id=${matchId}`}
          label="📋 Share this replay"
        />
        <a className="btn btn-sm btn-ghost" href="/leaderboard"
           style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
          See the leaderboard
        </a>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Reveal-only motion helpers. The flash is a CSS keyframe (neutralised by
 * the reduced-motion kill); the scramble and count-up check useReducedMotion
 * so their rAF loops never start.
 * ------------------------------------------------------------------------ */

/** Brief white-out along the panel edge the moment identities appear. */
function RevealFlash() {
  const reduce = useReducedMotion();
  if (reduce) return null;
  return (
    <span
      aria-hidden="true"
      className="flash-x"
      style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        transformOrigin: "0%", pointerEvents: "none",
        background: "linear-gradient(90deg, var(--green), var(--gold), var(--blue))",
      }}
    />
  );
}

const SCRAMBLE_POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_·";

/**
 * Decodes a model id into its final text. A cheap suspense beat that makes
 * the reveal feel like a reveal; the finished string is always the real one,
 * and it never affects what is stored or rated.
 */
function ScrambleText({ text, delay = 0 }) {
  const reduce = useReducedMotion();
  const [out, setOut] = useState(reduce ? text : "");

  useEffect(() => {
    if (reduce || !text) { setOut(text); return; }
    let frame = 0;
    let raf;
    let start;
    const total = text.length;
    const step = (t) => {
      if (start == null) start = t;
      const elapsed = t - start - delay * 1000;
      if (elapsed < 0) { raf = requestAnimationFrame(step); return; }
      const settled = Math.min(total, Math.floor(elapsed / 26));
      let s = text.slice(0, settled);
      for (let i = settled; i < total; i++) {
        s += text[i] === " " || text[i] === "/" || text[i] === ":"
          ? text[i]
          : SCRAMBLE_POOL[(Math.random() * SCRAMBLE_POOL.length) | 0];
      }
      setOut(s);
      frame = settled;
      if (frame < total) raf = requestAnimationFrame(step);
      else setOut(text);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [text, delay, reduce]);

  return <span aria-label={text}>{out || text}</span>;
}

/** Elo delta that ticks from 0 to its value — up green, down red. */
function EloDelta({ value }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(0);
  const raf = useRef(0);

  useEffect(() => {
    cancelAnimationFrame(raf.current);
    if (value == null) { setShown(0); return undefined; }
    if (reduce) { setShown(value); return undefined; }
    const start = performance.now();
    const dur = 900;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(value * eased));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [value, reduce]);

  if (value == null) return <>—</>;
  const sign = value >= 0 ? "+" : "";
  const color = value >= 0 ? "var(--green)" : "var(--red)";
  return (
    <b style={{ color, fontVariantNumeric: "tabular-nums" }}>
      {sign}{shown}
    </b>
  );
}
