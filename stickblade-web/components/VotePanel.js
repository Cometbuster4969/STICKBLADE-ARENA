"use client";
import { useEffect, useState } from "react";
import { getVoterTier, setVoterTier } from "@/lib/prefs";

/**
 * Multi-axis vote (action-plan §6).
 *
 * A viewer may prefer the dramatic fighter even when that fighter made the
 * worse decisions. Collecting the axes separately lets the dataset measure
 * the gap between "fought intelligently" and "was fun to watch" — and only
 * the tactical vote moves the rating.
 *
 * The extra axes are genuinely optional: the tactical vote is the gate for
 * the reveal, everything else is a one-click "add detail" step.
 *
 * The expert toggle (§6) records a self-declared evaluator tier on the
 * vote. It is NOT a weighting scheme — expert votes are never given more
 * influence, and the two tiers are never pooled silently. It exists so a
 * researcher can later ask "do experienced evaluators disagree with the
 * crowd?", which is unanswerable if the tiers are mixed at write time.
 */
const AXES = [
  { key: "execution", label: "Executed more cleanly",
    hint: "Did what it said it would do, without wasted motion." },
  { key: "entertainment", label: "More entertaining",
    hint: "Fun to watch — this does NOT affect the ranking." },
  { key: "deserved", label: "Deserved the win",
    hint: "Who the physics says earned it." },
];

export default function VotePanel({ onVote, disabled, prediction, streak }) {
  const [choice, setChoice] = useState(null);
  const [axes, setAxes] = useState({});
  const [confidence, setConfidence] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [busy, setBusy] = useState(false);
  // §6 expert track — persisted, so a returning evaluator isn't asked again.
  const [expert, setExpert] = useState(false);
  useEffect(() => { setExpert(getVoterTier() === "expert"); }, []);

  const toggleExpert = () => {
    const next = !expert;
    setExpert(next);
    setVoterTier(next ? "expert" : "casual");
  };

  const submit = async () => {
    if (!choice) return;
    setBusy(true);
    try {
      await onVote(choice, {
        execution: axes.execution || null,
        entertainment: axes.entertainment || null,
        deserved: axes.deserved || null,
        confidence: confidence || null,
        voter_tier: expert ? "expert" : "casual",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel" style={{ padding: 14, textAlign: "center",
                                    borderColor: "var(--gold, #d4b962)",
                                    borderStyle: "solid" }}>
      <div style={{ fontSize: 11, letterSpacing: 2, fontWeight: 700,
                    color: "var(--gold, #d4b962)", textTransform: "uppercase",
                    marginBottom: 8 }}>
        🔒 Models hidden — vote to reveal
      </div>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12,
                  maxWidth: 520, marginLeft: "auto", marginRight: "auto" }}>
        <b style={{ color: "var(--text)" }}>Who fought more intelligently?</b>{" "}
        That vote moves the ranking. Voting unlocks model names, Elo change
        {prediction ? " and whether your prediction was right" : ""}.
      </p>

      <div className="vote-row" role="group" aria-label="Tactical vote">
        <button className="vote-a" onClick={() => setChoice("a")}
                aria-pressed={choice === "a"} disabled={busy}>
          👑 Fighter A
        </button>
        <button className="vote-draw" onClick={() => setChoice("draw")}
                aria-pressed={choice === "draw"} disabled={busy}>
          Draw
        </button>
        <button className="vote-b" onClick={() => setChoice("b")}
                aria-pressed={choice === "b"} disabled={busy}>
          Fighter B 👑
        </button>
      </div>

      {choice && (
        <div style={{ marginTop: 12 }}>
          <button
            className="fight-btn"
            disabled={disabled || busy}
            onClick={submit}
            style={{ minWidth: 260 }}
          >
            {busy ? "Submitting…" : "Submit vote & reveal models"}
          </button>

          <div style={{ marginTop: 10 }}>
            <button className="btn-link" onClick={() => setShowDetail((v) => !v)}
                    aria-expanded={showDetail}>
              {showDetail ? "− Hide" : "+"} Add detail (optional) — execution,
              entertainment, confidence, evaluator tier
            </button>
          </div>

          {showDetail && (
            <div style={{ marginTop: 10, textAlign: "left", maxWidth: 620,
                          margin: "10px auto 0", padding: 12, borderRadius: 8,
                          border: "1px solid var(--line)",
                          background: "rgba(0,0,0,0.2)" }}>
              {AXES.map((ax) => (
                <fieldset key={ax.key} style={{ border: "none", marginBottom: 10,
                                                padding: 0 }}>
                  <legend style={{ fontSize: 12, color: "var(--text-2)",
                                   marginBottom: 4 }}>
                    {ax.label}
                  </legend>
                  <p style={{ fontSize: 11, color: "var(--dim)",
                              marginBottom: 6 }}>{ax.hint}</p>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {["a", "draw", "b"].map((side) => (
                      <button key={side}
                        className={side === "a" ? "vote-a" : side === "b"
                          ? "vote-b" : "vote-draw"}
                        style={{ padding: "5px 12px", fontSize: 12,
                                 opacity: axes[ax.key] === side ? 1 : 0.6 }}
                        aria-pressed={axes[ax.key] === side}
                        onClick={() => setAxes((prev) => ({
                          ...prev,
                          [ax.key]: prev[ax.key] === side ? null : side,
                        }))}>
                        {side === "draw" ? "Draw" : `Fighter ${side.toUpperCase()}`}
                      </button>
                    ))}
                  </div>
                </fieldset>
              ))}
              <label style={{ fontSize: 12, color: "var(--text-2)",
                              display: "flex", alignItems: "center",
                              gap: 8, marginTop: 10, cursor: "pointer" }}
                     title="Self-declared. Expert and casual votes are stored separately and can be reported separately — expert votes are never weighted higher.">
                <input type="checkbox" checked={expert}
                       onChange={toggleExpert}
                       style={{ width: 16, height: 16 }} />
                I am an experienced evaluator
                <span style={{ color: "var(--dim)", fontSize: 11 }}>
                  (recorded with the vote; both tiers stay separable)
                </span>
              </label>
              <label style={{ fontSize: 12, color: "var(--text-2)",
                              display: "block", marginTop: 6 }}>
                How confident are you? (1–5)
                <select
                  value={confidence || ""}
                  onChange={(e) => setConfidence(e.target.value
                    ? Number(e.target.value) : null)}
                  style={{ marginLeft: 8, minHeight: 34 }}>
                  <option value="">—</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
            </div>
          )}
        </div>
      )}

      {streak?.total > 0 && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--dim)",
                      letterSpacing: 1 }}>
          your predictions:{" "}
          <b style={{ color: "var(--gold)" }}>{streak.wins}</b>/{streak.total}{" "}
          ({Math.round((streak.wins / streak.total) * 100)}%)
          <span style={{ margin: "0 6px", color: "var(--mute)" }}>·</span>
          streak <b style={{ color: "var(--gold)" }}>{streak.cur}</b>
        </div>
      )}
    </div>
  );
}
