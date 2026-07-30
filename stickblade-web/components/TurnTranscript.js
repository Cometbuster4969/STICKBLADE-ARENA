"use client";
import { useMemo, useState } from "react";

/**
 * TurnTranscript — persistent per-turn log below the replay canvas.
 *
 * Fixes the "turn-wise output is not displayed" complaint: previously
 * the ONLY place per-turn LLM reasoning surfaced was as fleeting canvas
 * speech bubbles (~1.5s per turn, positioned above the fighter's head,
 * easy to miss while eyes track the swordfight). This component surfaces
 * the same data as a scrollable persistent list — the entire "why did
 * each model make this move" story visible at a glance.
 *
 * Data source: the replay JSON already contains everything we need:
 *   * replay.thoughts = [{f, turn, a, b}, ...]  LLM reasoning per turn
 *   * replay.events   = [{f, k:"hit", d, s, l, part, by}, ...] damage events
 *
 * Blind-safe: uses "Fighter A" / "Fighter B" not model names. No reveal
 * leak. Matches the same blind convention as CombatTicker.
 *
 * Click-to-seek: each row has a small ⏵ button that dispatches a
 * `replay-seek` CustomEvent with the frame index; the vanilla player
 * (public/player.js) listens for it. If the player isn't wired for
 * that event yet, the button is still visible but click is a no-op —
 * doesn't break anything, ships with graceful degradation.
 */
export default function TurnTranscript({ replay }) {
  const [expanded, setExpanded] = useState(true);

  // Roll up per-turn: pair each thought entry with the hit events that
  // happened AFTER it (up to the next thought's frame). Cheap: one pass
  // over thoughts + one pass over events. Memoized so scroll doesn't
  // re-compute on every render.
  const rows = useMemo(() => {
    const thoughts = replay?.thoughts || [];
    const events = replay?.events || [];
    const p1 = replay?.meta?.p1?.name || "Fighter A";
    const p2 = replay?.meta?.p2?.name || "Fighter B";
    return thoughts.map((t, i) => {
      const nextF = thoughts[i + 1]?.f ?? Infinity;
      const turnHits = events.filter(
        (e) => e.k === "hit" && e.f >= t.f && e.f < nextF
      );
      // events store attacker name in `by`; translate to canvas side.
      // In blind mode both p1/p2 are already "Fighter A"/"Fighter B" so
      // this is a straight name-equality check.
      return {
        turn: t.turn,
        frame: t.f,
        aThought: t.a || "",
        bThought: t.b || "",
        hits: turnHits.map((e) => ({
          by: e.by === p1 ? "a" : e.by === p2 ? "b" : "?",
          part: e.part,
          damage: e.d,
          sharp: !!e.s,
          lethal: !!e.l,
        })),
      };
    });
  }, [replay]);

  if (!rows.length) return null;

  // Click-to-seek: dispatch a custom event the vanilla player can listen
  // for. Wrapped in try because DOM CustomEvent isn't available in SSR
  // (component is "use client" so this only runs browser-side anyway,
  // but belt-and-braces).
  const seekTo = (frame) => {
    try {
      window.dispatchEvent(new CustomEvent("replay-seek", { detail: { frame } }));
    } catch (_) { /* SSR / older browsers — no-op */ }
  };

  return (
    <section className="panel" style={{
      marginTop: 12, padding: "14px 16px",
      background: "rgba(255,255,255,0.02)",
    }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: expanded ? 10 : 0, cursor: "pointer",
      }} onClick={() => setExpanded((e) => !e)}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span className="panel-title">
            <span className="tick" /> Turn-by-turn transcript
          </span>
          <span style={{ color: "var(--dim)", fontSize: 12 }}>
            {rows.length} turn{rows.length === 1 ? "" : "s"} · click row to jump the replay
          </span>
        </div>
        <button aria-label={expanded ? "Collapse transcript" : "Expand transcript"}
          style={{
            background: "transparent", border: "1px solid var(--line)",
            color: "var(--text-2)", cursor: "pointer",
            padding: "4px 10px", borderRadius: 4, fontSize: 12,
          }}>
          {expanded ? "▼" : "▶"}
        </button>
      </div>

      {expanded && (
        <div style={{ maxHeight: 340, overflowY: "auto",
                      border: "1px solid var(--line)", borderRadius: 4,
                      background: "rgba(0,0,0,0.15)" }}>
          {rows.map((r, i) => (
            <div key={r.turn} style={{
              padding: "10px 12px",
              borderBottom: i < rows.length - 1 ? "1px dashed var(--line)" : "none",
              fontSize: 13, lineHeight: 1.45,
            }}>
              <div style={{
                display: "flex", justifyContent: "space-between",
                alignItems: "center", marginBottom: 6,
              }}>
                <span style={{
                  color: "var(--gold, #d4b962)", fontWeight: 700,
                  fontSize: 11, letterSpacing: 2, textTransform: "uppercase",
                }}>
                  Turn {String(r.turn).padStart(2, "0")}
                </span>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {r.hits.length > 0 && (
                    <HitBadges hits={r.hits} />
                  )}
                  <button onClick={() => seekTo(r.frame)}
                    title="Jump replay to this turn"
                    style={{
                      background: "transparent", border: "1px solid var(--line)",
                      color: "var(--gold, #d4b962)", cursor: "pointer",
                      padding: "2px 8px", borderRadius: 3, fontSize: 11,
                    }}>
                    ⏵ jump
                  </button>
                </div>
              </div>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10,
              }}>
                <ThoughtCell side="a" text={r.aThought} />
                <ThoughtCell side="b" text={r.bThought} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** One side's reasoning bubble. Left border color-coded by fighter. */
function ThoughtCell({ side, text }) {
  const color = side === "a" ? "var(--green, #56dc82)" : "var(--blue, #5aa0ff)";
  return (
    <div style={{
      borderLeft: `3px solid ${color}`, paddingLeft: 10,
      minHeight: 34,
    }}>
      <div style={{
        color, fontSize: 10, letterSpacing: 2, fontWeight: 700,
        textTransform: "uppercase", marginBottom: 2,
      }}>
        Fighter {side.toUpperCase()}
      </div>
      <div style={{
        color: text ? "var(--text)" : "var(--dim)",
        fontStyle: text ? "italic" : "normal",
        fontSize: 12.5,
      }}>
        {text ? `"${text}"` : "(no reasoning captured — likely used scripted fallback)"}
      </div>
    </div>
  );
}

/** Inline compact hit summary: "◆ A→head 12dmg SHARP · ◇ B→arm 2dmg" */
function HitBadges({ hits }) {
  return (
    <span style={{
      fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
      fontSize: 11, color: "var(--dim)",
    }}>
      {hits.map((h, i) => {
        const glyph = h.sharp ? "◆" : "◇";
        const clr = h.sharp
          ? (h.lethal ? "var(--gold, #d4b962)" : "var(--red-2, #dc5656)")
          : "var(--dim)";
        return (
          <span key={i} style={{ color: clr, marginLeft: i ? 8 : 0,
                                   fontWeight: h.sharp ? 700 : 400 }}>
            {glyph} {h.by?.toUpperCase()}→{h.part} {h.damage}dmg
            {h.lethal ? " LETHAL" : h.sharp ? " SHARP" : ""}
          </span>
        );
      })}
    </span>
  );
}
