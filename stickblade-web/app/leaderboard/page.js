"use client";
import { useEffect, useMemo, useState } from "react";
import LeaderboardTable from "@/components/LeaderboardTable";
import ObjectiveLeaderboardTable from "@/components/ObjectiveLeaderboardTable";
import RatingTable from "@/components/RatingTable";
import ModelStatsTable from "@/components/ModelStatsTable";
import { getLeaderboard, getLeaderboardObjective,
         getLeaderboardBradleyTerry, getModelStats,
         getDataQuality } from "@/lib/api";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import DataQualityBanner from "@/components/DataQuality";

/* Full leaderboard (review items 15, 17, 18, 19, 22).

   Changes from the previous version:
     - every filter group is now made of native <button>s (they were
       div[role=button], which is keyboard- and AT-hostile)
     - an explicit active-filter summary line sits above the table so the
       numbers are never read without their cell
     - the vote table gets the objective rollup for the SAME filter, which
       powers the per-row "Why?" drill-down (N, CI, damage/turn, degraded
       matches) instead of a bare rating
     - "Elo by Vote" is named Human-Voted Elo everywhere, with the tooltip
       that says what it actually measures */

const ZONE_TABS_BY_WEAPON = {
  "":       [["", "Overall"], ["tip", "Tip"], ["edge", "Edge"], ["back_edge", "Back edge"], ["pommel", "Pommel"]],
  sword:    [["", "Overall"], ["tip", "Fencers (tip)"], ["edge", "Sabreurs (edge)"], ["back_edge", "Tricksters (back edge)"], ["pommel", "Brawlers (pommel)"]],
  dagger:   [["", "Overall"], ["tip", "Stabbers (tip)"], ["edge", "Slashers (edge)"], ["pommel", "Punchers (pommel)"]],
  spear:    [["", "Overall"], ["tip", "Pikemen (tip)"], ["shaft", "Polers (shaft)"], ["butt", "Buttwhackers"]],
  flail:    [["", "Overall"], ["ball", "Ball"], ["spikes", "Spikes"], ["chain", "Chain"], ["handle", "Handle"]],
  bow:      [["", "Overall"], ["arrowhead", "Arrowhead"], ["arrow_shaft", "Shaft"], ["bow_limb", "Stave"]],
};

const WEAPON_LABEL = { "": "All weapons", sword: "Sword", dagger: "Dagger",
                       spear: "Spear", flail: "Flail", bow: "Bow" };
const ARENA_LABEL = { "": "All arenas", normal: "Normal", ice: "Ice",
                      low_gravity: "Low G" };

/* One labelled filter row of native buttons. */
function FilterRow({ legend, hint, options, value, onChange, title }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="lbl" id={`legend-${legend}`}>
        {legend}
        {hint && (
          <span style={{ color: "var(--dim)", fontWeight: 400, marginLeft: 6,
                         fontSize: 11, textTransform: "none", letterSpacing: 0 }}>
            — {hint}
          </span>
        )}
      </div>
      <div className="chips" role="group" aria-labelledby={`legend-${legend}`}>
        {options.map(([v, label]) => {
          const on = value === v;
          return (
            <button
              key={String(v)}
              type="button"
              className="chip"
              aria-pressed={on}
              title={title ? title(v) : undefined}
              onClick={() => onChange(v)}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function LeaderboardPage() {
  const [weapon, setWeapon] = useState("");
  const [sharp, setSharp] = useState("");
  const [mode, setMode] = useState("");
  const [arena, setArena] = useState("");
  const [blindfolded, setBlindfolded] = useState(null);
  // §6 expert track: null = every vote (default), "expert"/"casual" =
  // that tier only. Only meaningful for vote-derived ratings, so the
  // control is hidden on the physics-only tabs.
  const [tier, setTier] = useState(null);
  // Tier-S #3: 'perceived' = human-vote Elo (default). 'objective' =
  // proxy metrics (damage_per_turn, hit_rate, etc). Different table
  // component per tab because the columns are totally different.
  // Tier-10 §5: two more tabs. 'bradley_terry' = ratings WITH confidence
  // intervals (Elo has none, and Elo depends on match arrival order);
  // 'metrics' = the full per-model measurement table a methods section
  // has to be able to cite.
  const [tab, setTab] = useState("perceived");
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({});
  // Objective rollup, always fetched: the vote table's "Why?" drill-down
  // reads degraded-match counts from it.
  const [objective, setObjective] = useState({});
  // Data-quality summary for the SAME cell: scripted-only / insufficient
  // real / real. Drives the banner above the table (next-step priority 2).
  const [quality, setQuality] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setErr("");
    setMeta({});
    const bf = blindfolded == null ? undefined : blindfolded;
    const args = [sharp || undefined, weapon || undefined,
                  mode || undefined, arena || undefined, bf];
    const calls = {
      perceived:     () => getLeaderboard(...args).then((r) => [r, {}]),
      objective:     () => getLeaderboardObjective(...args).then((r) => [r, {}]),
      bradley_terry: () => getLeaderboardBradleyTerry(...args, 200, tier)
                             .then((b) => [b.rows, b]),
      metrics:       () => getModelStats(...args).then((m) => [m.rows, m]),
    };
    calls[tab]().then(([r, m]) => { setRows(r); setMeta(m); })
                .catch((e) => setErr(e.message));
    // Always pull the objective rollup too: the vote table's "Why?"
    // drill-down shows degraded-match counts from it.
    getLeaderboardObjective(...args)
      .then((rs) => setObjective(Object.fromEntries(
        (rs || []).map((r) => [r.model, r]))))
      .catch(() => setObjective({}));
    getDataQuality(...args)
      .then((d) => setQuality(d?.summary || null))
      .catch(() => setQuality(null));
  }, [tab, sharp, weapon, mode, arena, blindfolded, tier]);

  // Switching weapon invalidates the sharp filter (zones are per-weapon).
  useEffect(() => { setSharp(""); }, [weapon]);

  const zoneTabs = ZONE_TABS_BY_WEAPON[weapon] || ZONE_TABS_BY_WEAPON[""];
  const zoneLabel = (zoneTabs.find(([z]) => z === sharp) || ["", "Overall"])[1];

  const summary = useMemo(() => [
    WEAPON_LABEL[weapon] || weapon,
    sharp ? `${zoneLabel} sharp` : "any sharp zone",
    mode === "macro" ? "Macro" : mode === "joint" ? "Joint" : "any control mode",
    ARENA_LABEL[arena] || arena,
    blindfolded == null ? "any spatial mode"
      : blindfolded ? "blindfolded" : "normal (with hints)",
  ].join(" · "), [weapon, sharp, zoneLabel, mode, arena, blindfolded]);

  return (
    <>
      <SiteNav />
    <div style={{ width: "100%", maxWidth: 820 }}>
      <h2 style={{ margin: "6px 0 4px",
                   fontFamily: "var(--font-display), system-ui, sans-serif",
                   letterSpacing: 2, textTransform: "uppercase", fontSize: 20 }}>
        Leaderboard
      </h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        {tab === "perceived"
          ? "Human-Voted Elo: ratings reflect human judgements of tactical decision quality, not only match wins. Segmented per weapon, sharp zone, control mode, arena and blindfolded variant — never averaged across them. Ratings under 10 matches are marked provisional; Win% carries a 95% Wilson confidence interval."
          : tab === "objective"
          ? "Objective proxy metrics computed from the raw physics event stream — no human votes involved. Damage-per-turn is the total damage a model deals divided by turns played. Hit-rate is landed / attempted. Fallback-rate is turns where the model timed out or returned malformed JSON."
          : tab === "bradley_terry"
          ? "Bradley–Terry fitted over every voted match in this cell at once, with 95% bootstrap intervals. Unlike Elo it does not depend on the order matches arrived in, and it can say 'these two are not separable'. Models whose intervals overlap share a tie letter — read them as tied, not ranked."
          : "Every metric the benchmark defines, per model: win rate (physics), human preference rate, damage, hit events, lethality, survival, timeouts, invalid actions, fallback turns and latency. Hover any column header for its exact definition."}
      </p>

      <div className="chips" role="group" aria-label="Leaderboard type"
           style={{ marginBottom: 14, borderBottom: "1px solid var(--line)",
                    paddingBottom: 10 }}>
        {[["perceived", "🗳 Human-Voted Elo"],
          ["objective", "📊 Objective metrics"],
          ["bradley_terry", "📐 Bradley–Terry (with CI)"],
          ["metrics", "🔬 Full metrics"]].map(([id, label]) => (
          <button key={id} type="button" className="chip"
                  aria-pressed={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      <div className="panel" style={{ gap: 4 }}>
        <FilterRow legend="Weapon" options={[["", "All"], ["sword", "🗡 Sword"],
          ["dagger", "🔪 Dagger"], ["spear", "🥄 Spear"], ["flail", "⛓ Flail"],
          ["bow", "🏹 Bow"]]} value={weapon} onChange={setWeapon} />
        <FilterRow legend="Sharp zone" options={zoneTabs} value={sharp}
                   onChange={setSharp} />
        <FilterRow legend="Control mode"
                   hint="JOINT is a different task, not a difficulty setting"
                   options={[["", "All"], ["macro", "🎯 Macro"], ["joint", "🧠 Joint"]]}
                   value={mode} onChange={setMode}
                   title={(m) => m === "joint"
                     ? "Model drives every joint raw — totally different task from MACRO"
                     : m === "macro"
                       ? "Model picks tactical moves; engine executes clean swordplay"
                       : "Both modes averaged (aggregate view)"} />
        <FilterRow legend="Arena"
                   options={[["", "All"], ["normal", "🏟 Normal"], ["ice", "❄ Ice"],
                             ["low_gravity", "🌙 Low G"]]}
                   value={arena} onChange={setArena}
                   title={(a) => a === "ice"
                     ? "Slippery floor — fighters slide on impact"
                     : a === "low_gravity"
                       ? "35% gravity — bigger arcs, arrows drop far less"
                       : a === "normal" ? "Standard physics" : "All arenas averaged"} />
        <FilterRow legend="Spatial reasoning"
                   hint="blindfolded strips pre-parsed hints, forces raw-coordinate reasoning"
                   options={[[null, "All"], [false, "🔍 Normal (with hints)"],
                             [true, "🙈 Blindfolded (raw coords only)"]]}
                   value={blindfolded} onChange={setBlindfolded} />
      </div>

      <div className="filter-summary" aria-live="polite" style={{ margin: "12px 0" }}>
        {summary}
      </div>

      {/* --- Evaluator tier (§6) ---
          Shown only on the vote-derived tabs: the physics tables never
          see a vote, so a tier filter there would be a lie. */}
      {tab === "bradley_terry" && (
        <>
          <label className="lbl">
            Evaluator tier
            <span style={{ color: "var(--dim)", fontWeight: 400,
                            marginLeft: 6, fontSize: 11 }}>
              — self-declared at vote time; tiers are never pooled silently
            </span>
          </label>
          <div className="chips" role="group" aria-label="Evaluator tier"
               style={{ marginBottom: 12 }}>
            {[[null, "All votes"],
              ["casual", "🙋 Casual"],
              ["expert", "🎓 Expert (self-declared)"]].map(([v, n]) => (
              <button key={String(v)} type="button" className="chip"
                aria-pressed={tier === v}
                title={v === "expert"
                  ? "Only votes from evaluators who self-identified as experienced. Small n is expected — that is the point of separating it."
                  : v === "casual"
                    ? "Excludes self-declared expert votes"
                    : "Every vote, both tiers pooled"}
                onClick={() => setTier(v)}>
                {n}
              </button>
            ))}
          </div>
        </>
      )}

      <DataQualityBanner summary={quality} cell={summary} />

      {err ? (
        <div className="status" role="alert">✖ {err}</div>
      ) : (
        <div className="panel">
          {tab === "objective"
            ? <ObjectiveLeaderboardTable rows={rows} />
            : tab === "bradley_terry"
            ? <RatingTable rows={rows}
                           comparisons={meta.comparisons}
                           bootstraps={meta.bootstraps} />
            : tab === "metrics"
            ? <ModelStatsTable rows={rows} />
            : (
              <LeaderboardTable
                rows={rows}
                objective={objective}
                emptyAction={
                  <a className="btn btn-sm" href="/"
                     style={{ textDecoration: "none" }}>
                    Start a duel
                  </a>
                }
              />
            )}
        </div>
      )}
    </div>
      <SiteFooter />
    </>
  );
}
