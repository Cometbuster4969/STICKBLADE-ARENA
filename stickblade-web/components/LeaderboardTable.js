"use client";
import { Fragment, useState } from "react";
import { EvidenceChip, EvidenceMeta, fmtDate } from "@/components/DataQuality";

// Minimum votes before a rating is considered non-provisional. Below this
// threshold the row is marked with a "provisional" chip — Elo swings from
// small N are noise, and hiding that from users would mislead them. Anchored
// to the AGENTS.md §0.5 research-grade audit: N-per-cell + uncertainty
// display is the single biggest legibility gap.
const PROVISIONAL_N = 10;

// Format a win-rate + Wilson 95% CI as "54% (48-61)". Returns null when
// the row has no vote data (N=0) — the render path skips those cells.
function fmtWinRateCi(r) {
  if (r.win_rate == null) return null;
  const pct = (x) => Math.round(x * 100);
  return { center: pct(r.win_rate), lo: pct(r.win_rate_lo), hi: pct(r.win_rate_hi) };
}

function Medal({ rank }) {
  if (rank > 3) return <>{rank}</>;
  const cls = rank === 1 ? "" : rank === 2 ? "silver" : "bronze";
  return <span className={`rank-medal ${cls}`} aria-label={`Rank ${rank}`}>{rank}</span>;
}

/** Elo trend arrow vs the 1000 baseline. ±20 dead-zone so models sitting
    exactly at start-rating don't flicker between ↑/↓. */
function TrendArrow({ rating }) {
  const delta = rating - 1000;
  const [glyph, color, title] = delta > 20
    ? ["↑", "var(--green)", `+${Math.round(delta)} above baseline`]
    : delta < -20
    ? ["↓", "var(--red-2)", `${Math.round(delta)} below baseline`]
    : ["→", "var(--dim)", "at baseline (±20)"];
  return (
    <span title={title}
          style={{ color, marginLeft: 6, fontWeight: 700, fontSize: "0.85em" }}>
      {glyph}
    </span>
  );
}

/** Sample size, always visible next to the rating (review item 18).
    "1084 · provisional · 7 matches" or "1084 · 42 matches · 61% win rate".
    A rating without its N is easy to misread as settled. */
function SampleSize({ n, winPct, provisional }) {
  return (
    <span style={{ color: "var(--dim)", fontSize: 11, whiteSpace: "nowrap" }}>
      {n} {n === 1 ? "match" : "matches"}
      {provisional
        ? <span style={{ color: "var(--gold)" }}> · provisional</span>
        : winPct != null && <span> · {winPct}% wins</span>}
    </span>
  );
}

/** "Why this rank?" drill-down (review item 19). Uses the vote row plus the
    objective rollup for the same filter cell, so the numbers shown are the
    numbers the backend actually has for that slice — no invented history. */
function WhyThisRank({ row, obj, columns }) {
  const ci = fmtWinRateCi(row);
  const degraded = obj ? Math.round((obj.fallback_rate || 0) * (obj.matches || 0)) : null;
  return (
    <tr>
      <td colSpan={columns} style={{ padding: 0 }}>
        <div className="why">
          <dl>
            <dt>Cell</dt>
            <dd>
              {row.weapon} · {(row.sharp || "?").split(",").join("+")} · {row.mode}
              {" · "}{row.arena}
              {row.blindfolded ? " · blindfolded" : ""}
            </dd>
            <dt>Matches</dt>
            <dd>{row.wins}W / {row.losses}L / {row.draws}D · N={row.n}</dd>
            <dt>Win rate</dt>
            <dd>
              {ci ? `${ci.center}% (95% CI ${ci.lo}–${ci.hi})` : "no votes yet"}
            </dd>
            <dt>Rating</dt>
            <dd>
              {row.rating} (start 1000, K=32)
              {row.n < PROVISIONAL_N && ` · provisional until N≥${PROVISIONAL_N}`}
            </dd>
            <dt>Prompt</dt>
            <dd>v{row.prompt_version}</dd>
            {row.data_quality && (
              <>
                <dt>Evidence</dt>
                <dd>
                  <EvidenceChip dq={row.data_quality} />
                  {" "}
                  <span style={{ color: "var(--dim)" }}>
                    {row.data_quality.real_provider_matches} real-provider ·{" "}
                    {row.data_quality.mixed_provider_matches} mixed ·{" "}
                    {row.data_quality.scripted_matches} scripted ·{" "}
                    {row.data_quality.ranking_eligible_matches} ranking-eligible ·{" "}
                    {row.data_quality.fallback_matches} fallback ·{" "}
                    {row.data_quality.token_missing_matches} missing tokens
                  </span>
                </dd>
                <dt>Updated</dt>
                <dd>
                  {fmtDate(row.data_quality.last_match_at)} · benchmark v
                  {(row.data_quality.benchmark_versions || []).join(", v") || "?"}
                </dd>
              </>
            )}
            {obj && (
              <>
                <dt>Damage/turn</dt>
                <dd>{obj.damage_per_turn}</dd>
                <dt>Hit rate</dt>
                <dd>{Math.round((obj.hit_rate || 0) * 100)}%
                  {" "}({obj.hits_landed}/{obj.hits_attempted})</dd>
                <dt>Avg distance</dt>
                <dd>{obj.avg_distance}px</dd>
                <dt>Degraded</dt>
                <dd>
                  {degraded} of {obj.matches} matches used the scripted fallback
                  {" "}({Math.round((obj.fallback_rate || 0) * 100)}%)
                </dd>
              </>
            )}
          </dl>
          {!obj && (
            <p style={{ marginTop: 8, color: "var(--mute)", fontSize: 11.5 }}>
              Objective rollup unavailable for this filter — vote-derived
              numbers only.
            </p>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function LeaderboardTable({ rows, compact = false, objective = {},
                                           emptyAction = null }) {
  const [open, setOpen] = useState(null);
  // `compact` = drop the "D"raws column and cap to top 10 so the sidebar
  // leaderboard on the fight page stays vertical without horizontal scroll.
  if (!rows?.length) {
    return (
      <div className="empty">
        <div className="empty-t">No human-voted ratings yet for this cell.</div>
        <div style={{ fontSize: 13 }}>
          Run a duel and cast the first blind vote — ratings appear the moment
          a vote lands.
        </div>
        {emptyAction}
      </div>
    );
  }
  const shown = compact ? rows.slice(0, 10) : rows;
  const promptVersion = shown[0]?.prompt_version ?? null;
  const columns = compact ? 7 : 10;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <caption className="visually-hidden" style={{ position: "absolute",
                                                        left: "-9999px" }}>
          Human-Voted Elo leaderboard. Ratings reflect human judgements of
          tactical decision quality, not only match wins.
        </caption>
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th className="r"
                title="Ratings reflect human judgements of tactical decision quality, not only match wins.">
              Human-Voted Elo
            </th>
            <th className="r" title="Total voted matches (wins + losses + draws)">Sample</th>
            <th title="Who actually made the decisions behind this rating: real inference providers, a mix, or scripted baselines. Hover a chip for the counts.">
              Evidence
            </th>
            {!compact && (
              <th className="r"
                  title="Win-rate with 95% Wilson score confidence interval. Draws count as half-wins per Elo convention.">
                Win% (95% CI)
              </th>
            )}
            <th className="r">W</th>
            <th className="r">L</th>
            {!compact && <th className="r">D</th>}
            <th aria-label="Details"></th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => {
            const rank = i + 1;
            const n = (r.wins || 0) + (r.losses || 0) + (r.draws || 0);
            const isProvisional = n < PROVISIONAL_N;
            const ci = fmtWinRateCi(r);
            const key = r.model + (r.sharp || "");
            const isOpen = open === key;
            return (
              <Fragment key={key}>
                <tr
                    className={rank === 1 ? "rank-1" : ""}
                    style={isProvisional ? { opacity: 0.82 } : undefined}>
                  <td><Medal rank={rank} /></td>
                  <td className="model">{r.name || r.model}</td>
                  <td className="r elo">
                    {r.rating}
                    <TrendArrow rating={r.rating} />
                    <div>
                      <SampleSize n={n} provisional={isProvisional}
                                  winPct={ci ? ci.center : null} />
                    </div>
                  </td>
                  <td className="r" style={{ color: "var(--dim)", fontWeight: 600 }}>{n}</td>
                  <td>
                    <EvidenceChip dq={r.data_quality} compact={compact} />
                    {!compact && (
                      <div><EvidenceMeta dq={r.data_quality} /></div>
                    )}
                  </td>
                  {!compact && (
                    <td className="r" style={{ color: "var(--dim)", fontSize: "0.85em" }}>
                      {ci ? (
                        <span title={`True win-rate is 95% likely to be in [${ci.lo}%, ${ci.hi}%]. Wider = less data.`}>
                          <b style={{ color: "var(--text)" }}>{ci.center}%</b>
                          <span style={{ color: "var(--mute)" }}>{" ("}{ci.lo}–{ci.hi}{")"}</span>
                        </span>
                      ) : (
                        <span style={{ color: "var(--mute)" }}>—</span>
                      )}
                    </td>
                  )}
                  <td className="r" style={{ color: "var(--green)" }}>{r.wins}</td>
                  <td className="r" style={{ color: "var(--red-2)" }}>{r.losses}</td>
                  {!compact && (
                    <td className="r" style={{ color: "var(--dim)" }}>{r.draws}</td>
                  )}
                  <td className="r">
                    <button
                      className="btn btn-sm btn-ghost"
                      aria-expanded={isOpen}
                      aria-label={`Why is ${r.name || r.model} ranked ${rank}?`}
                      onClick={() => setOpen(isOpen ? null : key)}
                    >
                      {isOpen ? "Hide" : "Why?"}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <WhyThisRank row={r} obj={objective[r.model]} columns={columns} />
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 10,
                    padding: "0 4px", letterSpacing: 0.3, lineHeight: 1.7 }}>
        <b style={{ color: "var(--gold)" }}>provisional</b> = fewer than
        {" "}{PROVISIONAL_N} voted matches; ratings at small N swing ±80 points
        and are labelled rather than hidden.
        {" "}<b>Evidence</b> says who decided: <b>scripted baseline</b> rows
        validate the pipeline, not a model; only <b>real-provider</b> rows
        with enough ranking-eligible matches are model results.
        {!compact && promptVersion != null && (
          <>
            <br />
            <span title="Prompt-version pin. Ratings are only comparable within the same prompt version — see AGENTS.md §PROMPT_VERSION_LOG.">
              🔖 rated under prompt&nbsp;
              <b style={{ color: "var(--text)" }}>v{promptVersion}</b>
            </span>
          </>
        )}
      </div>
    </div>
  );
}
