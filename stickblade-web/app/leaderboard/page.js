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
import { MotionSection, SlideIn } from "@/components/MotionSection";

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
              data-press style={{ "--ph": "1.05", "--pt": "0.95" }}
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
  const [tier, setTier] = useState(null);
  const [tab, setTab] = useState("perceived");
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({});
  const [objective, setObjective] = useState({});
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
    getLeaderboardObjective(...args)
      .then((rs) => setObjective(Object.fromEntries(
        (rs || []).map((r) => [r.model, r]))))
      .catch(() => setObjective({}));
    getDataQuality(...args)
      .then((d) => setQuality(d?.summary || null))
      .catch(() => setQuality(null));
  }, [tab, sharp, weapon, mode, arena, blindfolded, tier]);

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
      <div style={{ width: "100%", maxWidth: 820, position: "relative" }}>

        <MotionSection>
          <h2 style={{ margin: "24px 0 4px",
                       fontFamily: "var(--font-display), system-ui, sans-serif",
                       letterSpacing: 0.4, fontSize: 32, fontWeight: 800,
                       color: "var(--text)" }}>
            Leaderboard
          </h2>
        </MotionSection>

        <MotionSection delay={0.05}>
          <p style={{ color: "var(--text-2)", fontSize: 14, marginBottom: 16, lineHeight: 1.7 }}>
            {tab === "perceived"
              ? "Human-Voted Elo: ratings reflect human judgements of tactical decision quality, not only match wins. Segmented per weapon, sharp zone, control mode, arena and blindfolded variant — never averaged across them."
              : tab === "objective"
              ? "Objective proxy metrics computed from the raw physics event stream — no human votes involved. Damage-per-turn is the total damage a model deals divided by turns played. Hit-rate is landed / attempted."
              : tab === "bradley_terry"
              ? "Bradley–Terry fitted over every voted match in this cell at once, with 95% bootstrap intervals. Unlike Elo it does not depend on the order matches arrived in."
              : "Every metric the benchmark defines, per model: win rate, human preference rate, damage, hit events, lethality, survival, timeouts, invalid actions, fallback turns and latency."}
          </p>
        </MotionSection>

        <MotionSection delay={0.1}>
          <div className="chips" role="group" aria-label="Leaderboard type"
               style={{ marginBottom: 14, borderBottom: "1px solid var(--line)",
                        paddingBottom: 10 }}>
            {[["perceived", "🗳 Human-Voted Elo"],
              ["objective", "📊 Objective metrics"],
              ["bradley_terry", "📐 Bradley–Terry (with CI)"],
              ["metrics", "🔬 Full metrics"]].map(([id, label]) => (
              <button key={id} type="button" className="chip"
                      aria-pressed={tab === id} onClick={() => setTab(id)}
                      data-press style={{ "--ph": "1.05", "--pt": "0.95" }}>
                {label}
              </button>
            ))}
          </div>
        </MotionSection>

        <SlideIn direction="up" delay={0.1}>
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
                       hint="blindfolded strips pre-parsed hints"
                       options={[[null, "All"], [false, "🔍 Normal (with hints)"],
                                 [true, "🙈 Blindfolded (raw coords only)"]]}
                       value={blindfolded} onChange={setBlindfolded} />
          </div>
        </SlideIn>

        <MotionSection delay={0.15}>
          <div className="filter-summary" aria-live="polite" style={{ margin: "12px 0" }}>
            {summary}
          </div>
        </MotionSection>

        {tab === "bradley_terry" && (
          <MotionSection delay={0.2}>
            <label className="lbl">
              Evaluator tier
              <span style={{ color: "var(--dim)", fontWeight: 400,
                              marginLeft: 6, fontSize: 11 }}>
                — self-declared at vote time
              </span>
            </label>
            <div className="chips" role="group" aria-label="Evaluator tier"
                 style={{ marginBottom: 12 }}>
              {[[null, "All votes"],
                ["casual", "🙋 Casual"],
                ["expert", "🎓 Expert (self-declared)"]].map(([v, n]) => (
                <button key={String(v)} type="button" className="chip"
                  aria-pressed={tier === v}
                  onClick={() => setTier(v)}
                  data-press style={{ "--ph": "1.05", "--pt": "0.95" }}>
                  {n}
                </button>
              ))}
            </div>
          </MotionSection>
        )}

        <MotionSection delay={0.2}>
          <DataQualityBanner summary={quality} cell={summary} />
        </MotionSection>

        <MotionSection delay={0.25}>
          {err ? (
            <div className="status enter-scale" role="alert">✖ {err}</div>
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
                         style={{ textDecoration: "none", "--ph": "1.05" }}
                         data-press>
                        Start a duel
                      </a>
                    }
                  />
                )}
            </div>
          )}
        </MotionSection>
      </div>
      <SiteFooter />
    </>
  );
}
