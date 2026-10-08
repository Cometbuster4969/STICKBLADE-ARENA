"use client";
/**
 * Recurring events + champions archive (action-plan §31).
 * Motion redesign: scroll-revealed event windows, staggered champion rows.
 */
import { useEffect, useState } from "react";
import { getEvents } from "@/lib/api";
import SiteNav, { SiteFooter } from "@/components/SiteNav";
import { MotionSection, StaggerContainer, StaggerItem, FloatingOrb } from "@/components/MotionSection";

const STATUS = {
  active:   { label: "RUNNING",        tone: "var(--green)" },
  past:     { label: "FINISHED",       tone: "var(--dim)" },
  upcoming: { label: "UPCOMING",       tone: "var(--gold)" },
};

function fmtRange(start, end) {
  const s = new Date(start), e = new Date(end);
  const o = { month: "short", day: "numeric", timeZone: "UTC" };
  const sameMonth = s.getUTCMonth() === e.getUTCMonth();
  const a = s.toLocaleDateString("en-US", o);
  const b = e.toLocaleDateString("en-US", sameMonth
    ? { day: "numeric", timeZone: "UTC" } : o);
  return `${a} – ${b}`;
}

function Window({ w, delay = 0 }) {
  const st = STATUS[w.status] || STATUS.upcoming;
  const champion = w.champion;
  const isActive = w.status === "active";

  return (
    <div
      className="panel"
      data-reveal="up"
      style={{
        padding: 16, marginBottom: 12,
        borderColor: isActive ? "rgba(46, 232, 165, 0.25)" : undefined,
        "--r-in": `${Math.round(delay * 340)}px`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div>
          <b>{w.name}</b>
          <span style={{ color: st.tone, fontSize: 10, marginLeft: 8,
                         letterSpacing: 1, fontWeight: 700,
                         display: "inline-flex", alignItems: "center", gap: 4 }}>
            {isActive && (
              <span
                className="loop-fade"
                style={{ width: 6, height: 6, borderRadius: "50%", background: st.tone }}
              />
            )}
            {st.label}
          </span>
        </div>
        <span style={{ color: "var(--dim)", fontSize: 12 }}>
          {fmtRange(w.start, w.end)}
        </span>
      </div>

      {w.status === "upcoming" ? (
        <p style={{ color: "var(--dim)", fontSize: 12, margin: "8px 0 0" }}>
          {w.blurb}
        </p>
      ) : champion ? (
        <div style={{ marginTop: 8, fontSize: 14 }}>
          🏆 <b style={{ color: "var(--gold)" }}>{champion}</b>
          <span style={{ color: "var(--dim)", fontSize: 12, marginLeft: 8 }}>
            {w.champion_rating} [{w.champion_ci?.[0]}, {w.champion_ci?.[1]}]
            {" · "}{w.comparisons} comparisons
          </span>
        </div>
      ) : (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          <span style={{ color: "var(--dim)" }}>No champion yet — </span>
          {w.reason || "not enough data"}
          {w.comparisons ? (
            <span style={{ color: "var(--dim)", fontSize: 12 }}>
              {" "}{w.comparisons} comparisons recorded
            </span>
          ) : null}
        </div>
      )}

      {w.caveat && (
        <p style={{ color: "var(--red-2)", fontSize: 11,
                    margin: "8px 0 0", lineHeight: 1.5 }}>
          ⚠ {w.caveat}
        </p>
      )}

      {w.rows?.length > 1 && (
        <table className="lb" style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>#</th><th>Model</th>
              <th className="r">Rating</th><th className="r">95% CI</th>
              <th className="r">N</th>
            </tr>
          </thead>
          <tbody>
            {w.rows.slice(0, 6).map((r, i) => (
              <tr key={r.model} className={i === 0 ? "rank-1" : ""}>
                <td>{i + 1}</td>
                <td className="model">{r.name || r.model}</td>
                <td className="r elo">{r.rating}</td>
                <td className="r" style={{ color: "var(--dim)", fontSize: "0.85em" }}>
                  {r.ci_low}–{r.ci_high}
                </td>
                <td className="r" style={{ color: "var(--dim)" }}>{r.matches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SectionHeading({ children }) {
  return (
    <MotionSection>
      <h3 style={{ fontSize: 13, letterSpacing: 2, color: "var(--text-2)",
                   margin: "22px 0 10px", textTransform: "uppercase",
                   fontFamily: "var(--font-display), system-ui, sans-serif",
                   display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 16, height: 2, background: "var(--red)", borderRadius: 1 }} />
        {children}
      </h3>
    </MotionSection>
  );
}

export default function EventsPage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getEvents()
      .then(setData)
      .catch((e) => setErr(e.message));
  }, []);

  const events = data?.events || [];
  const active = events.filter((e) => e.status === "active");
  const upcoming = events.filter((e) => e.status === "upcoming").slice(0, 8);
  const archived = data?.champions || [];

  return (
    <>
      <SiteNav />
      <div style={{ width: "100%", maxWidth: 760, position: "relative" }}>
        <FloatingOrb size={300} color="rgba(46, 232, 165, 0.05)" top="-60px" right="-80px" />

        <MotionSection>
          <h2 style={{ margin: "24px 0 4px",
                       fontFamily: "var(--font-display), system-ui, sans-serif",
                       letterSpacing: 2, textTransform: "uppercase", fontSize: 28, fontWeight: 700 }}>
            Events
          </h2>
        </MotionSection>

        <MotionSection delay={0.05}>
          <p style={{ color: "var(--text-2)", fontSize: 13, marginBottom: 16, lineHeight: 1.7 }}>
            Recurring cups, seasons and challenges. Each event ranks the field
            with the same Bradley–Terry fit the leaderboard uses, and names a
            champion only when the leader is both past the minimum sample and
            statistically separated from the runner-up. Until then it says
            exactly what it is missing.
          </p>
        </MotionSection>

        {err && <div className="status enter-fade">✖ {err}</div>}
        {!data && !err && (
          <div style={{ color: "var(--dim)", fontSize: 13 }}>
            <span className="loop-fade" style={{ "--loop-d": "1.5s", "--loop-mid": "0.4" }}>
              loading events…
            </span>
          </div>
        )}

        {!!active.length && (
          <>
            <SectionHeading>Running now</SectionHeading>
            {active.map((w, i) => <Window key={w.event_id + w.start} w={w} delay={i * 0.08} />)}
          </>
        )}

        {!!upcoming.length && (
          <>
            <SectionHeading>Upcoming</SectionHeading>
            {upcoming.map((w, i) => <Window key={w.event_id + w.start} w={w} delay={i * 0.06} />)}
          </>
        )}

        <SectionHeading>Champions archive</SectionHeading>
        {archived.length ? (
          <MotionSection>
            <div className="panel" style={{ padding: 0, overflow: "hidden" }} data-reveal="fade">
              <table className="lb">
                <thead>
                  <tr>
                    <th>Window</th><th>Event</th><th>Champion</th>
                    <th className="r">Rating</th><th className="r">N</th>
                  </tr>
                </thead>
                <tbody>
                  {archived.map((c) => (
                    <tr key={c.event_id + c.start}>
                      <td style={{ color: "var(--dim)" }}>{fmtRange(c.start, c.end)}</td>
                      <td>{c.name}</td>
                      <td className="model">🏆 {c.champion}</td>
                      <td className="r elo">{c.champion_rating}</td>
                      <td className="r" style={{ color: "var(--dim)" }}>{c.comparisons}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </MotionSection>
        ) : (
          <MotionSection>
            <div className="panel" style={{ color: "var(--dim)", fontSize: 13 }}>
              No event has been decided yet. That is the honest state of a new
              calendar: the archive fills as events clear their minimum sample
              and their leader separates from the field.
            </div>
          </MotionSection>
        )}
      </div>
      <SiteFooter />
    </>
  );
}
