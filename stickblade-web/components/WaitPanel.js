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
  const [elapsedSec, setElapsedSec] = useState(0);
  const pollRef = useRef(null);
  const readyFiredRef = useRef(false);
  const startedAtRef = useRef(Date.now());

  // Elapsed-time ticker — 1Hz update so the wait feels alive even
  // when the ticker log is silent between turns. Deliberately
  // ELAPSED not REVERSE-COUNTDOWN: a countdown that hits 0:00 while
  // the match is still running would panic the user. Elapsed +
  // expected-range ("~60s typical") is the honest framing.
  useEffect(() => {
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

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

  // Phase label — human-readable state instead of raw "Simulating".
  // Deliberately avoids the word "video" (implies scripted playback);
  // uses "match" / "LLMs thinking" / "physics" to reinforce
  // "this is real inference happening now" framing that came out
  // of the friend-feedback session.
  const phaseLabel = status === "queued"
    ? "Queued — waiting for a worker"
    : turn === 0
      ? "Setting up arena · LLMs about to make first move"
      : `Running match — LLMs deciding turn ${turn} / 24`;

  const mmss = (s) => `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;

  return (
    <div className="panel" style={{ padding: 16 }}>
      <div className="panel-head" style={{ marginBottom: 6,
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center",
                                            flexWrap: "wrap", gap: 8 }}>
        <span className="panel-title">
          <span className="tick" /> {phaseLabel}
        </span>
        <span style={{ color: "var(--dim)", fontSize: 12, letterSpacing: 0.5,
                        fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>
          {mmss(elapsedSec)} <span style={{ color: "var(--mute)" }}>/ ~1:00 typical</span>
        </span>
      </div>
      {/* Short "why is this slow" hint — the #1 confusion point from
          friend feedback. Only shown while running (not queued) to keep
          the queued-panel focused on queue position. */}
      {status !== "queued" && (
        <div style={{ marginBottom: 10, fontSize: 12, color: "var(--dim)",
                       fontStyle: "italic", lineHeight: 1.4 }}>
          Each turn = one LLM API call per fighter (~5-15s of real inference)
          + 3s of physics. That's why it's not instant — it's live model
          decisions, not a pre-recorded animation.
        </div>
      )}
      {status === "queued" && qpos != null && qpos > 0 && (
        <div style={{ marginBottom: 10 }}>
          <span style={{ color: "var(--gold)", fontSize: 13, letterSpacing: 1 }}>
            {qpos} {qpos === 1 ? "fight" : "fights"} ahead of you
          </span>
        </div>
      )}

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

      {/* --- Read-while-you-wait: about-this-benchmark disclosure ---
          Collapsed by default. Deliberately placed in the wait panel
          (not just on the landing page) because THIS is the moment
          users have nothing else to do and the highest chance of
          engaging with the explainer. From friend-feedback: normies
          don't understand what they're looking at until they read
          more; give them the read-more where they naturally pause. */}
      <details style={{
        marginTop: 14, padding: "10px 12px",
        border: "1px solid var(--line)", borderRadius: 6,
        background: "rgba(255,255,255,0.015)", fontSize: 13,
      }}>
        <summary style={{ cursor: "pointer", color: "var(--gold)",
                          fontWeight: 700, fontSize: 11, letterSpacing: 2,
                          textTransform: "uppercase", listStyle: "none" }}>
          📖 About this benchmark (read while you wait)
        </summary>
        <div style={{ marginTop: 10, color: "var(--text-2)", lineHeight: 1.55 }}>
          <p style={{ marginBottom: 8 }}>
            <b>What this measures.</b> Traditional LLM benchmarks
            (MMLU, GPQA, Arena-Hard) test text answering. This one tests
            whether a model can plan under physical constraints — momentum,
            reach, opponent positioning, weapon geometry. Same 29 models
            you'd see on other leaderboards, evaluated on a different axis.
          </p>
          <p style={{ marginBottom: 8 }}>
            <b>Why blind voting.</b> If you saw model IDs before voting
            you'd anchor on brand. Blind = you rate the fighting behavior,
            not the model name. Reveal happens after the vote.
          </p>
          <p style={{ marginBottom: 8 }}>
            <b>Why the leaderboard has provisional flags.</b> Ratings
            under N=10 matches are Elo-shaped noise (K=32 can swing
            ±80 pts from 5 lucky matchups). We mark those honestly
            instead of pretending small samples are stable.
          </p>
          <p style={{ marginBottom: 0, color: "var(--dim)", fontSize: 12 }}>
            Featured on the{" "}
            <a href="https://www.pymunk.org/en/latest/showcase.html#stickblade-arena"
               target="_blank" rel="noreferrer"
               style={{ color: "inherit", textDecoration: "underline" }}>
              official pymunk showcase
            </a>. Source on{" "}
            <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA"
               target="_blank" rel="noreferrer"
               style={{ color: "inherit", textDecoration: "underline" }}>
              GitHub
            </a>.
          </p>
        </div>
      </details>

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
          {status === "queued"
            ? "waiting for a worker to pick up your match…"
            : "waiting on the first API round-trip — each LLM is deciding its opening move…"}
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
