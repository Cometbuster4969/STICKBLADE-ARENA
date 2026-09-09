"use client";

/**
 * Full per-model metric table (action-plan §5).
 *
 * The objective tab shows the headline proxies; this is the complete
 * measurement set a methods section has to be able to point at. Every
 * column is sortable, and every column carries a tooltip saying exactly
 * how it is computed — including the two that are routinely misread:
 * hit_rate can exceed 1.0 (contact events per decision, not accuracy) and
 * lethal_rate counts only kills, so an attrition fighter legitimately
 * shows lethal_rate 0 with a high win rate.
 */
import { useState } from "react";
import { EvidenceChip } from "@/components/DataQuality";

const COLUMNS = [
  { key: "matches",            label: "N",         help: "Completed matches (both sides), voted or not" },
  { key: "win_rate",           label: "Win",       help: "Physics win rate: wins / (wins + losses). Draws excluded from both numerator and denominator." },
  { key: "preference_rate",    label: "Pref",      help: "Human preference: wins + half the draws, over voted matches only. Null when nobody voted." },
  { key: "voted_matches",      label: "Votes",     help: "Matches in this cell that received at least one human vote" },
  { key: "damage_per_turn",    label: "Dmg/turn",  help: "Total damage dealt / total turns played" },
  { key: "hit_rate",           label: "Hits/atk",  help: "Hit events / attack decisions. NOT accuracy: one decision can produce several contact events, so macro bouts can exceed 1.0" },
  { key: "lethal_rate",        label: "Lethal",    help: "Fraction of matches this model KILLED its opponent. Winning on HP attrition is not a kill." },
  { key: "survival_rate",      label: "Survived",  help: "Fraction of matches this model did not die in" },
  { key: "timeout_rate",       label: "Timeout",   help: "Fraction of matches that hit the turn cap (no winner by damage or kill)" },
  { key: "invalid_action_rate", label: "Invalid",  help: "Malformed or illegal actions / turns played. High values mean the model is not parsing the state." },
  { key: "fallback_rate",      label: "Fallback",  help: "Turns where the provider timed out or returned unusable output, over turns played" },
  { key: "latency_ms_mean",    label: "Latency",   help: "Mean provider round-trip per decision (ms). Mock fighters are ~0." },
];

const PCT = new Set(["win_rate", "preference_rate", "lethal_rate",
                     "survival_rate", "timeout_rate",
                     "invalid_action_rate", "fallback_rate"]);

function fmt(key, v) {
  if (v == null) return "—";
  if (PCT.has(key)) return `${Math.round(v * 100)}%`;
  if (key === "hit_rate" || key === "damage_per_turn") return Number(v).toFixed(2);
  if (key === "latency_ms_mean") return `${Math.round(v)}ms`;
  return v;
}

export default function ModelStatsTable({ rows }) {
  const [sortKey, setSortKey] = useState("win_rate");
  const [sortDir, setSortDir] = useState("desc");

  if (!rows?.length) {
    return (
      <div style={{ color: "var(--dim)", fontSize: 13, padding: "18px 4px", textAlign: "center" }}>
        no completed matches in this cell yet
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey] ?? -1;
    const vb = b[sortKey] ?? -1;
    return sortDir === "desc" ? vb - va : va - vb;
  });

  const toggle = (k) => {
    if (sortKey === k) setSortDir(sortDir === "desc" ? "asc" : "desc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <thead>
          <tr>
            <th>Model</th>
            <th title="Who actually made the decisions: real providers, a mix, or scripted baselines. Hover a chip for counts.">Evidence</th>
            {COLUMNS.map((c) => (
              <th key={c.key} className="r" title={c.help}
                  onClick={() => toggle(c.key)}
                  style={{ cursor: "pointer",
                           color: sortKey === c.key ? "var(--gold, #d4b962)" : undefined }}>
                {c.label}
                {sortKey === c.key && (
                  <span style={{ marginLeft: 3 }}>{sortDir === "desc" ? "↓" : "↑"}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.model}>
              <td className="model">{r.name || r.model}</td>
              <td><EvidenceChip dq={r.data_quality} compact /></td>
              {COLUMNS.map((c) => {
                const v = r[c.key];
                const warn = (c.key === "invalid_action_rate" && (v ?? 0) > 0.1)
                          || (c.key === "fallback_rate" && (v ?? 0) > 0.25);
                return (
                  <td key={c.key} className="r"
                      style={warn ? { color: "var(--red-2)" }
                                  : { color: "var(--dim)" }}>
                    {fmt(c.key, v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 10,
                    padding: "0 4px", letterSpacing: 0.3, lineHeight: 1.7 }}>
        Click any column header to sort. Hover a header for its exact
        definition. <b>Win</b> is decided by the physics engine;
        <b> Pref</b> is decided by human votes, so they can disagree — that
        gap is a finding, not an error.
      </div>
    </div>
  );
}
