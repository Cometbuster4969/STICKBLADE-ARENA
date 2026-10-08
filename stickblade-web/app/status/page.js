"use client";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { getStatus, getMetrics, getDataQuality } from "@/lib/api";
import DataQualityBanner from "@/components/DataQuality";
import { MotionSection, StaggerContainer, StaggerItem, FloatingOrb } from "@/components/MotionSection";

/**
 * Status page (action-plan §35) — motion redesign.
 * Live health, animated status pills, staggered metric cards.
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
  return (
    <motion.span
      className={`badge ${tone}`}
      animate={tone === "ok" ? {} : { opacity: [1, 0.55, 1] }}
      transition={{ duration: 1.8, repeat: Infinity }}
    >
      {value || "unknown"}
    </motion.span>
  );
}

function StatCard({ k, v }) {
  return (
    <StaggerItem direction="scale">
      <motion.div
        className="cell"
        style={{ padding: "14px 12px", borderRadius: 12, textAlign: "center",
                 border: "1px solid var(--line)", background: "rgba(255,255,255,0.02)" }}
        whileHover={{ y: -2, borderColor: "var(--line-strong)" }}
        transition={{ type: "spring", stiffness: 300, damping: 22 }}
      >
        <div className="k">{k}</div>
        <div className="v">{v ?? "—"}</div>
      </motion.div>
    </StaggerItem>
  );
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

  const overallTone = String(status?.status || "").startsWith("ok")
    ? "var(--green)" : status?.status ? "var(--red)" : "var(--gold)";

  return (
    <>
      <SiteNav />
    <div className="container" style={{ position: "relative" }}>
      <FloatingOrb size={280} color="rgba(46, 232, 165, 0.05)" top="-60px" right="-80px" />

      <MotionSection>
        <div className="panel" style={{ overflow: "hidden", position: "relative" }}>
          <span className="panel-title">
            <motion.span
              className="tick"
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
              style={{ background: overallTone, color: overallTone }}
            />
            Service status
          </span>
          <p style={{ color: "var(--text-2)", fontSize: 13, marginTop: 8,
                      maxWidth: "72ch", lineHeight: 1.7 }}>
            Live health of the arena backend, the model providers it depends
            on, and the current queue. Refreshes every 30 seconds.
          </p>
          <AnimatePresence>
            {err && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                style={{ marginTop: 12, padding: "10px 12px", borderRadius: 10,
                         border: "1px solid rgba(255, 51, 85, 0.4)",
                         background: "rgba(255, 51, 85, 0.08)",
                         color: "var(--text)", fontSize: 13 }}
              >
                ⚠ Backend unreachable: {err}. The site still loads; matches
                cannot start until the API is back.
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </MotionSection>

      {status && (
        <>
          <MotionSection delay={0.05}>
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
                    {status.degraded_modes.map((d, i) => (
                      <motion.li key={d}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                      >{d}</motion.li>
                    ))}
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
          </MotionSection>

          <MotionSection delay={0.1}>
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
          </MotionSection>

          <MotionSection delay={0.12}>
            <div className="panel">
              <span className="panel-title">
                <span className="tick" /> Components
              </span>
              <StaggerContainer style={{ marginTop: 10, display: "grid", gap: 6 }} staggerDelay={0.05}>
                {COMPONENTS.map(([key, label]) => (
                  <StaggerItem key={key} direction="left">
                    <motion.div
                      style={{ display: "flex", justifyContent: "space-between",
                               alignItems: "center", padding: "10px 12px",
                               borderRadius: 10, border: "1px solid var(--line)",
                               background: "rgba(255,255,255,0.015)" }}
                      whileHover={{ borderColor: "var(--line-strong)", x: 2 }}
                    >
                      <span style={{ color: "var(--text)" }}>{label}</span>
                      <Level value={status.components?.[key]} />
                    </motion.div>
                  </StaggerItem>
                ))}
              </StaggerContainer>
            </div>
          </MotionSection>

          <MotionSection delay={0.15}>
            <div className="panel">
              <span className="panel-title">
                <span className="tick" /> Versions &amp; throughput
              </span>
              <StaggerContainer
                className="scorecard"
                style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginTop: 10 }}
                staggerDelay={0.06}
              >
                <StatCard k="Benchmark spec" v={"v" + status.benchmark_version} />
                <StatCard k="Physics / prompt" v={`v${status.physics_version} / v${status.prompt_version}`} />
                <StatCard k="Spec fingerprint" v={<code>{status.spec_fingerprint}</code>} />
                <StatCard k="Queue depth" v={status.queue_depth} />
                <StatCard k="Uptime" v={`${Math.round((status.uptime_s || 0) / 3600)}h`} />
                <StatCard k="Completion rate" v={status.completion_rate != null
                  ? `${Math.round(status.completion_rate * 100)}%` : "—"} />
              </StaggerContainer>
            </div>
          </MotionSection>
        </>
      )}

      {metrics?.storage && (
        <MotionSection delay={0.1}>
          <div className="panel">
            <span className="panel-title">
              <span className="tick" /> Reliability (lifetime + last 24h)
            </span>
            <StaggerContainer
              className="scorecard"
              style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginTop: 10 }}
              staggerDelay={0.04}
            >
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
              ].map(([k, v]) => <StatCard key={k} k={k} v={v} />)}
            </StaggerContainer>
            <p style={{ marginTop: 10, fontSize: 12, color: "var(--dim)" }}>
              Alert thresholds: match failure &gt; 5%, vote failures &gt; 1%,
              fallback rate &gt; 25%.
            </p>
          </div>
        </MotionSection>
      )}

      <MotionSection delay={0.1}>
        <div className="panel">
          <span className="panel-title">
            <span className="tick" /> If matches are failing
          </span>
          <ul style={{ marginTop: 10, paddingLeft: 20, color: "var(--dim)",
                       fontSize: 13, lineHeight: 1.8 }}>
            <li>Most "failures" are upstream free-tier rate limits, not the
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
      </MotionSection>
    </div>
    <SiteFooter />
  </>
  );
}
