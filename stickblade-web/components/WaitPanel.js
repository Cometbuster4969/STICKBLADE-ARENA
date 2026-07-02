"use client";
import { useEffect, useRef, useState } from "react";
import { getMatch, getHeadToHead, getRecent } from "@/lib/api";

/**
 * Wait-screen for an in-progress match. Replaces the old "⚙ Simulating…"
 * status string with the actual fight-in-progress data.
 *
 * Four panes, all reading data that already exists on the backend:
 *
 *   1. Pre-fight quips  (from /api/match/{mid}.live.quips)
 *      The trash-talk resolves ~5-15s in — MUCH earlier than the full
 *      match. Shows the moment it lands so the user doesn't stare at
 *      dots while the physics loop grinds through 24 turns.
 *
 *   2. Queue position  (from /api/match/{mid}.live.queue_pos)
 *      "3 fights ahead of you" answers "is this stuck?" anxiety.
 *
 *   3. Live combat ticker  (from /api/match/{mid}.live.log)
 *      Spoiler-safe turn-by-turn: "Turn 6 — sharp hit to torso, 14 dmg".
 *      Reads canvas-side keys (a/b), never model names, so no reveal
 *      leaks before the vote. Scrolls in as turns finalize server-side.
 *
 *   4. Head-to-head card  (from /api/head_to_head)
 *      Prior duels between THIS pair of models. User picked both so
 *      no blind risk. Hides when total === 0.
 *
 * Ownership: `matchId` and `modelA`/`modelB` are passed by the parent
 * (page.js). This component polls /api/match every 1.5s while `busy`
 * and stops as soon as status becomes "done" or the parent unmounts it.
 * `onReady(replay|null)` is the callback fired when the match is ready
 * for the parent to hand off to <ReplayPlayer>.
 */
export default function WaitPanel({ matchId, modelA, modelB, onReady }) {
  const [live, setLive] = useState(null);
  const [status, setStatus] = useState("queued");
  const [h2h, setH2h] = useState(null);
  const [recent, setRecent] = useState([]);
  const pollRef = useRef(null);
  const readyFiredRef = useRef(false);

  // ------- Head-to-head: one-shot fetch when the match starts -------
  useEffect(() => {
    if (!modelA || !modelB) return;
    getHeadToHead(modelA, modelB).then(setH2h).catch(() => setH2h(null));
  }, [modelA, modelB]);

  // ------- Recent duels: one-shot; refresh every 20s while waiting --
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getRecent().then((r) => { if (!cancelled) setRecent(r.slice(0, 8)); })
                 .catch(() => {});
    };
    tick();
    const id = setInterval(tick, 20000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ------- Poll match status every 1.5s, mirror old poll() semantics --
  useEffect(() => {
    if (!matchId) return;
    let cancelled = false;
    const tick = () => {
      pollRef.current = setTimeout(async () => {
        if (cancelled) return;
        try {
          const s = await getMatch(matchId);
          if (cancelled) return;
          setStatus(s.status);
          if (s.live) setLive(s.live);
          if (s.status === "done") {
            if (!readyFiredRef.current) {
              readyFiredRef.current = true;
              onReady?.(matchId);
            }
            return;
          }
          if (s.status === "error") {
            onReady?.(null, s.error || "simulation error");
            return;
          }
          tick();
        } catch (e) {
          onReady?.(null, e.message);
        }
      }, 1500);
    };
    tick();
    return () => { cancelled = true; clearTimeout(pollRef.current); };
  }, [matchId, onReady]);

  // ------------- render -------------
  const quips = live?.quips;
  const log   = live?.log || [];
  const qpos  = live?.queue_pos;
  const turn  = live?.turn || 0;

  return (
    <div className="panel" style={{ padding: 16 }}>
      <div className="panel-head" style={{ marginBottom: 10 }}>
        <span className="panel-title">
          <span className="tick" /> {status === "queued" ? "Queued" : "Simulating"}
          {status === "running" && turn > 0 && (
            <span style={{ color: "var(--dim)", marginLeft: 8, fontSize: 12 }}>
              · turn {turn}
            </span>
          )}
        </span>
        {status === "queued" && qpos != null && qpos > 0 && (
          <span style={{ color: "var(--gold)", fontSize: 13, letterSpacing: 1 }}>
            {qpos} {qpos === 1 ? "fight" : "fights"} ahead of you
          </span>
        )}
      </div>

      {/* --- Trash-talk quips (visible as soon as they resolve, ~5-15s) --- */}
      {quips && (quips.a || quips.b) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10,
                      marginBottom: 12 }}>
          <QuipCard side="a" text={quips.a} />
          <QuipCard side="b" text={quips.b} />
        </div>
      )}

      {/* --- Live combat ticker (spoiler-safe: canvas keys, no model names) --- */}
      <CombatTicker log={log} status={status} />

      {/* --- Head-to-head card (only if prior duels exist) --- */}
      {h2h && h2h.total > 0 && (
        <div style={{ marginTop: 14, padding: 12, borderTop: "1px dashed var(--line)" }}>
          <div style={{ fontSize: 11, letterSpacing: 2, color: "var(--gold)",
                        textTransform: "uppercase", fontWeight: 700, marginBottom: 8 }}>
            📜 Previous duels · this exact matchup
          </div>
          <div style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "center", flexWrap: "wrap", gap: 8, fontSize: 14 }}>
            <span>
              <b>{h2h.a_name}</b> <span style={{ color: "var(--green)" }}>{h2h.a_wins}W</span>
              {" · "}
              <span style={{ color: "var(--red-2)" }}>{h2h.b_wins}W</span> <b>{h2h.b_name}</b>
              {h2h.draws > 0 && <span style={{ color: "var(--dim)" }}> · {h2h.draws}D</span>}
            </span>
            <span style={{ color: "var(--dim)", fontSize: 12 }}>
              {h2h.total} {h2h.total === 1 ? "duel" : "duels"} · avg {h2h.avg_turns} turns
            </span>
          </div>
        </div>
      )}

      {/* --- Recent-duels ticker (something to click while waiting) --- */}
      {recent.length > 0 && (
        <div style={{ marginTop: 14, padding: 12, borderTop: "1px dashed var(--line)" }}>
          <div style={{ fontSize: 11, letterSpacing: 2, color: "var(--gold)",
                        textTransform: "uppercase", fontWeight: 700, marginBottom: 8 }}>
            ⚔ Other duels · just finished
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {recent.map((r) => (
              <a key={r.match_id} href={`/replay?id=${r.match_id}`}
                 style={{ display: "flex", justifyContent: "space-between",
                          color: "var(--text)", fontSize: 13, textDecoration: "none",
                          padding: "4px 6px", borderRadius: 4 }}
                 onMouseEnter={(e) => e.currentTarget.style.background = "var(--card-hover, rgba(255,255,255,0.04))"}
                 onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}>
                <span style={{ color: "var(--dim)" }}>
                  {r.models ? r.models.join(" vs ") : "anonymous duel"}
                </span>
                <span style={{ color: "var(--dim)", fontSize: 12 }}>
                  {r.turns} turns · {r.method}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QuipCard({ side, text }) {
  const color = side === "a" ? "var(--green)" : "var(--blue, #5aa0ff)";
  return (
    <div style={{ padding: "10px 12px", border: `1px solid ${color}`,
                  borderRadius: 6, background: "rgba(255,255,255,0.02)" }}>
      <div style={{ fontSize: 10, letterSpacing: 2, color, fontWeight: 700,
                    textTransform: "uppercase", marginBottom: 4 }}>
        Fighter {side.toUpperCase()}
      </div>
      <div style={{ fontStyle: "italic", fontSize: 14, lineHeight: 1.4,
                    color: text ? "var(--text)" : "var(--dim)" }}>
        {text ? `“${text}”` : "…thinking…"}
      </div>
    </div>
  );
}

function CombatTicker({ log, status }) {
  // Show last 6 turns; scroll into view as new ones land.
  const shown = log.slice(-6);
  return (
    <div style={{
      marginTop: 4, padding: "10px 12px",
      border: "1px solid var(--line)", borderRadius: 6,
      background: "rgba(0,0,0,0.25)",
      minHeight: 100, maxHeight: 200, overflowY: "auto",
      fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
      fontSize: 12.5, lineHeight: 1.6,
    }}>
      {shown.length === 0 ? (
        <div style={{ color: "var(--dim)" }}>
          {status === "queued" ? "waiting for a worker to pick up your match…"
                                : "LLMs are thinking about the first move…"}
        </div>
      ) : (
        shown.map((t) => <TickerLine key={t.turn} tick={t} />)
      )}
    </div>
  );
}

function TickerLine({ tick }) {
  // Build a one-line summary. Blind-safe: only canvas sides.
  const parts = [];
  parts.push(<span key="t" style={{ color: "var(--gold)" }}>
    turn {String(tick.turn).padStart(2, "0")}
  </span>);
  const actA = tick.action_a?.action;
  const actB = tick.action_b?.action;
  if (actA || actB) {
    parts.push(<span key="a" style={{ color: "var(--dim)" }}> · </span>);
    parts.push(<span key="ac" style={{ color: "var(--text)" }}>
      <span style={{ color: "var(--green)" }}>A:{actA || "?"}</span>
      {" vs "}
      <span style={{ color: "var(--blue, #5aa0ff)" }}>B:{actB || "?"}</span>
    </span>);
  }
  const hits = tick.hits || [];
  if (hits.length === 0) {
    parts.push(<span key="miss" style={{ color: "var(--dim)" }}> — no hit</span>);
  } else {
    for (const h of hits) {
      const cls = h.sharp ? { color: "var(--red-2)", fontWeight: 700 }
                          : { color: "var(--dim)" };
      const glyph = h.sharp ? "◆" : "◇";
      parts.push(<span key={`h${hits.indexOf(h)}`} style={{ marginLeft: 6, ...cls }}>
        {glyph} {h.by === "a" ? "A" : "B"}→{h.part} {h.damage}dmg{h.sharp ? " SHARP" : ""}
      </span>);
    }
  }
  return <div>{parts}</div>;
}
