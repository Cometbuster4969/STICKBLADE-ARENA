"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReplayPlayer from "@/components/ReplayPlayer";
import TurnTranscript from "@/components/TurnTranscript";
import { getMatch, getReplay, postVote } from "@/lib/api";

function ReplayInner() {
  const params = useSearchParams();
  const id = params.get("id");
  const [replay, setReplay] = useState(null);
  const [match, setMatch] = useState(null);
  const [reveal, setReveal] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!id) { setErr("no replay id in URL"); return; }
    Promise.all([getReplay(id), getMatch(id)])
      .then(([r, m]) => { setReplay(r); setMatch(m); })
      .catch((e) => setErr(e.message));
  }, [id]);

  async function vote(choice) {
    try { setReveal(await postVote(id, choice)); setMatch({ ...match, voted: true }); }
    catch (e) { setErr(e.message); }
  }

  if (err) return <div className="status">✖ {err}</div>;
  if (!replay) return <div className="status">loading replay…</div>;
  const canVote = match && !match.voted;
  return (
    <div style={{ width: "100%" }}>
      <ReplayPlayer replay={replay} />
      {/* Tier-A UX fix: persistent turn-by-turn transcript below canvas.
          Data source: replay.thoughts + replay.events (already fetched
          via getReplay above). Blind-safe; matches wait-panel ticker. */}
      <TurnTranscript replay={replay} />
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
      {(reveal || (match?.voted && match.model_a)) && (() => {
        // Prefer the fresh /api/vote reveal payload; fall back to
        // /api/match on refresh-of-already-voted-link.
        const src = reveal || match;
        // CRITICAL: canvas_a/b_model reflects who actually rendered as
        // Fighter A (green) vs Fighter B (blue) after the random flip.
        // model_a/model_b is only the user's original Slot 1/2 pick order
        // and can silently swap identities. Always prefer canvas_*.
        const aModel = src.canvas_a_model || src.model_a;
        const bModel = src.canvas_b_model || src.model_b;
        const names = src.names || {};
        const name = (m) => names[m] || m;
        const winner = src.engine_winner_side || src.winner_side;
        const method = src.method;
        return (
          <div className="panel reveal">
            🎭 Fighter A was <b>{name(aModel)}</b>
            {" · "}Fighter B was <b>{name(bModel)}</b>
            {winner && method && (
              <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-2)" }}>
                engine result: {winner === "draw"
                  ? "draw"
                  : `Fighter ${winner.toUpperCase()} won`} by {method}
                {(method === "points" || method === "incomplete_points") && (
                  <span style={{ color: "var(--dim)", fontSize: 12, marginLeft: 4 }}>
                    (time-cap reached, higher HP wins — no knockout)
                  </span>
                )}
                {(method === "incomplete_draw" || method === "timeout_draw") && (
                  <span style={{ color: "var(--dim)", fontSize: 12, marginLeft: 4 }}>
                    (time-cap reached, HP roughly equal — no clear winner)
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

export default function ReplayPage() {
  return (
    <Suspense fallback={<div className="status">loading…</div>}>
      <ReplayInner />
    </Suspense>
  );
}
