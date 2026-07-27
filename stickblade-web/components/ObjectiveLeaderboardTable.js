"use client";

/**
 * Objective-skill leaderboard table (Tier-S #3).
 *
 * Different columns from the perceived-skill (vote-based Elo) table
 * because it ranks on physics-derived metrics, not human preference.
 * Sortable by any metric; damage_per_turn is the default because it's
 * the closest single-number to "was this model good".
 *
 * Provisional threshold is HIGHER here (N < 5 matches) than the vote
 * table's N < 10 because these are objective per-match measurements
 * — noise is per-match variance not per-vote variance — but ratings
 * are still small-sample under 5 matches.
 */
const PROVISIONAL_N = 5;

import { useState } from "react";

const COLUMNS = [
  { key: "matches",         label: "N",     help: "Total completed matches (both sides)" },
  { key: "damage_per_turn", label: "Dmg/turn", help: "Total damage dealt divided by total turns played" },
  { key: "hit_rate",        label: "Hit %", help: "Landed hits ÷ attempted hits (defensive actions excluded)" },
  { key: "fallback_rate",   label: "Fallback %", help: "Turns where LLM timed out or returned bad JSON. Lower = better." },
  { key: "avg_distance",    label: "Avg dist", help: "Mean torso-torso distance across match (px). Roughly: aggressive vs kite-y." },
  { key: "wins",            label: "W",     help: "Match wins (by damage-dealt, physics-authoritative)" },
  { key: "losses",          label: "L",     help: "Match losses" },
];

export default function ObjectiveLeaderboardTable({ rows }) {
  const [sortKey, setSortKey] = useState("damage_per_turn");
  const [sortDir, setSortDir] = useState("desc");

  if (!rows?.length) {
    return (
      <div style={{ color: "var(--dim)", fontSize: 13, padding: "18px 4px", textAlign: "center" }}>
        no matches with proxy metrics yet — this leaderboard populates as
        new matches finish under Tier-S #3
      </div>
    );
  }

  // Sort in-place (copy) by the selected key.
  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey] ?? 0;
    const vb = b[sortKey] ?? 0;
    return sortDir === "desc" ? vb - va : va - vb;
  });

  const toggleSort = (k) => {
    if (sortKey === k) setSortDir(sortDir === "desc" ? "asc" : "desc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  const fmt = (k, v) => {
    if (v == null) return "—";
    if (k === "hit_rate" || k === "fallback_rate")
      return `${Math.round(v * 100)}%`;
    if (k === "damage_per_turn" || k === "avg_distance")
      return Number(v).toFixed(1);
    return v;
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            {COLUMNS.map((c) => (
              <th key={c.key} className="r"
                  onClick={() => toggleSort(c.key)}
                  title={c.help}
                  style={{ cursor: "pointer",
                            color: sortKey === c.key ? "var(--gold, #d4b962)" : undefined }}>
                {c.label}
                {sortKey === c.key && (
                  <span style={{ marginLeft: 3 }}>
                    {sortDir === "desc" ? "↓" : "↑"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const rank = i + 1;
            const provisional = (r.matches || 0) < PROVISIONAL_N;
            return (
              <tr key={r.model}
                  className={rank === 1 ? "rank-1" : ""}
                  style={provisional ? { opacity: 0.75 } : undefined}>
                <td>{rank}</td>
                <td className="model">
                  {r.name || r.model}
                  {provisional && (
                    <span title={`Provisional — only ${r.matches} match${r.matches === 1 ? "" : "es"}. Needs ≥${PROVISIONAL_N}.`}
                          style={{ marginLeft: 6, fontSize: "0.72em",
                                    padding: "1px 5px", borderRadius: 3,
                                    background: "rgba(212,185,98,0.15)",
                                    color: "var(--gold, #d4b962)",
                                    fontWeight: 700, letterSpacing: 1 }}>
                      ?
                    </span>
                  )}
                </td>
                {COLUMNS.map((c) => (
                  <td key={c.key} className="r"
                      style={c.key === "wins" ? { color: "var(--green)" }
                           : c.key === "losses" ? { color: "var(--red-2)" }
                           : c.key === "fallback_rate" && (r.fallback_rate || 0) > 0.1
                             ? { color: "var(--red-2)" }
                           : { color: "var(--dim)" }}>
                    {fmt(c.key, r[c.key])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 10,
                    padding: "0 4px", letterSpacing: 0.3, lineHeight: 1.7 }}>
        <b style={{ color: "var(--gold, #d4b962)" }}>?</b> = provisional
        (N &lt; {PROVISIONAL_N} matches). Click any column header to sort.
        Wins attributed by higher damage-dealt (physics-authoritative,
        independent of the human-vote canvas).
      </div>
    </div>
  );
}
