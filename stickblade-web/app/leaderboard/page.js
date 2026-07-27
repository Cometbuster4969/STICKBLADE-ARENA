"use client";
import { useEffect, useId, useState } from "react";
import LeaderboardTable from "@/components/LeaderboardTable";
import ObjectiveLeaderboardTable from "@/components/ObjectiveLeaderboardTable";
import { getLeaderboard, getLeaderboardObjective } from "@/lib/api";

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
  const [mode, setMode] = useState("");
  const [arena, setArena] = useState("");
  // Tier-S #3: blindfolded is the 5th eval axis. null = don't filter,
  // false = only normal-mode matches, true = only blindfolded matches.
  const [blindfolded, setBlindfolded] = useState(null);
  // Tier-S #3: 'perceived' = human-vote Elo (default). 'objective' =
  // proxy metrics (damage_per_turn, hit_rate, etc). Different table
  // component per tab because the columns are totally different.
  const [tab, setTab] = useState("perceived");
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const wId = useId();

  useEffect(() => {
    setErr("");
    const bf = blindfolded == null ? undefined : blindfolded;
    const fetcher = tab === "objective"
      ? getLeaderboardObjective
      : getLeaderboard;
    fetcher(sharp || undefined, weapon || undefined,
            mode || undefined, arena || undefined, bf)
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, [tab, sharp, weapon, mode, arena, blindfolded]);

  // If the user switches weapon, drop the sharp filter so we don't request a
  // (weapon, sharp) combo that doesn't exist for the new weapon.
  useEffect(() => { setSharp(""); }, [weapon]);

  const zoneTabs = ZONE_TABS_BY_WEAPON[weapon] || ZONE_TABS_BY_WEAPON[""];

  return (
    <div style={{ width: "100%", maxWidth: 760 }}>
      <h2 style={{ margin: "6px 0 4px" }}>Leaderboard</h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        {tab === "perceived"
          ? "Elo from blind human votes. Segmented per weapon, sharp zone, control mode, arena, and blindfolded variant. The '?' flag marks provisional ratings (N<10) so small-sample noise isn't over-read. Win% column shows the 95% Wilson CI."
          : "Objective proxy metrics computed from the raw physics event stream — no human votes involved. Damage-per-turn is the total damage a model deals divided by turns played. Hit-rate is landed / attempted (defensive actions excluded). Fallback-rate is turns where the LLM timed out or returned malformed JSON."}
      </p>

      {/* --- Perceived vs Objective tab toggle (Tier-S #3) --- */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14,
                    borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
        {[["perceived", "🗳 Perceived Skill (human vote)"],
          ["objective", "📊 Objective Skill (proxy metrics)"]].map(([id, label]) => (
          <button key={id}
            onClick={() => setTab(id)}
            style={{
              cursor: "pointer",
              padding: "6px 14px",
              background: tab === id ? "var(--panel)" : "transparent",
              border: `1px solid ${tab === id ? "var(--gold, #d4b962)" : "var(--line)"}`,
              borderRadius: 4,
              color: tab === id ? "var(--gold, #d4b962)" : "var(--text-2)",
              fontWeight: tab === id ? 700 : 500,
              fontSize: 13, letterSpacing: 0.3,
            }}>
            {label}
          </button>
        ))}
      </div>

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

      {/* --- Blindfolded filter (Tier-S #3) ---
          Three-state: All / Normal-only / Blindfolded-only. Blindfolded
          matches strip derived spatial hints so the model reasons from
          raw coords — a totally different eval axis. Uses null (not "")
          for the 'All' sentinel because false is a meaningful filter
          value (only-normal rows). */}
      <label className="lbl">
        Spatial reasoning
        <span style={{ color: "var(--dim)", fontWeight: 400, marginLeft: 6,
                        fontSize: 11 }}>
          — blindfolded matches strip pre-parsed hints, force raw-coord reasoning
        </span>
      </label>
      <div className="zones" style={{ marginBottom: 16 }}>
        {[[null, "All"],
          [false, "🔍 Normal (with hints)"],
          [true,  "🙈 Blindfolded (raw coords only)"]].map(([v, n]) => (
          <div key={String(v)}
            role="button" tabIndex={0} aria-pressed={blindfolded === v}
            className={"zone" + (blindfolded === v ? " on" : "")}
            title={v === true
              ? "State strips facing_enemy + higher/lower/level + distance — model must derive from coords"
              : v === false
                ? "Standard state with pre-parsed spatial hints (baseline v1 prompt)"
                : "Both blindfolded + normal averaged"}
            onClick={() => setBlindfolded(v)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setBlindfolded(v); } }}>
            {n}
          </div>
        ))}
      </div>

      {err
        ? <div className="status">✖ {err}</div>
        : <div className="panel">
            {tab === "objective"
              ? <ObjectiveLeaderboardTable rows={rows} />
              : <LeaderboardTable rows={rows} />}
          </div>}
    </div>
  );
}
