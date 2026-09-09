"use client";
import { useEffect, useState } from "react";
import ReplayPlayer from "@/components/ReplayPlayer";
import { getDemoReplay } from "@/lib/api";

/**
 * "Watch a sample fight" — the 20-second explainer (action-plan §3).
 *
 * A new visitor has to understand models, weapons, sharp zones, arenas,
 * control modes, blind voting and Elo before the setup panel makes sense.
 * Watching one fight with the five beats called out beats any amount of
 * copy, and it works offline: the replay is a committed asset rendered by
 * the same player as a live match.
 */
const STEPS = [
  ["1", "Two models decide", "Each turn both fighters get the same physics "
    + "state and independently choose an action — real API calls, not a "
    + "scripted animation."],
  ["2", "Physics executes it", "Pymunk simulates 3 seconds of ragdoll "
    + "motion: reach, timing, footwork and weapon geometry decide whether "
    + "the swing lands."],
  ["3", "Sharp zones set damage", "Only the zones you sharpened cut deep. "
    + "Tip, edge, pommel — the same swing can scratch or kill."],
  ["4", "You vote blind", "Model identities stay hidden until after you "
    + "vote, so brand bias can't tilt the rating."],
  ["5", "The reveal updates ratings", "Elo moves on the tactical vote, and "
    + "every match ships with its seed, latency and fallback record."],
];

export default function SampleFight({ open, onClose }) {
  const [replay, setReplay] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || replay) return;
    let alive = true;
    setLoading(true);
    getDemoReplay()
      .then((r) => {
        if (!alive) return;
        if (r) setReplay(r);
        else setErr("Sample fight not available offline.");
      })
      .catch((e) => alive && setErr(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [open, replay]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true"
         aria-label="Sample fight" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "center", gap: 10, marginBottom: 10 }}>
          <span className="panel-title">
            <span className="tick" /> Sample fight — how a match works
          </span>
          <button className="btn-secondary" onClick={onClose}
                  aria-label="Close sample fight">
            ✕ Close
          </button>
        </div>

        <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12,
                    maxWidth: "70ch" }}>
          This is a real engine replay recorded offline with scripted
          fighters — no API key, no waiting. Five beats to look for:
        </p>

        <ol style={{ listStyle: "none", display: "grid", gap: 8,
                     gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
                     marginBottom: 14, padding: 0 }}>
          {STEPS.map(([n, title, body]) => (
            <li key={n} style={{ padding: "10px 12px", borderRadius: 8,
                                 border: "1px solid var(--line)",
                                 background: "var(--bg-3)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ width: 20, height: 20, borderRadius: "50%",
                               display: "inline-flex", alignItems: "center",
                               justifyContent: "center", fontSize: 11,
                               fontWeight: 800, background: "var(--red)",
                               color: "#0b0d18" }}>{n}</span>
                <b style={{ fontSize: 13 }}>{title}</b>
              </div>
              <p style={{ marginTop: 6, fontSize: 12, color: "var(--dim)",
                          lineHeight: 1.55 }}>{body}</p>
            </li>
          ))}
        </ol>

        {loading && <p style={{ color: "var(--dim)" }}>Loading sample fight…</p>}
        {err && (
          <p style={{ color: "var(--gold)", fontSize: 13 }}>
            {err} You can still start a match — mock fighters run instantly.
          </p>
        )}
        {replay && <ReplayPlayer replay={replay} />}

        <div style={{ marginTop: 12, display: "flex", gap: 10,
                      justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button className="btn-secondary" onClick={onClose}>
            Got it — start a match
          </button>
        </div>
      </div>
    </div>
  );
}
