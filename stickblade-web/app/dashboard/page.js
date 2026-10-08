"use client";
import { useEffect, useMemo, useState } from "react";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { exportUrl, getBenchmarkSpec } from "@/lib/api";
import { MotionSection, StaggerContainer, StaggerItem, SlideIn } from "@/components/MotionSection";

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
  return { n, fallback: fb / n, ineligible,
    invalid: num("invalid_actions_a") + num("invalid_actions_b"),
    p50: pct(0.5), p95: pct(0.95) };
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
      .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
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

  const statCards = rel ? [
    ["Matches exported", rel.n],
    ["Fallback rate", fmtPct(rel.fallback)],
    ["Ranking-ineligible", rel.ineligible],
    ["Invalid actions", rel.invalid],
    ["Decision latency p50", (rel.p50 ?? "—") + " ms"],
    ["Decision latency p95", (rel.p95 ?? "—") + " ms"],
  ] : [];

  const coverageGroups = [["Weapon", byWeapon], ["Arena", byArena],
    ["Control mode", byMode], ["Match length", byLength]];

  return (
    <>
      <SiteNav />
    <div className="container" style={{ position: "relative" }}>

      <MotionSection>
        <div className="panel">
          <span className="panel-title">
            <span className="tick" /> Benchmark dashboard
          </span>
          <p style={{ color: "var(--text-2)", fontSize: 13, marginTop: 8,
                      maxWidth: "78ch", lineHeight: 1.7 }}>
            How the instrument itself is behaving: which configurations are
            actually being played, how often providers fail over, how much of
            the data is ranking-eligible, and how fast decisions come back.
            Built from the same{" "}
            <a href={exportUrl("csv", { limit: 5000 })}
               style={{ color: "var(--gold)" }}>CSV export</a>{" "}
            you can download.
          </p>
          {spec && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <span className="badge">spec v{spec.benchmark_version}</span>
              <span className="badge">physics v{spec.physics_version}</span>
              <span className="badge">prompt v{spec.model_interface?.prompt_version}</span>
              <span className="badge">
                fingerprint <code>{spec.fingerprint}</code>
              </span>
            </div>
          )}
        </div>
      </MotionSection>

      {loading && (
        <MotionSection delay={0.05}>
          <div className="panel" style={{ color: "var(--dim)" }}>
            Loading dataset export…
          </div>
        </MotionSection>
      )}
      {err && (
        <MotionSection delay={0.05}>
          <div className="panel" style={{ color: "var(--gold)" }}>
            Could not load the dataset ({err}).{" "}
            <a href={exportUrl("csv")} style={{ color: "var(--gold)" }}>CSV</a>
            {" · "}
            <a href={exportUrl("jsonl")} style={{ color: "var(--gold)" }}>JSONL</a>.
          </div>
        </MotionSection>
      )}

      {rel && (
        <>
          <MotionSection delay={0.1}>
            <div className="panel">
              <span className="panel-title">
                <span className="tick" /> Harness reliability
              </span>
              <div className="scorecard" style={{ display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginTop: 12 }}>
                {statCards.map(([k, v]) => (
                  <div key={k} className="cell"
                    style={{ padding: 14, borderRadius: 6, border: "1px solid var(--line)",
                             background: "var(--wash)", textAlign: "center" }}
                    data-press-edge
                  >
                    <div style={{ fontSize: 12,
                                  color: "var(--dim)", marginBottom: 6 }}>{k}</div>
                    <div style={{ fontSize: 20, fontWeight: 700,
                                  fontFamily: "var(--font-display), system-ui",
                                  color: "var(--text)" }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </MotionSection>

          <MotionSection delay={0.15}>
            <div className="panel">
              <span className="panel-title">
                <span className="tick" /> Configuration coverage
              </span>
              <p style={{ marginTop: 8, fontSize: 12, color: "var(--dim)" }}>
                Ratings are segmented per (model, sharp, weapon, mode, arena,
                blindfolded). Sparse cells are the main reason a leaderboard
                number can be provisional.
              </p>
              <StaggerContainer style={{ display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12, marginTop: 12 }} staggerDelay={0.08}>
                {coverageGroups.map(([title, counts]) => (
                  <StaggerItem key={title} direction="scale">
                    <div style={{ padding: 14, borderRadius: 6,
                            border: "1px solid var(--line)",
                            background: "var(--wash)" }}
                      data-press-edge>
                      <div style={{ fontSize: 12,
                                    color: "var(--dim)", marginBottom: 8 }}>{title}</div>
                      {counts.length === 0 && (
                        <div style={{ fontSize: 12, color: "var(--mute)" }}>no data</div>
                      )}
                      {counts.map(([k, v]) => (
                        <div key={k} style={{ display: "flex",
                              justifyContent: "space-between",
                              fontSize: 12, padding: "3px 0" }}>
                          <span>{k}</span>
                          <b style={{ color: "var(--text)" }}>{v}</b>
                        </div>
                      ))}
                    </div>
                  </StaggerItem>
                ))}
              </StaggerContainer>
            </div>
          </MotionSection>
        </>
      )}

      <MotionSection delay={0.2}>
        <div className="panel">
          <span className="panel-title">
            <span className="tick" /> Reproduce these numbers
          </span>
          <pre style={{ marginTop: 10, padding: 14, borderRadius: 10,
                        background: "var(--wash-2)", overflowX: "auto",
                        fontSize: 12, color: "var(--text-2)",
                        border: "1px solid var(--line)" }}>
{`# download the dataset (JSON / JSONL / CSV)
curl -L "${exportUrl("csv", { limit: 5000 })}" -o matches.csv

# run the frozen benchmark spec offline
./tools/run_match.py spec
./tools/run_match.py simulate --a bot:pro --b bot:greedy --seed 42

# balanced 30-match batch with Wilson confidence intervals
./tools/run_match.py batch --a bot:pro --b bot:greedy --n 30

# weapon / arena balance sweep
./tools/run_match.py balance --n 30 --md-out research/balance_report.md`}
          </pre>
        </div>
      </MotionSection>
    </div>
    <SiteFooter />
  </>
  );
}
