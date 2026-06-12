"use client";
import { useEffect, useRef } from "react";

/* Wraps the battle-tested vanilla player (public/player.js).
   The player binds to fixed DOM ids; this component owns that DOM. */
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

export default function ReplayPlayer({ replay }) {
  const holderRef = useRef(null);

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

  return (
    <div ref={holderRef} style={{ width: "100%" }}>
      {/* hidden sinks the player writes match info into */}
      <span id="subtitle" style={{ display: "none" }} />
      <span id="cardResult" style={{ display: "none" }} />
      <canvas id="cv" className="arena" width={1280} height={720} />
      <div className="controls">
        <button id="bPlay">⏸ Pause</button>
        <button id="bRestart">⟲ Restart</button>
        <input type="range" id="scrub" min="0" max="100" defaultValue="0" step="1" />
        <span className="time" id="time">0:00 / 0:00</span>
        <select id="speed" defaultValue="1">
          <option value="0.25">0.25×</option>
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
        </select>
      </div>
    </div>
  );
}
