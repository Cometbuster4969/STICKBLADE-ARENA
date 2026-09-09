"use client";
/**
 * Shared shell for the public research pages (next-step priority 5):
 * /research, /methodology, /data, /reproducibility, /limitations.
 *
 * Every page is a list of sections rendered in the same panel style as the
 * rest of the site, plus an optional live "evidence strip" pulled from
 * /api/data_quality so a page can never claim more than the dataset holds.
 * Prose lives in the page files; this is only the frame.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import DataQualityBanner, { fmtDate } from "@/components/DataQuality";
import { getDataQuality } from "@/lib/api";

export const GITHUB = "https://github.com/Cometbuster4969/STICKBLADE-ARENA";
export const TREE = `${GITHUB}/blob/main`;

export function Code({ children }) {
  return <code style={{ fontSize: "0.92em" }}>{children}</code>;
}

export function Src({ path, line, children }) {
  const href = `${TREE}/${path}${line ? `#L${line}` : ""}`;
  return (
    <a href={href} target="_blank" rel="noreferrer"
       style={{ color: "var(--gold)", textDecoration: "none" }}>
      <code style={{ fontSize: "0.9em" }}>{children || `${path}${line ? `:${line}` : ""}`}</code>
    </a>
  );
}

export function P({ children, style }) {
  return (
    <p style={{ color: "var(--dim)", fontSize: 13.5, lineHeight: 1.75,
                maxWidth: "80ch", margin: "8px 0 0", ...style }}>
      {children}
    </p>
  );
}

export function UL({ items }) {
  return (
    <ul style={{ margin: "8px 0 0", paddingLeft: 20, color: "var(--dim)",
                 fontSize: 13.5, lineHeight: 1.75, maxWidth: "80ch" }}>
      {items.map((it, i) => <li key={i}>{it}</li>)}
    </ul>
  );
}

export function Pre({ children }) {
  return (
    <pre style={{ marginTop: 10, padding: "10px 12px", borderRadius: 6,
                  border: "1px solid var(--line)", background: "rgba(0,0,0,0.25)",
                  color: "var(--text)", fontSize: 12.5, lineHeight: 1.6,
                  overflowX: "auto" }}>
      {children}
    </pre>
  );
}

export function KV({ rows }) {
  return (
    <table className="prov-table" style={{ marginTop: 10 }}>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td style={{ width: "26%", color: "var(--text)", fontWeight: 700,
                         verticalAlign: "top" }}>{k}</td>
            <td style={{ color: "var(--dim)", fontFamily: "inherit",
                         fontSize: 13, lineHeight: 1.6 }}>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Section({ id, title, tone, children }) {
  return (
    <div className="panel" id={id}>
      <span className={`panel-title ${tone || ""}`}>
        <span className="tick" /> {title}
      </span>
      {children}
    </div>
  );
}

/** Live evidence strip. Renders nothing while loading or if the API is down. */
export function EvidenceStrip({ compact = false }) {
  const [q, setQ] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    getDataQuality().then((r) => alive && setQ(r)).catch(() => alive && setErr(true));
    return () => { alive = false; };
  }, []);
  if (err) {
    return (
      <P style={{ color: "var(--mute)" }}>
        Live data-quality report unavailable (backend asleep or unreachable).
        The numbers on this page that depend on it are shown as “—”.
      </P>
    );
  }
  if (!q) return null;
  const s = q.summary || {};
  return (
    <div style={{ marginTop: 10 }}>
      <DataQualityBanner summary={s} cell="the whole dataset" style={{ margin: 0 }} />
      {!compact && (
        <P style={{ marginTop: 8, fontSize: 12.5 }}>
          Live from <Code>/api/data_quality</Code>: {s.matches ?? "—"} finished
          matches · {s.real_provider_matches ?? "—"} real-provider ·{" "}
          {s.mixed_provider_matches ?? "—"} mixed · {s.scripted_matches ?? "—"} scripted
          · {s.real_ranked_matches ?? "—"} real + ranking-eligible (board minimum{" "}
          {s.min_real_for_board ?? "—"}) · fallback {s.fallback_matches ?? "—"} ·
          silent fallback {s.silent_fallback_matches ?? "—"} · token coverage{" "}
          {s.token_coverage == null ? "n/a" : `${Math.round(s.token_coverage * 100)}%`}
          · last match {fmtDate(s.last_match_at)} · benchmark v{q.benchmark_version}
          · prompt v{q.prompt_version ?? "?"} · fingerprint <Code>{q.spec_fingerprint}</Code>
        </P>
      )}
    </div>
  );
}

export const RESEARCH_LINKS = [
  ["/research", "Research"],
  ["/methodology", "Methodology"],
  ["/data", "Data"],
  ["/reproducibility", "Reproducibility"],
  ["/limitations", "Limitations"],
  ["/status", "Status"],
];

export function ResearchSubnav({ current }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
      {RESEARCH_LINKS.map(([href, label]) => (
        <Link key={href} href={href}
              className={`site-nav-link ${current === href ? "active" : ""}`}
              aria-current={current === href ? "page" : undefined}
              style={{ fontSize: 12.5 }}>
          {label}
        </Link>
      ))}
    </div>
  );
}

export default function DocPage({ title, lead, current, children, evidence = true }) {
  return (
    <>
      <SiteNav />
      <div className="container">
        <div className="panel">
          <span className="panel-title gold"><span className="tick" /> {title}</span>
          {lead && <P>{lead}</P>}
          <ResearchSubnav current={current} />
          {evidence && <EvidenceStrip />}
        </div>
        {children}
      </div>
      <SiteFooter />
    </>
  );
}
