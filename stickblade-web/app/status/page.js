"use client";
import { useEffect, useState } from "react";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { getStatus, getMetrics, getDataQuality } from "@/lib/api";
import DataQualityBanner from "@/components/DataQuality";

/**
 * Status page (action-plan §35).
 *
 * Third-party model providers throttle and go down; without a status page
 * every outage looks like our bug. This reads the same endpoints a monitor
 * would, so what you see here is what the backend actually reports.
 */
const COMPONENTS = [
  ["frontend", "Website"],
  ["backend", "Simulation API"],
  ["providers", "Model providers"],
  ["queue", "Match queue"],
  ["database", "Match database"],
  ["replays", "Replay storage"],
];

function fmtWhen(epoch) {
  if (!epoch) return "—";
  try { return new Date(epoch * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC"; }
  catch { return "—"; }
}

function Level({ value }) {
  const v = String(value || "");
  const tone = v.startsWith("ok") ? "ok" : v.startsWith("degraded") ? "warn"
    : v ? "bad" : "warn";
  return <span className={`badge ${tone}`}>{value || "unknown"}</span>;
}

export default function StatusPage() {
  const [status, setStatus] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [quality, setQuality] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [s, m, q] = await Promise.all([
          getStatus(), getMetrics(),
          getDataQuality().catch(() => null)]);
        if (!alive) return;
        setStatus(s);
        setMetrics(m);
        setQuality(q?.summary || null);
        setErr(null);
      } catch (e) {
        if (alive) setErr(e.message || "backend unreachable");
      }
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <>
      <SiteNav />
    <div className="container">
      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> Service status
        </span>
        <p style={{ color: "var(--dim)", fontSize: 13, marginTop: 8,
                    maxWidth: "72ch", lineHeight: 1.6 }}>
          Live health of the arena backend, the model providers it depends
          on, and the current queue. Refreshes every 30 seconds.
        </p>
        {err && (
          <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 6,
                        border: "1px solid rgba(255, 61, 92, 0.4)",
                        background: "rgba(255, 61, 92, 0.08)",
                        color: "var(--text)", fontSize: 13 }}>
            ⚠ Backend unreachable: {err}. The site still loads; matches
            cannot start until the API is back.
          </div>
        )}
      </div>

      {status && (
        <>
          {/* Overall state + degraded modes + last incident (priority 4).
              "ok" here means the arena is BOTH operationally up and not
              running in a mode that quietly changes what the numbers
              mean (no provider keys, scripted-only rankings, replay
              blobs missing). */}
          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Overall: <Level value={status.status} />
            </span>
            {(status.degraded_modes || []).length > 0 ? (
              <>
                <p style={{ color: "var(--dim)", fontSize: 13, marginTop: 8 }}>
                  Degraded modes currently active:
                </p>
                <ul style={{ margin: "4px 0 0", paddingLeft: 20, color: "var(--text)",
                             fontSize: 13, lineHeight: 1.7 }}>
                  {status.degraded_modes.map((d) => <li key={d}>{d}</li>)}
                </ul>
              </>
            ) : (
              <p style={{ color: "var(--dim)", fontSize: 13, marginTop: 8 }}>
                No degraded modes active.
              </p>
            )}
            <p style={{ color: "var(--dim)", fontSize: 13, marginTop: 10 }}>
              <b style={{ color: "var(--text)" }}>Last incident:</b>{" "}
              {status.last_incident
                ? <>{fmtWhen(status.last_incident.at)} — <code>{status.last_incident.what}</code></>
                : "none recorded since the backend process started"}
              {status.uptime_s != null && (
                <span style={{ color: "var(--mute)" }}>
                  {" "}(process up {Math.round(status.uptime_s / 3600)} h)
                </span>
              )}
            </p>
            {status.provider_errors && Object.keys(status.provider_errors).length > 0 && (
              <p style={{ color: "var(--dim)", fontSize: 12.5, marginTop: 6 }}>
                Provider errors since start:{" "}
                {Object.entries(status.provider_errors)
                  .map(([k, v]) => `${k} ×${v}`).join(" · ")}
              </p>
            )}
          </div>

          {/* Data-quality mode (next-step priority 4): if every ranking is
              scripted or the real-provider sample is too small, say so
              here — an operational "all green" is not a research "all
              green". */}
          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Ranking data quality
            </span>
            <div style={{ marginTop: 10 }}>
              <DataQualityBanner summary={quality} cell="whole dataset"
                                 style={{ margin: 0 }} />
              {!quality && (
                <p style={{ color: "var(--dim)", fontSize: 13 }}>
                  data-quality report unavailable
                </p>
              )}
            </div>
          </div>

          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Components
            </span>
            <table className="prov-table" style={{ marginTop: 10 }}>
              <tbody>
                {COMPONENTS.map(([key, label]) => (
                  <tr key={key}>
                    <td style={{ width: "30%", color: "var(--text)" }}>{label}</td>
                    <td><Level value={status.components?.[key]} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Versions &amp; throughput
            </span>
            <div className="scorecard">
              <div className="cell">
                <div className="k">Benchmark spec</div>
                <div className="v">v{status.benchmark_version}</div>
              </div>
              <div className="cell">
                <div className="k">Physics / prompt</div>
                <div className="v">v{status.physics_version} /
                  v{status.prompt_version}</div>
              </div>
              <div className="cell">
                <div className="k">Spec fingerprint</div>
                <div className="v"><code>{status.spec_fingerprint}</code></div>
              </div>
              <div className="cell">
                <div className="k">Queue depth</div>
                <div className="v">{status.queue_depth}</div>
              </div>
              <div className="cell">
                <div className="k">Uptime</div>
                <div className="v">
                  {Math.round((status.uptime_s || 0) / 3600)}h
                </div>
              </div>
              <div className="cell">
                <div className="k">Completion rate</div>
                <div className="v">
                  {status.completion_rate != null
                    ? `${Math.round(status.completion_rate * 100)}%` : "—"}
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {metrics?.storage && (
        <div className="panel">
          <span className="panel-title">
            <span className="tick" /> Reliability (lifetime + last 24h)
          </span>
          <div className="scorecard">
            {[
              ["Matches", metrics.storage.matches?.total],
              ["Completed", metrics.storage.matches?.done],
              ["Errors", metrics.storage.matches?.error],
              ["Fallback used", metrics.storage.matches?.fallback_used],
              ["Unranked", metrics.storage.matches?.ranking_ineligible],
              ["Votes", metrics.storage.matches?.votes],
              ["Fallback rate",
                metrics.storage.rates?.fallback != null
                  ? `${Math.round(metrics.storage.rates.fallback * 100)}%` : "—"],
              ["Vote-through",
                metrics.storage.rates?.vote_through != null
                  ? `${Math.round(metrics.storage.rates.vote_through * 100)}%` : "—"],
              ["Decision p50",
                metrics.storage.latency_ms_24h?.p50 != null
                  ? `${Math.round(metrics.storage.latency_ms_24h.p50)} ms` : "—"],
              ["Decision p95",
                metrics.storage.latency_ms_24h?.p95 != null
                  ? `${Math.round(metrics.storage.latency_ms_24h.p95)} ms` : "—"],
            ].map(([k, v]) => (
              <div className="cell" key={k}>
                <div className="k">{k}</div>
                <div className="v">{v ?? "—"}</div>
              </div>
            ))}
          </div>
          <p style={{ marginTop: 10, fontSize: 12, color: "var(--dim)" }}>
            Alert thresholds: match failure &gt; 5%, vote failures &gt; 1%,
            fallback rate &gt; 25%.
          </p>
        </div>
      )}

      <div className="panel">
        <span className="panel-title">
          <span className="tick" /> If matches are failing
        </span>
        <ul style={{ marginTop: 10, paddingLeft: 20, color: "var(--dim)",
                     fontSize: 13, lineHeight: 1.8 }}>
          <li>Most “failures” are upstream free-tier rate limits, not the
            arena. The fallback ladder routes around them automatically.</li>
          <li>Use <b>Strict</b> fallback policy in Research Mode if you need
            every match to be fully model-controlled — such matches are
            excluded from rankings instead of silently counted.</li>
          <li>Paste your own OpenRouter key in the setup panel to draw from
            your quota instead of the shared one. See the{" "}
            <a href="/trust" style={{ color: "var(--gold)" }}>trust page</a>{" "}
            for how that key is handled.</li>
        </ul>
      </div>
    </div>
    <SiteFooter />
  </>
  );
}
