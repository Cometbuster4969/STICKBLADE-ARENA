"use client";
import { useEffect, useMemo, useRef, useState } from "react";

/* Wraps the battle-tested vanilla player (public/player.js).
   The player binds to fixed DOM ids; this component owns that DOM.

   Toolbar (review item 10): this is an evaluation tool, so the replay has to
   be inspectable rather than just watchable — play/pause, scrubber with
   event markers, 0.5/1/2/4× speed, previous/next turn, and a KILLCAM jump to
   the decisive hit in slow motion. Turn jumps and the killcam both go through
   the `replay-seek` CustomEvent the player already listens for; only the
   killcam needed a player-side change (it re-arms the slow-mo treatment). */
let playerScriptPromise = null;
function loadPlayerScript() {
  if (typeof window === "undefined") return Promise.reject();
  if (window.initPlayer) return Promise.resolve();
  if (!playerScriptPromise) {
    playerScriptPromise = new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "/player.js";
      s.onload = res;
      s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  return playerScriptPromise;
}

function seek(frame, opts = {}) {
  try {
    window.dispatchEvent(new CustomEvent("replay-seek",
      { detail: { frame, ...opts } }));
  } catch (_) { /* SSR / ancient browsers — no-op */ }
}

export default function ReplayPlayer({ replay }) {
  const holderRef = useRef(null);
  // §10 research overlay state (ours)
  const [debug, setDebug] = useState(false);
  // Turn-marker / decisive-hit navigation (other branch)
  const [markers, setMarkers] = useState(true);

  const total = replay?.frames?.length || 0;

  // Turn start frames come from the thought stream (one entry per turn).
  const turnFrames = useMemo(
    () => (replay?.thoughts || []).map((t) => t.f),
    [replay]
  );
  const [turnIdx, setTurnIdx] = useState(0);

  // Decisive hit: last lethal event, else the biggest hit.
  const killFrame = useMemo(() => {
    const hits = (replay?.events || []).filter((e) => e.k === "hit");
    if (!hits.length) return null;
    const lethal = hits.slice().reverse().find((e) => e.l);
    const target = lethal || hits.slice().sort((a, b) => b.d - a.d)[0];
    return Math.max(0, target.f - 90);      // ~1.5s of preroll
  }, [replay]);

  const hitEvents = useMemo(
    () => (replay?.events || []).filter((e) => e.k === "hit"),
    [replay]
  );

  useEffect(() => {
    let cancelled = false;
    if (!replay) return;
    loadPlayerScript().then(() => {
      if (!cancelled) window.initPlayer(replay);
    });
    return () => {
      cancelled = true;
      if (window.__sbPlayer) window.__sbPlayer.destroy();
    };
  }, [replay]);

  // "d" toggles the research overlay (§10). Skipped while typing in a field
  // — the replay page has a share/link input the user may be editing.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "d" && e.key !== "D") return;
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"
                || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (!window.__sbDebugToggle) return;
      setDebug(window.__sbDebugToggle());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleDebug = () => {
    if (window.__sbDebugToggle) setDebug(window.__sbDebugToggle());
  };

  const jumpTurn = (delta) => {
    if (!turnFrames.length) return;
    const next = Math.min(turnFrames.length - 1, Math.max(0, turnIdx + delta));
    setTurnIdx(next);
    seek(turnFrames[next]);
  };

  return (
    <div ref={holderRef} style={{ width: "100%" }}>
      {/* hidden sinks the player writes match info into */}
      <span id="subtitle" style={{ display: "none" }} />
      <span id="cardResult" style={{ display: "none" }} />
      <canvas id="cv" className="arena" width={1280} height={720}
              aria-label="Combat replay canvas" role="img" />

      <div className="controls">
        <button id="bPlay" aria-label="Play or pause the replay">⏸ Pause</button>
        <button id="bRestart" aria-label="Restart the replay from the beginning">⟲ Restart</button>
        <input
          type="range" id="scrub" min="0" max={Math.max(0, total - 1)}
          defaultValue="0" step="1"
          aria-label="Replay position scrubber"
        />
        <span className="time" id="time">0:00 / 0:00</span>
        <select id="speed" defaultValue="1" aria-label="Replay playback speed">
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
        </select>
        <button id="bMute" aria-pressed="false" title="Toggle sound effects">
          🔊 Sound
        </button>
        {/* §10: research debug overlay — hitboxes, weapon segments, velocity
            vectors, contact points, damage source, frame + current action.
            Off by default (noise for a casual viewer, essential for anyone
            auditing a result). Keyboard shortcut: "d". */}
        <button
          id="bDebug"
          aria-pressed={debug}
          onClick={toggleDebug}
          title="Show hitboxes, weapon segments, velocity vectors, contact points, damage source and the current action (§10). Shortcut: d"
        >
          {debug ? "⚙ Debug: on" : "⚙ Debug"}
        </button>
      </div>

      {/* Event markers: where the hits landed on the timeline. Colour AND
          height both encode severity, so it reads in greyscale too. */}
      {markers && total > 0 && (
        <div className="marker-track" aria-hidden="true">
          {hitEvents.map((e, i) => (
            <span
              key={i}
              className={`marker ${e.l ? "lethal" : e.s ? "sharp" : ""}`}
              style={{ left: `${(e.f / total) * 100}%` }}
              title={`hit · ${e.part} · ${e.d} dmg${e.l ? " · lethal" : ""}`}
            />
          ))}
        </div>
      )}

      <div className="replay-tools">
        <button className="btn btn-sm" onClick={() => jumpTurn(-1)}
                disabled={turnIdx === 0} aria-label="Jump to previous turn">
          ⏮ Prev turn
        </button>
        <button className="btn btn-sm" onClick={() => jumpTurn(1)}
                disabled={turnIdx >= turnFrames.length - 1}
                aria-label="Jump to next turn">
          Next turn ⏭
        </button>
        <span className="fight-summary" aria-live="polite">
          turn <b>{turnFrames.length ? turnIdx + 1 : 0}</b> / {turnFrames.length}
        </span>
        {killFrame != null && (
          <button className="btn btn-sm btn-primary"
                  onClick={() => seek(killFrame, { killcam: true })}
                  aria-label="Jump to the decisive hit in slow motion">
            🎯 Killcam
          </button>
        )}
        <button className="btn btn-sm btn-ghost"
                aria-pressed={markers}
                onClick={() => setMarkers((v) => !v)}>
          {markers ? "Hide event markers" : "Show event markers"}
        </button>
        <span className="fight-summary" style={{ marginLeft: "auto" }}>
          space = play/pause · ←/→ = step a frame
        </span>
      </div>
    </div>
  );
}
