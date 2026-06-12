"use client";

export default function LeaderboardTable({ rows }) {
  if (!rows?.length)
    return <div style={{ color: "var(--dim)", fontSize: 13 }}>no votes yet</div>;
  return (
    <table className="lb">
      <thead>
        <tr>
          <th>#</th><th>Model</th><th className="r">Elo</th>
          <th className="r">W</th><th className="r">L</th><th className="r">D</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.model + (r.sharp || "")}>
            <td className={i === 0 ? "rank-1" : ""}>{i + 1}</td>
            <td className={i === 0 ? "rank-1" : ""}>{r.name || r.model}</td>
            <td className="r">{r.rating}</td>
            <td className="r">{r.wins}</td>
            <td className="r">{r.losses}</td>
            <td className="r">{r.draws}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
