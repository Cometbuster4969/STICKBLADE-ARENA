"use client";

// Minimum votes before a rating is considered non-provisional. Below this
// threshold the row is marked with a "?" glyph — Elo swings from small N
// are noise, and hiding that from users would mislead them. Anchored to
// the AGENTS.md §0.5 research-grade audit: N-per-cell + uncertainty
// display is the single biggest legibility gap.
const PROVISIONAL_N = 10;

// Format a win-rate + Wilson 95% CI as "54% (48-61)". Returns null when
// the row has no vote data (N=0) — the render path skips those cells.
// The backend supplies win_rate / win_rate_lo / win_rate_hi as floats
// in [0, 1]; we render as integer percent for compactness in the table.
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

/**
 * Elo trend arrow vs the 1000 baseline. Subtle glyph, no extra data
 * needed — Elo is already on the row. ±20 dead-zone so models sitting
 * exactly at start-rating don't flicker between ↑/↓.
 */
function TrendArrow({ rating }) {
  const delta = rating - 1000;
  const [glyph, color, title] = delta > 20
    ? ["↑", "var(--green, #56dc82)", `+${Math.round(delta)} above baseline`]
    : delta < -20
    ? ["↓", "var(--red-2, #dc5656)", `${Math.round(delta)} below baseline`]
    : ["→", "var(--dim)", "at baseline (±20)"];
  return (
    <span title={title}
          style={{ color, marginLeft: 6, fontWeight: 700, fontSize: "0.85em" }}>
      {glyph}
    </span>
  );
}

/**
 * Provisional-rating flag. Elo with N < 10 is basically noise (K=32
 * moves ~16 pts per vote, so 5 votes = ±80pt swing possible from a
 * couple of lucky matchups). Marking these rows honestly is the
 * anti-overclaim move — a real researcher will trust the leaderboard
 * more when the small-N cells wear their uncertainty on the sleeve.
 */
function ProvisionalFlag({ n }) {
  if (n >= PROVISIONAL_N) return null;
  return (
    <span
      title={`Provisional — only ${n} match${n === 1 ? "" : "es"}. Needs ≥${PROVISIONAL_N} for a stable rating.`}
      style={{
        marginLeft: 6, fontSize: "0.72em", padding: "1px 5px",
        borderRadius: 3, background: "rgba(212,185,98,0.15)",
        color: "var(--gold, #d4b962)", fontWeight: 700, letterSpacing: 1,
      }}
    >
      ?
    </span>
  );
}

export default function LeaderboardTable({ rows, compact = false }) {
  // `compact` = drop the "D"raws column and cap to top 10 so the sidebar
  // leaderboard on the fight page stays vertical without horizontal scroll.
  // Previously the prop was passed by app/page.js but ignored — silent no-op.
  if (!rows?.length) {
    return (
      <div style={{ color: "var(--dim)", fontSize: 13, padding: "18px 4px", textAlign: "center" }}>
        no votes yet · be the first
      </div>
    );
  }
  const shown = compact ? rows.slice(0, 10) : rows;
  // The prompt-version pin is the same across every row on any given
  // leaderboard load (backend fills from brains.PROMPT_VERSION), so we
  // read it from the first row and show it once in the footer.
  const promptVersion = shown[0]?.prompt_version ?? null;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th className="r">Elo</th>
            <th className="r" title="Total voted matches (wins + losses + draws)">N</th>
            {!compact && (
              <th className="r"
                  title="Win-rate with 95% Wilson score confidence interval. Draws count as half-wins per Elo convention.">
                Win% (95% CI)
              </th>
            )}
            <th className="r">W</th>
            <th className="r">L</th>
            {!compact && <th className="r">D</th>}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => {
            const rank = i + 1;
            const n = (r.wins || 0) + (r.losses || 0) + (r.draws || 0);
            const isProvisional = n < PROVISIONAL_N;
            const ci = fmtWinRateCi(r);
            return (
              <tr key={r.model + (r.sharp || "")}
                  className={rank === 1 ? "rank-1" : ""}
                  style={isProvisional ? { opacity: 0.75 } : undefined}>
                <td><Medal rank={rank} /></td>
                <td className="model">{r.name || r.model}</td>
                <td className="r elo">
                  {r.rating}
                  <TrendArrow rating={r.rating} />
                  <ProvisionalFlag n={n} />
                </td>
                <td className="r" style={{ color: "var(--dim)", fontWeight: 600 }}>{n}</td>
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
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 10,
                    padding: "0 4px", letterSpacing: 0.3, lineHeight: 1.7 }}>
        <b style={{ color: "var(--gold, #d4b962)" }}>?</b> = provisional
        (N &lt; {PROVISIONAL_N} matches; ratings still stabilizing)
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
