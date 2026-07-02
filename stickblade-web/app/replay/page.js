"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReplayPlayer from "@/components/ReplayPlayer";
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
        return (
          <div className="panel reveal">
            🎭 Fighter A was <b>{name(aModel)}</b>
            {" · "}Fighter B was <b>{name(bModel)}</b>
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
