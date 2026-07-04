"use client";

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
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th className="r">Elo</th>
            <th className="r">W</th>
            <th className="r">L</th>
            {!compact && <th className="r">D</th>}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => {
            const rank = i + 1;
            return (
              <tr key={r.model + (r.sharp || "")} className={rank === 1 ? "rank-1" : ""}>
                <td><Medal rank={rank} /></td>
                <td className="model">{r.name || r.model}</td>
                <td className="r elo">
                  {r.rating}
                  <TrendArrow rating={r.rating} />
                </td>
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
    </div>
  );
}
