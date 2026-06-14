"use client";

function Medal({ rank }) {
  if (rank > 3) return <>{rank}</>;
  const cls = rank === 1 ? "" : rank === 2 ? "silver" : "bronze";
  return <span className={`rank-medal ${cls}`} aria-label={`Rank ${rank}`}>{rank}</span>;
}

export default function LeaderboardTable({ rows }) {
  if (!rows?.length) {
    return (
      <div style={{ color: "var(--dim)", fontSize: 13, padding: "18px 4px", textAlign: "center" }}>
        no votes yet · be the first
      </div>
    );
  }
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
            <th className="r">D</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const rank = i + 1;
            return (
              <tr key={r.model + (r.sharp || "")} className={rank === 1 ? "rank-1" : ""}>
                <td><Medal rank={rank} /></td>
                <td className="model">{r.name || r.model}</td>
                <td className="r elo">{r.rating}</td>
                <td className="r" style={{ color: "var(--green)" }}>{r.wins}</td>
                <td className="r" style={{ color: "var(--red-2)" }}>{r.losses}</td>
                <td className="r" style={{ color: "var(--dim)" }}>{r.draws}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
