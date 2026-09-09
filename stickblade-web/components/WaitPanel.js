"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { getMatch, getHeadToHead, getRecent, cancelMatch } from "@/lib/api";

/* Wait-screen for an in-progress match (review items 7-9).

   What it replaced: a spinner plus a status string, with the interesting
   data (quips, queue position, live ticker) rendered as secondary text. The
   wait IS the product's worst moment — 45-90s of nothing while two model
   APIs think — so this panel is built to answer three questions the whole
   time:

     1. IS IT WORKING?   -> progress timeline driven by the backend's real
                            match phase (QUEUED / THINKING / SIM / done),
                            not a client-side guess
     2. HOW FAR ALONG?   -> "Turn 4 of 24" + elapsed clock + honest range
     3. IS IT BROKEN?    -> explicit stalled state at 120s with
                            Keep waiting / Cancel / Retry, plus live
                            disclosure when a turn fell back to the
                            scripted bot (benchmark integrity)

   Blind rules unchanged: canvas sides (a/b) only, never model names. */

const STALL_AFTER_S = 120;    // past this, offer explicit recovery
const MAX_TURNS = 24;         // config.MAX_TURNS

const PHASES = [
  ["QUEUED",    "Queued"],
  ["THINKING",  "Models thinking"],
  ["SIM",       "Physics resolving"],
  ["DONE",      "Match complete"],
];

// server.py publishes Match.PH_* verbatim, and that enum has two members the
// timeline doesn't: PH_BANNER (the turn-title card, shown between turns) and
// PH_OVER (sim ended). Without this alias PHASES.findIndex returns -1,
// Math.max clamps it to 0, and the bar snaps back to "Queued" mid-fight —
// exactly the untrustworthy progress indicator the review complained about.
const PHASE_ALIAS = { BANNER: "SIM", OVER: "DONE" };

export default function WaitPanel({ matchId, modelA, modelB, onReady,
                                    onCancel, onRetry }) {
  const [live, setLive] = useState(null);
  const [status, setStatus] = useState("queued");
  const [h2h, setH2h] = useState(null);
  const [recent, setRecent] = useState([]);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [dismissStall, setDismissStall] = useState(false);
  // Server-computed progress (§13): real turn budget, elapsed and ETA.
  // It carries total_turns, which the MAX_TURNS constant cannot know —
  // sprint/standard/full are 4/12/24 turns (benchmark spec v1.0).
  const [progress, setProgress] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const pollRef = useRef(null);
  const readyFiredRef = useRef(false);
  const startedAtRef = useRef(Date.now());

  // Elapsed-time ticker — 1Hz so the wait feels alive between turns.
  // Deliberately ELAPSED, never a countdown: a countdown that hits 0:00
  // while the match is still running reads as a failure.
  useEffect(() => {
    startedAtRef.current = Date.now();
    const id = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!modelA || !modelB) return;
    getHeadToHead(modelA, modelB).then(setH2h).catch(() => setH2h(null));
  }, [modelA, modelB]);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getRecent().then((r) => { if (!cancelled) setRecent(r.slice(0, 6)); })
                 .catch(() => {});
    };
    tick();
    const id = setInterval(tick, 20000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

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
          if (s.progress) setProgress(s.progress);
          if (s.status === "done") {
            if (!readyFiredRef.current) {
              readyFiredRef.current = true;
              // 2.5s settle: fast matches used to flip the ticker away before
              // the last few turns could be read.
              setTimeout(() => { if (!cancelled) onReady?.(matchId); }, 2500);
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

  const quips = live?.quips;
  const log   = live?.log || [];
  const qpos  = live?.queue_pos;
  const turn  = live?.turn || 0;
  const rawPhase = live?.phase || (status === "queued" ? "QUEUED" : "THINKING");
  const phase = PHASE_ALIAS[rawPhase] || rawPhase;

  const fallbackTurns = useMemo(
    () => log.filter((t) => t.fallback_a || t.fallback_b),
    [log]
  );
  const stalled = status !== "done" && elapsedSec >= STALL_AFTER_S && !dismissStall;

  const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const phaseIdx = Math.max(0, PHASES.findIndex(([k]) =>
    k === (status === "done" ? "DONE" : phase)));

  // Prefer the server's turn budget: MAX_TURNS is the legacy constant and
  // is simply wrong for a 4-turn sprint.
  const total = progress?.total_turns || MAX_TURNS;
  const headline = status === "done"
    ? "Match complete — building replay"
    : status === "queued"
      ? (qpos > 0 ? `Queued — ${qpos} ${qpos === 1 ? "fight" : "fights"} ahead of you`
                  : "Queued — waiting for a worker")
      : turn === 0
        ? "Setting up the arena"
        : `Turn ${turn} of ${total}`;

  return (
    <div className="panel" style={{ padding: 16 }}>
      {/* ---------- Big header: who is fighting + where we are ---------- */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontFamily: "var(--font-display), system-ui, sans-serif",
                        fontSize: 20, fontWeight: 700, letterSpacing: 2 }}>
            <span style={{ color: "var(--green)" }}>FIGHTER A</span>
            <span style={{ color: "var(--mute)", margin: "0 10px" }}>vs</span>
            <span style={{ color: "var(--blue)" }}>FIGHTER B</span>
          </div>
          <div aria-live="polite" style={{ fontSize: 13, color: "var(--text-2)",
                                          marginTop: 2 }}>
            {headline}
          </div>
        </div>
        <div style={{ textAlign: "right", fontFamily: "ui-monospace, SFMono-Regular, monospace",
                      fontSize: 13, color: "var(--text-2)" }}>
          {mmss(elapsedSec)}
          <div style={{ fontSize: 11, color: "var(--dim)" }}>
            usually 45–90s · up to 3 min
          </div>
        </div>
      </div>

      {/* ---------- Progress timeline ---------- */}
      <div className="timeline" aria-hidden="false">
        {PHASES.map(([key, label], i) => {
          const state = i < phaseIdx ? "done" : i === phaseIdx ? "active" : "todo";
          return (
            <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {i > 0 && <span className="tl-sep" aria-hidden="true">→</span>}
              <span className="tl-step" data-state={state}>
                <span className="tl-dot" />
                {label}
              </span>
            </span>
          );
        })}
      </div>

      {/* ---------- Honest progress (§13) ----------
          The bar is the server's own turn count, not a client-side guess,
          and the ETA only appears once a turn has actually landed. */}
      <div style={{ margin: "10px 0 12px" }}>
        <div className="progress-track"
             role="progressbar"
             aria-valuemin={0}
             aria-valuemax={100}
             aria-valuenow={Math.round(progress?.percent || 0)}
             aria-label="Match progress">
          <div className="progress-fill"
               style={{ width: `${Math.min(100, progress?.percent || 0)}%` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between",
                      gap: 10, flexWrap: "wrap", marginTop: 6,
                      fontSize: 12, color: "var(--dim)" }}>
          <span>
            turn {turn} / {total}
            {progress?.elapsed_s != null &&
              ` · ${mmss(progress.elapsed_s)} elapsed`}
            {progress?.eta_s != null &&
              ` · ~${mmss(progress.eta_s)} remaining`}
          </span>
          <span>
            <button
              className="btn-link"
              disabled={cancelling}
              onClick={async () => {
                if (!matchId) return;
                setCancelling(true);
                try {
                  await cancelMatch(matchId);
                  onCancel?.();
                } catch {
                  setCancelling(false);
                }
              }}
            >
              {cancelling ? "Cancelling…" : "✕ Cancel match"}
            </button>
          </span>
        </div>
      </div>

      {/* ---------- Stalled-state recovery ---------- */}
      {stalled && (
        <div className="stalled" role="status">
          <p>
            <b>This match is taking longer than usual.</b> The model provider
            may be throttled or the queue is deep. Nothing is lost by waiting,
            but you can also cancel and retry.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-sm btn-ghost" onClick={() => setDismissStall(true)}>
              Keep waiting
            </button>
            {onRetry && (
              <button className="btn btn-sm" onClick={onRetry}>
                Retry same settings
              </button>
            )}
            {onCancel && (
              <button className="btn btn-sm btn-ghost" onClick={onCancel}>
                Cancel match
              </button>
            )}
          </div>
        </div>
      )}

      {/* ---------- Degraded-turn disclosure, live ---------- */}
      {fallbackTurns.length > 0 && (
        <div className="stalled" style={{ borderColor: "rgba(255, 102, 128, 0.45)",
                                          background: "rgba(255, 61, 92, 0.07)" }}>
          <p>
            <b>Scripted fallback in use.</b>{" "}
            {fallbackTurns.map((t) =>
              `Turn ${t.turn}: ${[t.fallback_a && "Fighter A", t.fallback_b && "Fighter B"]
                .filter(Boolean).join(" + ")}`).join(" · ")}.
            {" "}Those turns were played by the heuristic bot, not the model —
            the integrity banner after the vote will say the same.
          </p>
        </div>
      )}

      {/* ---------- Pre-fight trash talk ---------- */}
      {quips && (quips.a || quips.b) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <QuipCard side="a" text={quips.a} />
          <QuipCard side="b" text={quips.b} />
        </div>
      )}

      {/* ---------- Live combat ticker ---------- */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "baseline", marginBottom: 6 }}>
          <span className="lbl" style={{ margin: 0 }}>Live combat ticker</span>
          <button
            className="btn btn-sm btn-ghost"
            aria-expanded={techOpen}
            onClick={() => setTechOpen((v) => !v)}
          >
            {techOpen ? "Hide technical log" : "Technical log"}
          </button>
        </div>
        <div className="ticker" aria-live="polite" aria-relevant="additions">
          {log.length === 0 ? (
            <div style={{ color: "var(--dim)" }}>
              {status === "queued"
                ? "waiting for a worker to pick up your match…"
                : "waiting on the first API round-trip — each model is deciding its opening move…"}
            </div>
          ) : (
            log.slice(-8).map((t) => <TickerLine key={t.turn} tick={t} tech={techOpen} />)
          )}
        </div>
      </div>

      {/* ---------- Head-to-head ---------- */}
      {h2h && h2h.total > 0 && (
        <div style={{ padding: 12, borderTop: "1px dashed var(--line)" }}>
          <div className="lbl" style={{ color: "var(--gold)" }}>
            Previous duels · this exact matchup
          </div>
          <div style={{ display: "flex", justifyContent: "space-between",
                        flexWrap: "wrap", gap: 8, fontSize: 14 }}>
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

      {/* ---------- Read while you wait ---------- */}
      <details style={{ border: "1px solid var(--line)", borderRadius: 6,
                        background: "rgba(255,255,255,0.015)", fontSize: 13,
                        padding: "10px 12px" }}>
        <summary style={{ cursor: "pointer", color: "var(--gold)", fontWeight: 700,
                          fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>
          About this benchmark (read while you wait)
        </summary>
        <div style={{ marginTop: 10, color: "var(--text-2)", lineHeight: 1.55 }}>
          <p style={{ marginBottom: 8 }}>
            <b>What this measures.</b> Text benchmarks test answering. This one
            tests whether a model can plan under physical constraints —
            momentum, reach, opponent positioning, weapon geometry.
          </p>
          <p style={{ marginBottom: 8 }}>
            <b>Why blind voting.</b> Seeing model names before you judge anchors
            you to the brand. Blind means you rate the fighting, then the reveal
            happens after your vote is locked.
          </p>
          <p style={{ marginBottom: 0, color: "var(--dim)", fontSize: 12 }}>
            Ratings under 10 matches are marked provisional — Elo at small N is
            noise, and we would rather show you the uncertainty than hide it.
          </p>
        </div>
      </details>

      {/* ---------- Other duels ---------- */}
      {recent.length > 0 && (
        <div style={{ padding: 12, borderTop: "1px dashed var(--line)" }}>
          <div className="lbl" style={{ color: "var(--gold)" }}>Other duels · just finished</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {recent.map((r) => (
              <a key={r.match_id} href={`/replay?id=${r.match_id}`}
                 style={{ display: "flex", justifyContent: "space-between", gap: 10,
                          color: "var(--text-2)", fontSize: 13, textDecoration: "none",
                          padding: "4px 6px", borderRadius: 4 }}>
                <span style={{ color: "var(--dim)" }}>
                  {r.models ? r.models.join(" vs ") : "anonymous duel"}
                </span>
                <span style={{ color: "var(--dim)", fontSize: 12 }}>
                  {r.weapon} · {r.turns} turns · {r.method}
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
  const color = side === "a" ? "var(--green)" : "var(--blue)";
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

/* One ticker row. Event types are distinguished by colour AND by a glyph +
   a word (SHARP / LETHAL / FALLBACK), so the meaning survives greyscale. */
function TickerLine({ tick, tech }) {
  const hits = tick.hits || [];
  return (
    <div className="tk-row">
      <span className="tk-turn">T{String(tick.turn).padStart(2, "0")}</span>
      {(tick.action_a?.action || tick.action_b?.action) && (
        <span className="tk-act">
          <span style={{ color: "var(--green)" }}>A:{tick.action_a?.action || "?"}</span>
          {tech && tick.action_a?.footwork && <span style={{ color: "var(--mute)" }}>/<span>{tick.action_a.footwork}</span></span>}
          {" vs "}
          <span style={{ color: "var(--blue)" }}>B:{tick.action_b?.action || "?"}</span>
          {tech && tick.action_b?.footwork && <span style={{ color: "var(--mute)" }}>/<span>{tick.action_b.footwork}</span></span>}
        </span>
      )}
      {hits.length === 0 ? (
        <span className="tk-miss">— no hit</span>
      ) : (
        hits.map((h, i) => (
          <span key={i} className={h.lethal ? "tk-lethal" : h.sharp ? "tk-sharp" : "tk-hit"}>
            {h.lethal ? "✖" : h.sharp ? "◆" : "◇"}{" "}
            {h.by === "a" ? "A" : "B"}→{h.part} {h.damage}
            {h.lethal ? " LETHAL" : h.sharp ? " SHARP" : ""}
          </span>
        ))
      )}
      {(tick.fallback_a || tick.fallback_b) && (
        <span className="tk-fb">FALLBACK {tick.fallback_a ? "A" : ""}{tick.fallback_b ? "B" : ""}</span>
      )}
      {tech && (
        <span style={{ color: "var(--mute)" }}>
          hp {tick.hp_a}/{tick.hp_b}
          {tick.distance != null && ` · d=${tick.distance}`}
        </span>
      )}
    </div>
  );
}
