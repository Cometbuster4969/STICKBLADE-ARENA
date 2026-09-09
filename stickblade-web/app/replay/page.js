"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReplayPlayer from "@/components/ReplayPlayer";
import TurnTranscript from "@/components/TurnTranscript";
import { PredictPanel, VotePanel, RevealPanel } from "@/components/JudgePanels";
import { getMatch, getReplay, postVote } from "@/lib/api";
import SiteNav, { SiteFooter } from "@/components/SiteNav";

/* Replay + judge stage (review items 11-15, 22).

   Order of operations, and why:
     1. Watch. The replay, the transcript, and the technical state carry no
        identity information.
     2. Predict (optional). "Who will win?" — a physics question. It is
        recorded locally, locked before the vote, and is NEVER sent to the
        server, so it cannot contaminate the research vote.
     3. Vote. "Who made the better decisions?" — this is the only thing that
        writes to the leaderboard. Models stay anonymous until it is cast.
     4. Reveal. Names, Human-Voted Elo delta, integrity, fallback count and
        the decisive event.

   The old page had one inline vote row and a reveal that showed only names
   + engine result. There was no prediction, no disagreement callout, no Elo
   delta, and no integrity disclosure. */

const STREAK_KEY = "sb.predictStreak.v1";
const EMPTY_STREAK = { cur: 0, best: 0, total: 0, wins: 0 };

function loadStreak() {
  if (typeof window === "undefined") return EMPTY_STREAK;
  try {
    return { ...EMPTY_STREAK, ...JSON.parse(localStorage.getItem(STREAK_KEY) || "{}") };
  } catch { return EMPTY_STREAK; }
}
function saveStreak(s) {
  try { localStorage.setItem(STREAK_KEY, JSON.stringify(s)); } catch { /* private mode */ }
}

function ReplayInner() {
  const params = useSearchParams();
  const id = params.get("id");
  const [replay, setReplay] = useState(null);
  const [match, setMatch] = useState(null);
  const [reveal, setReveal] = useState(null);
  const [voteChoice, setVoteChoice] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [predictionCorrect, setPredictionCorrect] = useState(null);
  const [streak, setStreak] = useState(EMPTY_STREAK);
  const [voting, setVoting] = useState(false);
  const [err, setErr] = useState("");
  const voteRef = useRef(null);

  useEffect(() => {
    if (!id) { setErr("no replay id in URL — open a replay from a duel or from Recent duels"); return; }
    setStreak(loadStreak());
    Promise.all([getReplay(id), getMatch(id)])
      .then(([r, m]) => { setReplay(r); setMatch(m); })
      .catch((e) => setErr(e.message));
  }, [id]);

  // Deep link from Recent duels ("Vote") lands the user on the vote panel.
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#vote") {
      const t = setTimeout(() => voteRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 400);
      return () => clearTimeout(t);
    }
  }, [replay, match]);

  const integrity = replay?.meta?.evaluation_integrity || match?.evaluation_integrity;
  const fallbackTurns = (integrity?.fallback_turns_a || 0) + (integrity?.fallback_turns_b || 0);
  const integrityNote = useMemo(() => {
    if (!integrity) return "";
    if (integrity.fully_llm_controlled) return "";
    return `⚠ ${fallbackTurns} of ${integrity.total_turns || "?"} turns were resolved by the scripted fallback rather than by the models. Judge what you saw; the rating knows.`;
  }, [integrity, fallbackTurns]);

  const canVote = !!(match && !match.voted);

  function predict(side) {
    setPrediction(side);
  }

  async function vote(choice) {
    if (voting || !canVote) return;             // duplicate-submit guard
    setVoting(true);
    setErr("");
    try {
      const res = await postVote(id, choice);
      setVoteChoice(choice);
      setReveal(res);
      setMatch({ ...match, voted: true });
      // Grade the optional prediction locally — never sent to the API.
      if (prediction) {
        const winner = res.engine_winner_side;
        const correct = winner === prediction
          || (prediction === "draw" && winner === "draw");
        setPredictionCorrect(correct);
        const next = {
          total: streak.total + 1,
          wins: streak.wins + (correct ? 1 : 0),
          cur: correct ? streak.cur + 1 : 0,
          best: Math.max(streak.best, correct ? streak.cur + 1 : streak.best),
        };
        setStreak(next);
        saveStreak(next);
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setVoting(false);
    }
  }

  if (err && !replay) {
    return (
      <div className="panel empty">
        <div className="empty-t">This replay could not be loaded.</div>
        <p style={{ color: "var(--dim)", fontSize: 13, margin: 0 }}>{err}</p>
        <a className="btn btn-sm" href="/" style={{ textDecoration: "none" }}>
          Start a duel
        </a>
      </div>
    );
  }
  if (!replay) return <div className="status" role="status">Loading replay…</div>;

  // Already voted (e.g. reopening a shared link): reconstruct a reveal from
  // /api/match. It carries canvas_*_model + names, so identities are still
  // correct after the random canvas flip. elo_change/commentary are absent
  // and RevealPanel renders "—" for them.
  const revealSource = reveal
    || (match?.voted && match.model_a
      ? { ...match, elo_change: null, commentary: null }
      : null);

  return (
    <div style={{ width: "100%" }}>
      {err && <div className="status" role="alert">✖ {err}</div>}

      <ReplayPlayer replay={replay} />
      {/* §10: the debug overlay is the difference between "trust us" and
          "check for yourself". Hidden by default so it never gets in a
          casual viewer's way, but one click (or the "d" key) away. */}
      <p style={{ color: "var(--dim)", fontSize: 11, margin: "6px 2px 0",
                  lineHeight: 1.6 }}>
        Press <b style={{ color: "var(--text-2)" }}>⚙ Debug</b> (or
        <b style={{ color: "var(--text-2)" }}> d</b>) to overlay the
        physics: hitboxes, weapon segments with the sharp zone highlighted,
        velocity vectors, contact points with damage and body part, and the
        frame / turn / action in force. Everything shown is replayed from the
        recorded frame data — nothing is re-simulated, so what you see is
        what the engine did.
      </p>

      {/* Turn-by-turn transcript: the same events the ticker showed live.
          Data source: replay.thoughts + replay.events. Blind-safe. */}
      <TurnTranscript replay={replay} />

      <div ref={voteRef} style={{ scrollMarginTop: 80 }}>
        {canVote && !prediction && (
          <PredictPanel prediction={null} onPredict={predict} streak={streak} />
        )}
        {canVote && prediction && (
          <div className="panel" style={{ padding: 14 }}>
            <div className="panel-title"><span className="tick" /> Prediction locked</div>
            <p className="vote-sub" style={{ margin: "8px 0 0" }}>
              You called <b>Fighter {prediction === "draw" ? "draw" : prediction.toUpperCase()}</b>.
              Graded after you vote — prediction accuracy is kept on your
              device only and never touches the Elo maths.
            </p>
          </div>
        )}

        {canVote && (
          <VotePanel onVote={vote} predictionLocked={!!prediction}
                     integrityNote={integrityNote} />
        )}
        {canVote && voting && (
          <div className="status" role="status">Recording your vote…</div>
        )}

        <RevealPanel
          result={revealSource}
          replay={replay}
          voteChoice={voteChoice}
          prediction={revealSource ? prediction : null}
          predictionCorrect={predictionCorrect}
          streak={streak}
          matchId={id}
        />

        {revealSource && !voteChoice && (
          <p style={{ color: "var(--dim)", fontSize: 12.5, marginTop: 10 }}>
            This match was already voted on, so the models are no longer
            anonymous. Elo deltas are only shown for the vote you just cast.
          </p>
        )}
      </div>
    </div>
  );
}

export default function ReplayPage() {
  return (
    <>
      <SiteNav />
    <Suspense fallback={<div className="status" role="status">Loading…</div>}>
      <ReplayInner />
    </Suspense>
      <SiteFooter />
    </>
  );
}
