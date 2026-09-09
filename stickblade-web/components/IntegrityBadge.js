"use client";
import { useEffect, useState } from "react";
import { getIntegrity } from "@/lib/api";

/**
 * Replay Integrity panel (action-plan §8).
 *
 * Shows what every published match should be able to prove: that it is
 * version-pinned, seeded, has a complete action log, and replays to the
 * recorded result. Also surfaces the anti-gaming verdict (§7) so a win
 * earned by stalling or spamming is labelled rather than celebrated.
 */
export default function IntegrityBadge({ matchId, compact = false }) {
  const [rep, setRep] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!matchId) return;
    let alive = true;
    getIntegrity(matchId)
      .then((r) => alive && setRep(r))
      .catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [matchId]);

  if (err) return null;
  if (!rep) {
    return <span className="badge" aria-label="Checking replay integrity">
      … checking integrity
    </span>;
  }

  const checks = rep.checks || {};
  const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
  const ag = rep.anti_gaming || {};
  const flags = ag.flags || [];

  if (compact) {
    return (
      <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
        <span className={`badge ${rep.ok ? "ok" : "bad"}`}
              title={rep.ok ? "All integrity checks passed"
                            : `Failed: ${failed.join(", ")}`}>
          {rep.ok ? "✓ verified" : `✗ ${failed.length} failed`}
        </span>
        {!rep.ranking_eligible && (
          <span className="badge warn" title={rep.fallback_policy}>
            unranked
          </span>
        )}
        {flags.length > 0 && (
          <span className="badge warn" title={flags.join(" · ")}>
            ⚠ {flags.length} gaming flag{flags.length > 1 ? "s" : ""}
          </span>
        )}
      </span>
    );
  }

  return (
    <div className="panel" style={{ padding: 14 }}>
      <span className="panel-title">
        <span className="tick" /> Replay Integrity
      </span>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                    margin: "10px 0" }}>
        <span className={`badge ${rep.ok ? "ok" : "bad"}`}>
          {rep.ok ? "✓ reproducible" : "✗ not reproducible"}
        </span>
        <span className={`badge ${rep.ranking_eligible ? "ok" : "warn"}`}>
          {rep.ranking_eligible ? "ranked" : "unranked"}
        </span>
        {rep.seed != null && (
          <span className="badge">seed {rep.seed}</span>
        )}
        {flags.length > 0 && (
          <span className="badge warn">⚠ {flags.length} gaming flag(s)</span>
        )}
      </div>
      <table className="prov-table">
        <tbody>
          <tr>
            <td>benchmark / physics / prompt</td>
            <td>v{rep.benchmark_version} / v{rep.physics_version} /
              v{rep.prompt_version}</td>
          </tr>
          <tr>
            <td>spec fingerprint</td>
            <td><code>{rep.fingerprint}</code></td>
          </tr>
          <tr>
            <td>turns recorded</td>
            <td>{rep.turns}</td>
          </tr>
          <tr>
            <td>fallback policy</td>
            <td>{rep.fallback_policy}</td>
          </tr>
        </tbody>
      </table>
      <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
        {Object.entries(checks).map(([k, v]) => (
          <span key={k} className={`badge ${v ? "ok" : "bad"}`}>
            {v ? "✓" : "✗"} {k.replace(/_/g, " ")}
          </span>
        ))}
      </div>
      {flags.length > 0 && (
        <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 6,
                      border: "1px solid rgba(255, 197, 71, 0.35)",
                      background: "rgba(255, 197, 71, 0.06)",
                      fontSize: 12, color: "var(--dim)", lineHeight: 1.6 }}>
          <b style={{ color: "var(--gold)" }}>Anti-gaming flags.</b>{" "}
          {ag.verdict}
          <ul style={{ margin: "6px 0 0 18px" }}>
            {flags.slice(0, 6).map((f) => <li key={f}>{f}</li>)}
          </ul>
        </div>
      )}
      <p style={{ marginTop: 10, fontSize: 12, color: "var(--dim)",
                  lineHeight: 1.6 }}>
        LLM decisions are not reproducible from a seed — only the physics and
        scripted brains are. Reproducibility here means the stored action log
        plus the seed reconstruct this exact fight.
      </p>
    </div>
  );
}
