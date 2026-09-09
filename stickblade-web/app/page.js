"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ModelPicker, { CUSTOM } from "@/components/ModelPicker";
import ReplayPlayer from "@/components/ReplayPlayer";
import TurnTranscript from "@/components/TurnTranscript";
import LeaderboardTable from "@/components/LeaderboardTable";
import WaitPanel from "@/components/WaitPanel";
import ByokPanel from "@/components/ByokPanel";
import OnboardingCard from "@/components/OnboardingCard";
import SharpZonePicker from "@/components/SharpZonePicker";
import { WeaponPicker, ArenaPicker, WEAPON_INFO, ARENA_INFO } from "@/components/OptionCards";
import { PredictPanel, RevealPanel } from "@/components/JudgePanels";
// Our VotePanel, not JudgePanels': this one collects the optional
// execution / entertainment / deserved axes, the 1-5 confidence rating and
// the self-declared evaluator tier (action-plan §6). Only the tactical
// choice moves a rating, but the other axes are what let the dataset
// separate "fought intelligently" from "was fun to watch".
import VotePanel from "@/components/VotePanel";
import SampleFight from "@/components/SampleFight";
import IntegrityBadge from "@/components/IntegrityBadge";
import FAQ from "@/components/FAQ";
import { readByokKey, readByokEnabled } from "@/lib/byok";
import { getModels, createMatch, getMatch, getReplay, postVote,
         getLeaderboard, getLeaderboardObjective, startKeepalive,
         getIntegrity, getDataQuality } from "@/lib/api";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import DataQualityBanner from "@/components/DataQuality";

/* Fight page — restructured around one workflow (review items 1, 2, 6, 23):

     CONFIGURE  ->  OBSERVE  ->  JUDGE BLIND  ->  REVEAL  ->  INSPECT

   Setup is split into numbered sections (Fighters / Fight Rules /
   Evaluation mode / Advanced) instead of one flat column of equal-weight
   controls, "Run recommended duel" fills every field with sane defaults in
   one click, and terminology is fixed: models are "Model 1"/"Model 2" until
   the fight starts, then they are only ever "Fighter A"/"Fighter B" until
   the reveal names them. */

const WEAPON_ZONES = {
  sword:  ["tip", "edge", "back_edge", "pommel"],
  dagger: ["tip", "edge", "back_edge", "pommel"],
  spear:  ["tip", "shaft", "butt"],
  flail:  ["ball", "spikes", "chain", "handle"],
  bow:    ["arrowhead", "arrow_shaft", "bow_limb"],
};

const ZONE_TITLE = {
  tip: "Tip sharp", edge: "Edge sharp", back_edge: "Back edge sharp",
  pommel: "Pommel sharp", shaft: "Shaft sharp", butt: "Butt sharp",
  ball: "Ball sharp", spikes: "Spikes sharp", chain: "Chain sharp",
  handle: "Handle sharp", arrowhead: "Arrowhead sharp",
  arrow_shaft: "Arrow shaft sharp", bow_limb: "Bow limb sharp",
};

// ----- predict-streak + accuracy (localStorage) -----------------------------
const STREAK_KEY = "sba.predictStreak";
const STREAK_BEST_KEY = "sba.predictBest";
const PREDICT_WINS_KEY = "sba.predictWins";
const PREDICT_TOTAL_KEY = "sba.predictTotal";

function readStreak() {
  if (typeof window === "undefined") return { cur: 0, best: 0, wins: 0, total: 0 };
  try {
    return {
      cur:   parseInt(localStorage.getItem(STREAK_KEY) || "0", 10),
      best:  parseInt(localStorage.getItem(STREAK_BEST_KEY) || "0", 10),
      wins:  parseInt(localStorage.getItem(PREDICT_WINS_KEY) || "0", 10),
      total: parseInt(localStorage.getItem(PREDICT_TOTAL_KEY) || "0", 10),
    };
  } catch {
    return { cur: 0, best: 0, wins: 0, total: 0 };
  }
}
function writeStreak(cur, best, wins, total) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STREAK_KEY, String(cur));
    localStorage.setItem(STREAK_BEST_KEY, String(best));
    if (wins != null) localStorage.setItem(PREDICT_WINS_KEY, String(wins));
    if (total != null) localStorage.setItem(PREDICT_TOTAL_KEY, String(total));
  } catch {}
}

const WORKFLOW = [
  ["configure", "Configure", "pick two models"],
  ["observe",   "Watch",     "live physics"],
  ["judge",     "Vote blind", "who fought smarter"],
  ["inspect",   "Reveal",    "names, Elo, integrity"],
];

export default function Home() {
  const [models, setModels] = useState([]);
  const [m1, setM1] = useState("");
  const [m2, setM2] = useState("");
  const [custom1, setCustom1] = useState("");
  const [custom2, setCustom2] = useState("");
  const [sharp, setSharp] = useState(["tip"]);
  const [weapon, setWeapon] = useState("sword");
  const [mode, setMode] = useState("macro");
  const [arena, setArena] = useState("normal");
  const [blindfolded, setBlindfolded] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [allowSelfPlay, setAllowSelfPlay] = useState(false);

  const [matchId, setMatchId] = useState(null);
  const [status, setStatus] = useState("idle");     // idle|submitting|running|ready
  const [error, setError] = useState(null);
  const [replay, setReplay] = useState(null);
  const [voteChoice, setVoteChoice] = useState(null);
  const [voteResult, setVoteResult] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  // Evidence level of the sidebar cell (scripted-only / insufficient /
  // real) — the compact table carries per-row chips, this is the banner.
  const [quality, setQuality] = useState(null);
  // ---- benchmark spec v1.0 controls (§1) ----
  // Match length, fallback policy and seed are part of the frozen spec:
  // they decide whether a result is comparable with anything else, and
  // they travel in the match's provenance record.
  const [matchLength, setMatchLength] = useState("standard");
  const [fallbackPolicy, setFallbackPolicy] = useState("operational");
  const [seed, setSeed] = useState("");
  // §8: replay integrity audit for the match just watched.
  const [integrity, setIntegrity] = useState(null);
  // §3: sample-fight modal.
  const [showSample, setShowSample] = useState(false);
  const [objective, setObjective] = useState({});
  const [prediction, setPrediction] = useState(null);
  const [streak, setStreak] = useState({ cur: 0, best: 0, wins: 0, total: 0 });
  const [lastPredWasCorrect, setLastPredWasCorrect] = useState(null);

  const setupRef = useRef(null);

  // Keep the backend awake while this tab is open (cold-start mitigation).
  useEffect(() => startKeepalive(), []);

  useEffect(() => {
    getModels().then((ms) => {
      setModels(ms);
      const real = ms.filter((m) => !m.no_api);
      const pool = real.length >= 2 ? real : ms;
      setM1((prev) => prev || pool[0]?.id || "");
      setM2((prev) => prev || pool[1]?.id || "");
    }).catch((e) => setError(e.message));
    setStreak(readStreak());
  }, []);

  const filterKey = useMemo(
    () => [sharp.join(","), weapon, mode, arena, blindfolded].join("|"),
    [sharp, weapon, mode, arena, blindfolded]
  );

  useEffect(() => {
    const [sh, wp, md, ar, bf] = filterKey.split("|");
    getLeaderboard(sh, wp, md, ar, bf === "true")
      .then(setLeaderboard).catch(() => setLeaderboard([]));
    getLeaderboardObjective(sh, wp, md, ar, bf === "true")
      .then((rows) => setObjective(Object.fromEntries(
        (rows || []).map((r) => [r.model, r]))))
      .catch(() => setObjective({}));
    getDataQuality(sh, wp, md, ar, bf === "true")
      .then((d) => setQuality(d?.summary || null))
      .catch(() => setQuality(null));
  }, [filterKey]);

  const pickWeapon = (w) => {
    setWeapon(w);
    setSharp([WEAPON_ZONES[w][0]]);      // zones are weapon-specific
  };

  const toggleSharp = (z) => {
    setSharp((prev) => {
      const next = prev.includes(z) ? prev.filter((x) => x !== z) : [...prev, z];
      return next.length === 0 ? [z] : next;   // never zero sharp zones
    });
  };

  const modelA = m1 === CUSTOM ? custom1.trim() : m1;
  const modelB = m2 === CUSTOM ? custom2.trim() : m2;
  const meta1 = models.find((m) => m.id === m1);
  const meta2 = models.find((m) => m.id === m2);
  const sameModel = Boolean(modelA) && modelA === modelB;
  const ready = Boolean(modelA && modelB) && (!sameModel || allowSelfPlay);
  const isBusy = status === "submitting" || status === "running";

  // Worst-case wall clock, derived from the per-model turn budgets the
  // backend actually enforces (brains._timeout_for). Shown as an upper
  // bound next to the honest "usually 45-90s" so nobody reads a slow
  // reasoning model as a hang.
  const worstCaseMin = useMemo(() => {
    const perTurn = (meta1?.est_turn_s || 0) + (meta2?.est_turn_s || 0) + 3;
    if (!perTurn || perTurn <= 3) return null;
    return Math.max(1, Math.ceil((perTurn * 12) / 60));
  }, [meta1, meta2]);

  const stage = voteResult ? "inspect"
    : replay ? "judge"
    : isBusy ? "observe"
    : "configure";

  const resetMatchState = () => {
    setMatchId(null);
    setStatus("idle");
    setReplay(null);
    setVoteChoice(null);
    setVoteResult(null);
    setPrediction(null);
    setLastPredWasCorrect(null);
    setError(null);
  };

  const launch = useCallback(async () => {
    setError(null);
    setReplay(null);
    setVoteChoice(null);
    setVoteResult(null);
    setPrediction(null);
    setLastPredWasCorrect(null);
    setStatus("submitting");
    if (!modelA || !modelB) {
      setError("Pick two models first.");
      setStatus("idle");
      return;
    }
    try {
      const byok = (readByokEnabled() && readByokKey()) ? { api_key: readByokKey() } : {};
      const res = await createMatch({
        model_a: modelA, model_b: modelB, sharp, blind: true,
        mode, weapon, arena, blindfolded, ...byok,
        // Frozen-spec fields. Seeded matches are reproducible from the
        // stored action log; empty input means unseeded (casual default).
        match_length: matchLength,
        fallback_policy: fallbackPolicy,
        seed: seed === "" ? null : Number(seed),
      });
      setMatchId(res.match_id);
      setStatus("running");
    } catch (e) {
      setError(e.message);
      setStatus("idle");
    }
  }, [modelA, modelB, sharp, mode, weapon, arena, blindfolded]);

  // WaitPanel owns the polling; it calls back when the replay is ready.
  const handleReady = useCallback(async (id, err) => {
    if (err || !id) {
      setError(err || "Match simulation failed.");
      setStatus("idle");
      setMatchId(null);
      return;
    }
    try {
      const r = await getReplay(id);
      setReplay(r);
      setStatus("ready");
      // Replay integrity audit (§8) — 8 checks on provenance, seed, action
      // log and reproducibility. Shown next to the replay so a viewer can
      // see whether this result is auditable, not just watchable.
      getIntegrity(id).then(setIntegrity).catch(() => setIntegrity(null));
    } catch (e) {
      setError(e.message);
      setStatus("idle");
    }
  }, []);

  const runRecommended = () => {
    // Fastest two models on the free tier that aren't currently throttled.
    // The point of the button is "get me a fight now", so latency beats
    // capability here — and it's honest about what it picked.
    const pool = models
      .filter((m) => !m.no_api && m.cooldown_s === 0)
      .sort((a, b) => a.est_turn_s - b.est_turn_s);
    if (pool.length >= 2) {
      setM1(pool[0].id);
      setM2(pool[1].id);
    } else if (models.length >= 2) {
      setM1(models[0].id);
      setM2(models[1].id);
    }
    setWeapon("sword");
    setSharp(["tip"]);
    setMode("macro");
    setArena("normal");
    setBlindfolded(false);
    setAllowSelfPlay(false);
    setError(null);
    setupRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // `extra` carries the optional axes (execution / entertainment /
  // deserved), the 1-5 confidence rating and voter_tier (§6). They are
  // stored with the vote; none of them move a rating.
  const vote = async (choice, extra) => {
    if (!matchId) return;
    setVoteChoice(choice);
    try {
      const res = await postVote(matchId, choice, extra || {});
      setVoteResult(res);

      if (prediction) {
        const engineWinner = replay?.meta?.winner?.startsWith("Fighter A") ? "a"
          : replay?.meta?.winner?.startsWith("Fighter B") ? "b" : "draw";
        const correct = prediction === engineWinner;
        setLastPredWasCorrect(correct);
        const newCur = correct ? streak.cur + 1 : 0;
        const newBest = Math.max(streak.best, newCur);
        const newWins = (streak.wins || 0) + (correct ? 1 : 0);
        const newTotal = (streak.total || 0) + 1;
        const next = { cur: newCur, best: newBest, wins: newWins, total: newTotal };
        setStreak(next);
        writeStreak(newCur, newBest, newWins, newTotal);
      }
      const [sh, wp, md, ar, bf] = filterKey.split("|");
      getLeaderboard(sh, wp, md, ar, bf === "true").then(setLeaderboard).catch(() => {});
      getLeaderboardObjective(sh, wp, md, ar, bf === "true")
        .then((rows) => setObjective(Object.fromEntries(
          (rows || []).map((r) => [r.model, r]))))
        .catch(() => {});
    } catch (e) {
      setVoteChoice(null);
      setError(e.message);
    }
  };

  const filterSummary = [
    `${WEAPON_INFO[weapon]?.label || weapon}`,
    sharp.map((z) => ZONE_TITLE[z] || z).join(" + "),
    mode === "macro" ? "Macro" : "Joint",
    ARENA_INFO[arena]?.label || arena,
    blindfolded ? "Blindfolded" : null,
  ].filter(Boolean).join(" · ");

  const integrityNote = replay?.meta?.fallback_turns > 0
    ? `Heads up: ${replay.meta.fallback_turns} of ${replay.meta.total_turns || "?"} turns used the scripted fallback, so parts of this fight were not model play.`
    : null;

  return (
    <>
      <SiteNav />
      {/* ---------- Workflow strip: what to do, in order ---------- */}
      <section className="workflow" aria-label="How a duel works">
        {WORKFLOW.map(([key, title, sub], i) => (
          <div className="workflow-step" key={key} data-active={stage === key}>
            <span className="n">{i + 1}</span>
            <span>
              <div className="t">{title}</div>
              <div className="s">{sub}</div>
            </span>
          </div>
        ))}
      </section>

      <OnboardingCard />

      {error && (
        <div className="panel" style={{ borderColor: "var(--red)" }} role="alert">
          <b style={{ color: "var(--red-2)" }}>Error:</b> {error}
        </div>
      )}

      {/* ================= CONFIGURE ================= */}
      <div ref={setupRef} className="panel setup-step">
        <div className="step-head">
          <span className="step-num">1</span>
          <span className="step-title">Fighters</span>
          <span className="step-desc">
            Two language models. Canvas colours are randomised per match, so
            you cannot tell which is which while watching.
          </span>
        </div>
        <div className="row">
          <ModelPicker
            label="Model 1" slotIndex={1} models={models} value={m1}
            custom={custom1} onChange={(v) => { setM1(v); setAllowSelfPlay(false); }}
            onCustomChange={setCustom1} mode={mode}
          />
          <ModelPicker
            label="Model 2" slotIndex={2} models={models} value={m2}
            custom={custom2} onChange={(v) => { setM2(v); setAllowSelfPlay(false); }}
            onCustomChange={setCustom2} mode={mode}
          />
        </div>
        {sameModel && (
          <div className="stalled">
            <p>
              <b>Both slots point at the same model.</b> That is a mirror match —
              legal, but the two fighters will play identically and the vote
              tells you little.
            </p>
            <button className="btn btn-sm" onClick={() => setAllowSelfPlay(true)}>
              Run as self-play anyway
            </button>
          </div>
        )}
      </div>

      <div className="panel setup-step">
        <div className="step-head">
          <span className="step-num">2</span>
          <span className="step-title">Fight rules</span>
          <span className="step-desc">
            Weapon, which part of it is lethal, and the arena physics.
          </span>
        </div>
        <WeaponPicker value={weapon} onChange={pickWeapon} />
        <ArenaPicker value={arena} onChange={setArena} />
        <SharpZonePicker
          weapon={weapon}
          zones={sharp}
          allZones={WEAPON_ZONES[weapon] || WEAPON_ZONES.sword}
          onToggle={toggleSharp}
        />
      </div>

      <div className="panel setup-step">
        <div className="step-head">
          <span className="step-num">3</span>
          <span className="step-title">Evaluation mode</span>
          <span className="step-desc">
            How much control the model gets, and how much spatial help.
          </span>
        </div>
        <div>
          <div className="lbl" id="mode-legend">Control mode</div>
          <div className="cards" role="radiogroup" aria-labelledby="mode-legend">
            <button type="button" className="card" role="radio"
                    aria-checked={mode === "macro"} onClick={() => setMode("macro")}>
              <span className="card-name">Macro</span>
              <span className="card-desc">Picks tactical moves — thrust, lunge, draw_shot.</span>
            </button>
            <button type="button" className="card" role="radio"
                    aria-checked={mode === "joint"} onClick={() => setMode("joint")}>
              <span className="card-name">Joint</span>
              <span className="card-desc">Raw per-joint torques — Toribash motor control.</span>
            </button>
          </div>
        </div>
        <div>
          <div className="lbl" id="blind-legend">Spatial information</div>
          <div className="cards" role="radiogroup" aria-labelledby="blind-legend">
            <button type="button" className="card" role="radio"
                    aria-checked={!blindfolded} onClick={() => setBlindfolded(false)}>
              <span className="card-name">Normal</span>
              <span className="card-desc">Gets derived hints: enemy left/right, height, facing.</span>
            </button>
            <button type="button" className="card" role="radio"
                    aria-checked={blindfolded} onClick={() => setBlindfolded(true)}>
              <span className="card-name">Blindfolded</span>
              <span className="card-desc">Raw coordinates only — tests pure spatial reasoning. Separate rating cell.</span>
            </button>
          </div>
        </div>
      </div>

      {/* ---------- Advanced (BYOK + raw config) ---------- */}
      <div className="panel setup-step">
        <div className="step-head">
          <span className="step-num">4</span>
          <span className="step-title">Advanced</span>
          <button
            className="btn btn-sm btn-ghost"
            style={{ marginLeft: "auto" }}
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {advancedOpen ? "Hide" : "Show"}
          </button>
        </div>
        {advancedOpen && (
          <>
            <ByokPanel />

            {/* ---- benchmark spec v1.0 (§1): length, fallback policy, seed ----
                These three are part of what makes two results comparable,
                so they are recorded in every match's provenance. */}
            <div>
              <div className="lbl" id="len-legend">Match length</div>
              <div className="cards" role="radiogroup" aria-labelledby="len-legend">
                {[["sprint", "Sprint", "4 turns — fast, noisy; use for smoke tests"],
                  ["standard", "Standard", "12 turns — the default cell"],
                  ["full", "Full", "24 turns — most data, slowest"]].map(
                  ([id, name, desc]) => (
                  <button key={id} type="button" className="card" role="radio"
                          aria-checked={matchLength === id}
                          onClick={() => setMatchLength(id)}>
                    <span className="card-name">{name}</span>
                    <span className="card-desc">{desc}</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="lbl" id="fb-legend">Fallback policy</div>
              <div className="cards" role="radiogroup" aria-labelledby="fb-legend">
                {[["strict", "Strict", "Any scripted fallback turn ⇒ the match is unranked"],
                  ["operational", "Operational", "Fallback turns are counted and disclosed, match still ranks"],
                  ["demo", "Demo", "Never ranked — for demonstrations"]].map(
                  ([id, name, desc]) => (
                  <button key={id} type="button" className="card" role="radio"
                          aria-checked={fallbackPolicy === id}
                          onClick={() => setFallbackPolicy(id)}>
                    <span className="card-name">{name}</span>
                    <span className="card-desc">{desc}</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="lbl" htmlFor="seed-input">
                Seed{" "}
                <span style={{ fontWeight: 400, color: "var(--dim)" }}>
                  — a seeded match replays bit-for-bit from its action log
                </span>
              </label>
              <input
                id="seed-input"
                type="number"
                value={seed}
                placeholder="random"
                onChange={(e) => setSeed(e.target.value)}
                style={{ maxWidth: 180 }}
              />
            </div>
            <div>
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => setShowSample(true)}
              >
                ▶ Watch a sample fight first
              </button>
            </div>

            <div>
              <div className="lbl">Raw configuration sent to the engine</div>
              <pre style={{ fontSize: 11.5, color: "var(--dim)", overflowX: "auto",
                            background: "rgba(0,0,0,0.25)", padding: 10,
                            borderRadius: 6, border: "1px solid var(--line)" }}>
{JSON.stringify({ model_a: modelA || null, model_b: modelB || null, sharp,
                  weapon, mode, arena, blindfolded, blind: true,
                  match_length: matchLength,
                  fallback_policy: fallbackPolicy,
                  seed: seed === "" ? null : Number(seed) }, null, 2)}
              </pre>
            </div>
          </>
        )}

        {/* ---------- Fight bar with preflight feedback ---------- */}
        <div className="fightbar" style={{ borderTop: "1px solid var(--line)",
                                           paddingTop: 14 }}>
          <button
            className="fight-btn"
            onClick={launch}
            disabled={!ready || isBusy}
            aria-disabled={!ready || isBusy}
          >
            {status === "submitting" ? "Starting duel…"
              : isBusy ? "Duel running…"
              : "⚔ Fight"}
          </button>
          <div className="fight-summary">
            <b>{filterSummary}</b>{" · "}{matchLength} length
            <br />
            usually 45–90s
            {worstCaseMin ? ` · up to ~${worstCaseMin} min if both models use their full budget` : ""}
            {" · blind vote on"}
            {!ready && !isBusy && (
              <><br /><span style={{ color: "var(--gold)" }}>
                {sameModel ? "confirm self-play to continue" : "pick two models to continue"}
              </span></>
            )}
          </div>
          <button className="btn btn-sm" style={{ marginLeft: "auto" }}
                  onClick={runRecommended}>
            ⚡ Run recommended duel
          </button>
        </div>
      </div>

      {/* ================= OBSERVE ================= */}
      {isBusy && matchId && (
        <WaitPanel
          matchId={matchId}
          modelA={modelA}
          modelB={modelB}
          onReady={handleReady}
          onCancel={() => { resetMatchState(); }}
          onRetry={() => { resetMatchState(); launch(); }}
        />
      )}

      {/* ================= REPLAY ================= */}
      {replay && (
        <div className="panel">
          <span className="panel-title"><span className="tick" /> Combat replay</span>
          <ReplayPlayer replay={replay} />
          {integrityNote && (
            <div className="stalled" style={{ borderColor: "rgba(255, 102, 128, 0.45)",
                                              background: "rgba(255, 61, 92, 0.07)" }}>
              <p>⚠️ <b>Scripted fallback used:</b> {integrityNote}</p>
            </div>
          )}
          {integrity && (
            <IntegrityBadge audit={integrity} matchId={matchId} />
          )}
          <TurnTranscript replay={replay} />
        </div>
      )}

      {/* ================= JUDGE ================= */}
      {replay && !voteResult && (
        <PredictPanel prediction={prediction} onPredict={setPrediction} streak={streak} />
      )}
      {replay && !voteResult && (
        <VotePanel onVote={vote} predictionLocked={Boolean(prediction)}
                   integrityNote={integrityNote} />
      )}

      {/* ================= REVEAL ================= */}
      {voteResult && (
        <RevealPanel
          result={voteResult}
          replay={replay}
          voteChoice={voteChoice}
          prediction={prediction}
          predictionCorrect={lastPredWasCorrect}
          streak={streak}
          matchId={matchId}
        />
      )}
      {voteResult && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn" onClick={() => { resetMatchState();
                    setupRef.current?.scrollIntoView({ behavior: "smooth" }); }}>
            ⟲ Run another duel
          </button>
          {status === "ready" && (
            <span className="fight-summary" style={{ alignSelf: "center" }}>
              same rules · <b>{filterSummary}</b>
            </span>
          )}
        </div>
      )}

      {/* ================= INSPECT: leaderboard ================= */}
      <div className="panel">
        <div className="step-head">
          <span className="panel-title gold"><span className="tick" /> Human-Voted Elo</span>
          <span style={{ fontSize: 12, color: "var(--dim)", marginLeft: "auto" }}
                title="Ratings reflect human judgements of tactical decision quality, not only match wins.">
            ratings reflect judged decision quality, not only wins
          </span>
        </div>
        <div className="filter-summary">{filterSummary}</div>
        {quality && quality.evidence_level !== "real" && (
          <DataQualityBanner summary={quality} cell={filterSummary} />
        )}
        <LeaderboardTable
          rows={leaderboard}
          objective={objective}
          compact
          emptyAction={
            <button className="btn btn-sm"
                    onClick={() => setupRef.current?.scrollIntoView({ behavior: "smooth" })}>
              Start a duel
            </button>
          }
        />
        <a className="btn btn-sm btn-ghost" href="/leaderboard"
           style={{ alignSelf: "flex-start", textDecoration: "none" }}>
          Full leaderboard & filters →
        </a>
      </div>

      {/* ---------- Sample fight (§3) ----------
          Served from a static replay so it works even when the backend is
          asleep or a provider is throttled. */}
      <SampleFight open={showSample} onClose={() => setShowSample(false)} />

      <FAQ />
      <SiteFooter />
    </>
  );
}
