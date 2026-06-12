"use client";
import { useEffect, useState } from "react";
import LeaderboardTable from "@/components/LeaderboardTable";
import { getLeaderboard } from "@/lib/api";

const TABS = [
  ["", "Overall"],
  ["tip", "Fencers (tip)"],
  ["edge", "Sabreurs (edge)"],
  ["back_edge", "Tricksters (back edge)"],
  ["pommel", "Brawlers (pommel)"],
];

export default function LeaderboardPage() {
  const [sharp, setSharp] = useState("");
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    getLeaderboard(sharp || undefined)
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, [sharp]);

  return (
    <div style={{ width: "100%", maxWidth: 760 }}>
      <h2 style={{ margin: "6px 0 4px" }}>Leaderboard</h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        Elo from blind human votes — tracked separately per weapon rule.
        A model that wins with a sharp tip is a fencer; winning with only a
        sharp pommel takes a whole different strategy.
      </p>
      <div className="zones" style={{ marginBottom: 12 }}>
        {TABS.map(([z, name]) => (
          <div key={z}
            className={"zone" + (sharp === z ? " on" : "")}
            onClick={() => setSharp(z)}>
            {name}
          </div>
        ))}
      </div>
      {err
        ? <div className="status">✖ {err}</div>
        : <div className="panel"><LeaderboardTable rows={rows} /></div>}
    </div>
  );
}
