"use client";
import { useEffect, useMemo, useState } from "react";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { exportUrl, getBenchmarkSpec } from "@/lib/api";

/**
 * Public benchmark dashboard (action-plan §28).
 *
 * The leaderboard answers "who is winning". This answers the questions a
 * researcher asks next: is the instrument balanced, how reliable is the
 * harness, and which configuration cell am I actually looking at.
 *
 * Everything is derived from the public dataset export — the same file a
 * researcher can download — so the dashboard can never show anything
 * that isn't reproducible offline.
 */
const fmtPct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function groupCount(rows, key) {
  const out = {};
  for (const r of rows) {
    const k = r[key] ?? "—";
    out[k] = (out[k] || 0) + 1;
  }
  return Object.entries(out).sort((a, b) => b[1] - a[1]);
}

function reliability(rows) {
  if (!rows.length) return null;
  const n = rows.length;
  const num = (f) => rows.reduce((acc, r) => acc + (Number(r[f]) || 0), 0);
  const fb = rows.filter((r) => r.fallback_used).length;
  const ineligible = rows.filter((r) => r.ranking_eligible === false).length;
  const lat = rows.flatMap((r) => [r.latency_ms_a, r.latency_ms_b])
    .filter((v) => v != null).sort((a, b) => a - b);
  const pct = (p) => (lat.length
    ? Math.round(lat[Math.min(lat.length - 1, Math.floor(p * lat.length))])
    : null);
  return {
    n,
    fallback: fb / n,
    ineligible,
    invalid: num("invalid_actions_a") + num("invalid_actions_b"),
    p50: pct(0.5),
    p95: pct(0.95),
  };
}

export default function DashboardPage() {
  const [rows, setRows] = useState([]);
  const [spec, setSpec] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(exportUrl("json", { limit: 5000 }))
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((d) => { if (alive) setRows(d.matches || []); })
      .catch((e) => alive && setErr(e.message))
      .finally(() => alive && setLoading(false));
    getBenchmarkSpec().then(setSpec).catch(() => {});
    return () => { alive = false; };
  }, []);

  const rel = useMemo(() => reliability(rows), [rows]);
  const byWeapon = useMemo(() => groupCount(rows, "weapon"), [rows]);
  const byArena = useMemo(() => groupCount(rows, "arena"), [rows]);
  const byMode = useMemo(() => groupCount(rows, "mode"), [rows]);
  const byLength = useMemo(() => groupCount(rows, "match_length"), [rows]);

  return (
    <>
      <SiteNav />
    <div className="container">
      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Benchmark dashboard
        </span>
        <p style={{ color: "var(--dim)", fontSize: 13, marginTop: 8,
                    maxWidth: "78ch", lineHeight: 1.6 }}>
          How the instrument itself is behaving: which configurations are
          actually being played, how often providers fail over, how much of
          the data is ranking-eligible, and how fast decisions come back.
          Built from the same{" "}
          <a href={exportUrl("csv", { limit: 5000 })}
             style={{ color: "var(--gold)" }}>CSV export</a>{" "}
          you can download.
        </p>
        {spec && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                        marginTop: 10 }}>
            <span className="badge">spec v{spec.benchmark_version}</span>
            <span className="badge">physics v{spec.physics_version}</span>
            <span className="badge">prompt v{spec.model_interface
              ?.prompt_version}</span>
            <span className="badge">
              fingerprint <code>{spec.fingerprint}</code>
            </span>
          </div>
        )}
      </div>

      {loading && (
        <div className="panel" style={{ color: "var(--dim)" }}>
          Loading dataset export…
        </div>
      )}
      {err && (
        <div className="panel" style={{ color: "var(--gold)" }}>
          Could not load the dataset ({err}). Start the backend locally with{" "}
          <code>uvicorn server:app</code>, or download the export directly:{" "}
          <a href={exportUrl("csv")} style={{ color: "var(--gold)" }}>CSV</a>
          {" · "}
          <a href={exportUrl("jsonl")} style={{ color: "var(--gold)" }}>JSONL</a>.
        </div>
      )}

      {rel && (
        <>
          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Harness reliability
            </span>
            <div className="scorecard">
              <div className="cell">
                <div className="k">Matches exported</div>
                <div className="v">{rel.n}</div>
              </div>
              <div className="cell">
                <div className="k">Fallback rate</div>
                <div className="v">{fmtPct(rel.fallback)}</div>
              </div>
              <div className="cell">
                <div className="k">Ranking-ineligible</div>
                <div className="v">{rel.ineligible}</div>
              </div>
              <div className="cell">
                <div className="k">Invalid actions</div>
                <div className="v">{rel.invalid}</div>
              </div>
              <div className="cell">
                <div className="k">Decision latency p50</div>
                <div className="v">{rel.p50 ?? "—"} ms</div>
              </div>
              <div className="cell">
                <div className="k">Decision latency p95</div>
                <div className="v">{rel.p95 ?? "—"} ms</div>
              </div>
            </div>
            <p style={{ marginTop: 10, fontSize: 12, color: "var(--dim)" }}>
              Fallback = a turn played by a scripted brain after every
              provider attempt failed. Under the strict policy those matches
              are excluded from rankings entirely, which is why the eligible
              count can be lower than the match count.
            </p>
          </div>

          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Configuration coverage
            </span>
            <p style={{ marginTop: 8, fontSize: 12, color: "var(--dim)" }}>
              Ratings are segmented per (model, sharp, weapon, mode, arena,
              blindfolded). Sparse cells are the main reason a leaderboard
              number can be provisional — this shows where the data actually
              is.
            </p>
            <div style={{ display: "grid",
                          gridTemplateColumns:
                            "repeat(auto-fit, minmax(220px, 1fr))",
                          gap: 12, marginTop: 12 }}>
              {[["Weapon", byWeapon], ["Arena", byArena],
                ["Control mode", byMode], ["Match length", byLength]]
                .map(([title, counts]) => (
                  <div key={title} style={{ padding: 12, borderRadius: 8,
                                            border: "1px solid var(--line)",
                                            background: "var(--bg-3)" }}>
                    <div style={{ fontSize: 11, letterSpacing: 1.4,
                                  textTransform: "uppercase",
                                  color: "var(--dim)",
                                  marginBottom: 6 }}>{title}</div>
                    {counts.length === 0 && (
                      <div style={{ fontSize: 12, color: "var(--mute)" }}>
                        no data
                      </div>
                    )}
                    {counts.map(([k, v]) => (
                      <div key={k} style={{ display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: 12, padding: "2px 0" }}>
                        <span>{k}</span>
                        <b>{v}</b>
                      </div>
                    ))}
                  </div>
                ))}
            </div>
          </div>
        </>
      )}

      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Reproduce these numbers
        </span>
        <pre style={{ marginTop: 10, padding: 12, borderRadius: 8,
                      background: "rgba(0,0,0,0.35)", overflowX: "auto",
                      fontSize: 12, color: "var(--text-2)",
                      border: "1px solid var(--line)" }}>
{`# download the dataset (JSON / JSONL / CSV)
curl -L "${exportUrl("csv", { limit: 5000 })}" -o matches.csv

# run the frozen benchmark spec offline — no server, no API key
./tools/run_match.py spec
./tools/run_match.py simulate --a bot:pro --b bot:greedy --seed 42

# balanced 30-match batch with Wilson confidence intervals
./tools/run_match.py batch --a bot:pro --b bot:greedy --n 30

# weapon / arena balance sweep
./tools/run_match.py balance --n 30 --md-out research/balance_report.md`}
        </pre>
      </div>
    </div>
    <SiteFooter />
  </>
  );
}
