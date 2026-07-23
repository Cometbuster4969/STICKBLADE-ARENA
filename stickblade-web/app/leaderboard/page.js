"use client";
import { useEffect, useId, useState } from "react";
import LeaderboardTable from "@/components/LeaderboardTable";
import { getLeaderboard } from "@/lib/api";

const ZONE_TABS_BY_WEAPON = {
  "":       [["", "Overall"], ["tip", "Tip"], ["edge", "Edge"], ["back_edge", "Back edge"], ["pommel", "Pommel"]],
  sword:    [["", "Overall"], ["tip", "Fencers (tip)"], ["edge", "Sabreurs (edge)"], ["back_edge", "Tricksters (back edge)"], ["pommel", "Brawlers (pommel)"]],
  dagger:   [["", "Overall"], ["tip", "Stabbers (tip)"], ["edge", "Slashers (edge)"], ["pommel", "Punchers (pommel)"]],
  spear:    [["", "Overall"], ["tip", "Pikemen (tip)"], ["shaft", "Polers (shaft)"], ["butt", "Buttwhackers"]],
  flail:    [["", "Overall"], ["ball", "Ball"], ["spikes", "Spikes"], ["chain", "Chain"], ["handle", "Handle"]],
  bow:      [["", "Overall"], ["arrowhead", "Arrowhead"], ["arrow_shaft", "Shaft"], ["bow_limb", "Stave"]],
};

export default function LeaderboardPage() {
  const [weapon, setWeapon] = useState("");
  const [sharp, setSharp] = useState("");
  // Tier-S commit 2: mode + arena are first-class eval axes. "" = don't
  // filter (aggregate across the axis when combined with other filters,
  // or per-cell rows when at least one filter is set).
  const [mode, setMode] = useState("");
  const [arena, setArena] = useState("");
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const wId = useId();

  useEffect(() => {
    getLeaderboard(sharp || undefined, weapon || undefined,
                   mode || undefined, arena || undefined)
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, [sharp, weapon, mode, arena]);

  // If the user switches weapon, drop the sharp filter so we don't request a
  // (weapon, sharp) combo that doesn't exist for the new weapon.
  useEffect(() => { setSharp(""); }, [weapon]);

  const zoneTabs = ZONE_TABS_BY_WEAPON[weapon] || ZONE_TABS_BY_WEAPON[""];

  return (
    <div style={{ width: "100%", maxWidth: 760 }}>
      <h2 style={{ margin: "6px 0 4px" }}>Leaderboard</h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        Elo from blind human votes — tracked separately per weapon, sharp zone,
        control mode, AND arena. A model that dominates macro-mode swordplay
        may collapse in joint-mode or on the ice arena. The uncertainty
        column shows the 95% Wilson CI on win-rate; rows under N=10 are
        marked provisional (?) to prevent over-reading small-sample noise.
      </p>

      <label htmlFor={wId} className="lbl">Weapon</label>
      <div className="zones" style={{ marginBottom: 12 }} id={wId}>
        {[["", "All"], ["sword", "🗡 Sword"], ["dagger", "🔪 Dagger"],
          ["spear", "⊥ Spear"], ["flail", "⛓ Flail"], ["bow", "🏹 Bow"]].map(([w, n]) => (
          <div key={w}
            role="button" tabIndex={0} aria-pressed={weapon === w}
            className={"zone" + (weapon === w ? " on" : "")}
            onClick={() => setWeapon(w)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setWeapon(w); } }}>
            {n}
          </div>
        ))}
      </div>

      <label className="lbl">Sharp zone</label>
      <div className="zones" style={{ marginBottom: 12 }}>
        {zoneTabs.map(([z, name]) => (
          <div key={z}
            role="button" tabIndex={0} aria-pressed={sharp === z}
            className={"zone" + (sharp === z ? " on" : "")}
            onClick={() => setSharp(z)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSharp(z); } }}>
            {name}
          </div>
        ))}
      </div>

      <label className="lbl">Control mode</label>
      <div className="zones" style={{ marginBottom: 12 }}>
        {[["", "All"], ["macro", "🎯 MACRO"], ["joint", "🧠 JOINT"]].map(([m, n]) => (
          <div key={m}
            role="button" tabIndex={0} aria-pressed={mode === m}
            className={"zone" + (mode === m ? " on" : "")}
            title={m === "joint"
              ? "LLM drives every joint raw — totally different task from MACRO"
              : m === "macro"
                ? "LLM picks tactical moves; engine executes clean swordplay"
                : "Both modes averaged (aggregate view)"}
            onClick={() => setMode(m)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setMode(m); } }}>
            {n}
          </div>
        ))}
      </div>

      <label className="lbl">Arena</label>
      <div className="zones" style={{ marginBottom: 12 }}>
        {[["", "All"], ["normal", "🏟 Normal"], ["ice", "❄ Ice"],
          ["low_gravity", "🌙 Low G"]].map(([a, n]) => (
          <div key={a}
            role="button" tabIndex={0} aria-pressed={arena === a}
            className={"zone" + (arena === a ? " on" : "")}
            title={a === "ice"
              ? "Slippery floor — fighters slide on impact"
              : a === "low_gravity"
                ? "Moon-ish gravity — bigger arcs, slower falls"
                : a === "normal"
                  ? "Standard physics"
                  : "All arenas averaged"}
            onClick={() => setArena(a)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setArena(a); } }}>
            {n}
          </div>
        ))}
      </div>

      {err
        ? <div className="status">✖ {err}</div>
        : <div className="panel"><LeaderboardTable rows={rows} /></div>}
    </div>
  );
}
