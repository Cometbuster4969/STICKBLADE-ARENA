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
      {(reveal || (match?.voted && match.model_a)) && (
        <div className="panel reveal">
          🎭 {reveal
            ? <>Fighter A was <b>{reveal.names[reveal.model_a]}</b> · Fighter B
                was <b>{reveal.names[reveal.model_b]}</b></>
            : <>Fighter A was <b>{match.model_a}</b> · Fighter B was{" "}
                <b>{match.model_b}</b></>}
        </div>
      )}
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
