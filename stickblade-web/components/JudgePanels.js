"use client";
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
        <button className="vote-a" onClick={() => onPredict("a")}>Fighter A wins</button>
        <button className="vote-draw" onClick={() => onPredict("draw")}>Draw</button>
        <button className="vote-b" onClick={() => onPredict("b")}>Fighter B wins</button>
      </div>
    </div>
  );
}

export function VotePanel({ onVote, predictionLocked, integrityNote }) {
  return (
    <div className="panel" style={{ padding: 18, borderColor: "var(--gold)",
                                    borderStyle: "solid" }}>
      <div style={{ fontSize: 11, letterSpacing: 2, fontWeight: 700,
                    color: "var(--gold)", textTransform: "uppercase",
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
    <div className="panel reveal">
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
                        color: "var(--gold)", textTransform: "uppercase", marginBottom: 4 }}>
            AI commentator
          </div>
          “{result.commentary}”
        </div>
      )}

      <div className="reveal-grid">
        <div className="reveal-cell">
          <div className="side" style={{ color: "var(--green)" }}>Fighter A was</div>
          <div className="who">{nameA}</div>
          <div style={{ fontSize: 12, color: "var(--dim)", marginTop: 6 }}>
            Human-Voted Elo {fmtElo(eloA)}
            {winnerSide === "a" && <b style={{ color: "var(--gold)" }}> · won the fight</b>}
            {votedSide === "a" && <b style={{ color: "var(--green)" }}> · your vote</b>}
          </div>
        </div>
        <div className="reveal-cell">
          <div className="side" style={{ color: "var(--blue)" }}>Fighter B was</div>
          <div className="who">{nameB}</div>
          <div style={{ fontSize: 12, color: "var(--dim)", marginTop: 6 }}>
            Human-Voted Elo {fmtElo(eloB)}
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

      <div className="reveal-rows">
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
