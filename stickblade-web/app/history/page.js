"use client";
import { useEffect, useState } from "react";
import { getRecent } from "@/lib/api";
import ShareButton from "@/components/ShareButton";

export default function HistoryPage() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getRecent().then(setRows).catch((e) => setErr(e.message));
  }, []);

  return (
    <div style={{ width: "100%", maxWidth: 860 }}>
      <h2 style={{ margin: "6px 0 4px" }}>Recent duels</h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 12 }}>
        Fighters stay anonymous until someone votes on the match.
      </p>
      {err && <div className="status">✖ {err}</div>}
      {rows && (
        <div className="panel">
          <table className="lb">
            <thead>
              <tr>
                <th>Fighters</th><th>Sharp</th><th className="r">Turns</th>
                <th>Method</th><th>Replay</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const url = typeof window !== "undefined"
                  ? `${window.location.origin}/replay?id=${m.match_id}` : "";
                return (
                  <tr key={m.match_id}>
                    <td>{m.models ? m.models.join(" vs ") : "🎭 anonymous (unvoted)"}</td>
                    <td>{m.sharp}</td>
                    <td className="r">{m.turns}</td>
                    <td>{m.method}</td>
                    <td>
                      <a className="mlink" href={`/replay?id=${m.match_id}`}>
                        ▶ watch
                      </a>
                    </td>
                    <td className="r">
                      <ShareButton url={url} label="📋 share" compact />
                    </td>
                  </tr>
                );
              })}
              {!rows.length && (
                <tr><td colSpan={6} style={{ color: "var(--dim)" }}>
                  no matches yet — go fight!
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
