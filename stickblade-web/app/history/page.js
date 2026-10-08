"use client";
import { useEffect, useMemo, useState } from "react";
import { getRecent } from "@/lib/api";
import ShareButton from "@/components/ShareButton";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { MotionSection, StaggerContainer, StaggerItem, SlideIn } from "@/components/MotionSection";

const WEAPON_ICON = { sword: "🗡", dagger: "🔪", spear: "🥄", flail: "⛓",
                      bow: "🏹" };
const ARENA_LABEL = { normal: "Normal arena", ice: "Ice arena",
                      low_gravity: "Low-G arena" };
const METHOD_LABEL = {
  kill: "knockout", hp: "HP lead", hp_draw: "draw (HP tie)",
  timeout: "time limit", draw: "draw", forfeit: "forfeit",
};

function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "yesterday" : `${d}d ago`;
}

function prettyZone(z) {
  if (!z) return "any zone";
  return z.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" ");
}

export default function HistoryPage() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [weapon, setWeapon] = useState("");
  const [unvotedOnly, setUnvotedOnly] = useState(false);

  useEffect(() => {
    getRecent().then(setRows).catch((e) => setErr(e.message));
  }, []);

  const [, forceTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => forceTick((n) => n + 1), 30000);
    return () => clearInterval(t);
  }, []);

  const weapons = useMemo(() => {
    const seen = [];
    (rows || []).forEach((m) => {
      if (m.weapon && !seen.includes(m.weapon)) seen.push(m.weapon);
    });
    return seen;
  }, [rows]);

  const shown = useMemo(() => (rows || []).filter((m) =>
    (!weapon || m.weapon === weapon) && (!unvotedOnly || !m.voted)),
  [rows, weapon, unvotedOnly]);

  const pendingVotes = (rows || []).filter((m) => !m.voted).length;

  const weaponFilters = [["", "All"], ...weapons.map((w) => [w, (WEAPON_ICON[w] || "") + " " + w.charAt(0).toUpperCase() + w.slice(1)])];

  return (
    <>
      <SiteNav />
    <div style={{ width: "100%", maxWidth: 860 }}>
      <MotionSection>
        <h2 style={{ margin: "24px 0 4px",
                     fontFamily: "var(--font-display), system-ui, sans-serif",
                     letterSpacing: 2, textTransform: "uppercase", fontSize: 28, fontWeight: 700 }}>
          Recent duels
        </h2>
      </MotionSection>
      <MotionSection delay={0.05}>
        <p style={{ color: "var(--text-2)", fontSize: 14, marginBottom: 16, lineHeight: 1.7 }}>
          Every duel is replayable. Fighters stay anonymous —{" "}
          {pendingVotes > 0 ? (
            <strong style={{ color: "var(--gold)" }}>
              {pendingVotes} {pendingVotes === 1 ? "match is" : "matches are"} waiting on a vote
            </strong>
          ) : (
            <span>and every match here has already been voted on</span>
          )}. Voting is what turns a fight into an Elo datapoint.
        </p>
      </MotionSection>

      {(rows?.length ?? 0) > 0 && (
        <SlideIn direction="up" delay={0.1}>
          <div className="panel" style={{ gap: 4, marginBottom: 12 }}>
            <div className="lbl" id="legend-histw">Weapon</div>
            <div className="chips" role="group" aria-labelledby="legend-histw">
              {weaponFilters.map(([w, label]) => (
                <button key={w || "all"} type="button" className="chip"
                        aria-pressed={weapon === w} onClick={() => setWeapon(w)}
                        data-press style={{ "--ph": "1.05", "--pt": "0.95" }}>
                  {label}
                </button>
              ))}
              <button type="button" className="chip"
                      aria-pressed={unvotedOnly}
                      onClick={() => setUnvotedOnly((v) => !v)}
                      data-press style={{ "--ph": "1.05", "--pt": "0.95" }}>
                🎭 Unvoted only
              </button>
            </div>
          </div>
        </SlideIn>
      )}

      {err && <div className="status enter-down" role="alert">✖ {err}</div>}

      {!err && rows && !rows.length && (
        <MotionSection>
          <div className="panel empty">
            <div className="empty-t">No duels yet.</div>
            <p style={{ color: "var(--dim)", fontSize: 13, margin: "6px 0 0" }}>
              You'll be the first. Pick two models, pick a weapon, and the physics engine does the rest.
            </p>
            <a className="btn btn-primary" href="/"
               style={{ textDecoration: "none", "--ph": "1.05" }} data-press>
              Start a duel →
            </a>
          </div>
        </MotionSection>
      )}

      {!err && rows && rows.length > 0 && !shown.length && (
        <MotionSection>
          <div className="panel empty">
            <div className="empty-t">No duels match that filter.</div>
            <button className="btn btn-sm" type="button"
                    onClick={() => { setWeapon(""); setUnvotedOnly(false); }}
                    data-press style={{ "--ph": "1.05" }}>
              Clear filters
            </button>
          </div>
        </MotionSection>
      )}

      <StaggerContainer className="hist" staggerDelay={0.06}>
        {shown.map((m) => {
          const url = typeof window !== "undefined"
            ? window.location.origin + "/replay?id=" + m.match_id : "";
          const degraded = (m.fallback_turns || 0) > 0 || m.fully_llm_controlled === false;
          const names = m.voted && Array.isArray(m.models) && m.models.length === 2
            ? m.models : ["Fighter A", "Fighter B"];
          const winner = m.winner_side === "a" ? names[0]
                       : m.winner_side === "b" ? names[1] : null;
          return (
            <StaggerItem key={m.match_id} direction="up">
              <article className="hist-card">
                <div className="hist-top">
                  <div style={{ fontSize: 14, lineHeight: 1.35 }}>
                    <span className="mono" style={{ opacity: 0.55, marginRight: 8 }}>
                      {m.match_id.slice(0, 8)}
                    </span>
                    <strong>{names[0]}</strong>
                    <span style={{ color: "var(--dim)", margin: "0 6px" }}>vs</span>
                    <strong>{names[1]}</strong>
                  </div>
                  <span style={{ color: "var(--dim)", fontSize: 12, whiteSpace: "nowrap" }}>
                    {ago(m.created)}
                  </span>
                </div>

                <div className="hist-meta">
                  <span>{WEAPON_ICON[m.weapon] || "⚔"} {m.weapon || "sword"}</span>
                  <span>Sharp: {prettyZone(m.sharp)}</span>
                  <span>{ARENA_LABEL[m.arena] || m.arena || "Normal arena"}</span>
                  <span>{m.mode === "joint" ? "🧠 Joint control" : "🎯 Macro control"}</span>
                  {m.blindfolded && <span>🙈 Blindfolded</span>}
                  <span>{m.turns ?? "—"} turns</span>
                  {winner ? (
                    <span style={{ borderColor: "rgba(46, 232, 165, 0.45)", color: "var(--green)" }}>
                      ✓ {METHOD_LABEL[m.method] || m.method} — {winner}
                    </span>
                  ) : (
                    <span>{METHOD_LABEL[m.method] || m.method || "no winner"}</span>
                  )}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                  {m.voted ? (
                    <span className="badge ok">🗳 Voted — names revealed</span>
                  ) : (
                    <span className="badge warn">🎭 Not voted — models stay hidden</span>
                  )}
                  {degraded ? (
                    <span className="badge off"
                          title="Some turns were resolved by the engine because the model timed out or answered invalid JSON">
                      ⚠ {m.fallback_turns ?? 0} fallback turn{m.fallback_turns === 1 ? "" : "s"}
                      {m.total_turns ? ` / ${m.total_turns}` : ""}
                    </span>
                  ) : (
                    <span className="badge ok" title="Every turn was decided by the model itself">
                      ⚙ Fully model-controlled
                    </span>
                  )}

                  <span style={{ flex: 1 }} />
                  <a className="btn btn-sm btn-primary"
                     href={`/replay?id=${m.match_id}`}
                     style={{ textDecoration: "none", "--ph": "1.05" }}
                     data-press>
                    ▶ Watch replay
                  </a>
                  {!m.voted && (
                    <a className="btn btn-sm"
                       href={`/replay?id=${m.match_id}#vote`}
                       style={{ textDecoration: "none", "--ph": "1.05" }}
                       data-press>
                      🗳 Vote
                    </a>
                  )}
                  <ShareButton url={url} label="📋 Share" compact />
                </div>
              </article>
            </StaggerItem>
          );
        })}
      </StaggerContainer>
    </div>
      <SiteFooter />
    </>
  );
}
