"use client";
/**
 * Recurring events + champions archive (action-plan §31).
 *
 * A leaderboard is one number that never stops moving; an event is a dated
 * result you can cite. This page is the calendar (what is running, what is
 * next) and the archive (who actually won something).
 *
 * The honesty rule that shapes the whole page: an event with too little
 * data has NO champion. It says exactly how far it is from deciding —
 * "leader has 4 comparisons, needs ≥5" or "intervals overlap, not
 * separable" — instead of crowning a winner nobody can defend.
 */
import { useEffect, useState } from "react";
import { getEvents } from "@/lib/api";
import SiteNav, { SiteFooter } from "@/components/SiteNav";

const STATUS = {
  active:   { label: "RUNNING",        tone: "var(--green, #56dc82)" },
  past:     { label: "FINISHED",       tone: "var(--dim)" },
  upcoming: { label: "UPCOMING",       tone: "var(--gold, #d4b962)" },
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

function Window({ w }) {
  const st = STATUS[w.status] || STATUS.upcoming;
  const champion = w.champion;
  return (
    <div className="panel" style={{ padding: 14, marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div>
          <b>{w.name}</b>
          <span style={{ color: st.tone, fontSize: 10, marginLeft: 8,
                         letterSpacing: 1, fontWeight: 700 }}>
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
          🏆 <b style={{ color: "var(--gold, #d4b962)" }}>{champion}</b>
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
              {" "}({w.comparisons} comparisons recorded)
            </span>
          ) : null}
        </div>
      )}

      {w.caveat && (
        <p style={{ color: "var(--red-2, #dc5656)", fontSize: 11,
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
                <td className="r" style={{ color: "var(--dim)",
                                           fontSize: "0.85em" }}>
                  {r.ci_low}–{r.ci_high}
                </td>
                <td className="r" style={{ color: "var(--dim)" }}>
                  {r.matches}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
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
      <div style={{ width: "100%", maxWidth: 760 }}>
        <h2 style={{ margin: "6px 0 4px" }}>Events</h2>
        <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 16 }}>
          Recurring cups, seasons and challenges. Each event ranks the field
          with the same Bradley–Terry fit the leaderboard uses, and names a
          champion only when the leader is both past the minimum sample and
          statistically separated from the runner-up. Until then it says
          exactly what it is missing.
        </p>

        {err && <div className="status">✖ {err}</div>}
        {!data && !err && (
          <div style={{ color: "var(--dim)", fontSize: 13 }}>loading events…</div>
        )}

        {!!active.length && (
          <>
            <h3 style={{ fontSize: 13, letterSpacing: 1, color: "var(--text-2)",
                         margin: "18px 0 8px" }}>RUNNING NOW</h3>
            {active.map((w) => (
              <Window key={w.event_id + w.start} w={w} />
            ))}
          </>
        )}

        {!!upcoming.length && (
          <>
            <h3 style={{ fontSize: 13, letterSpacing: 1, color: "var(--text-2)",
                         margin: "22px 0 8px" }}>UPCOMING</h3>
            {upcoming.map((w) => (
              <Window key={w.event_id + w.start} w={w} />
            ))}
          </>
        )}

        <h3 style={{ fontSize: 13, letterSpacing: 1, color: "var(--text-2)",
                     margin: "22px 0 8px" }}>CHAMPIONS ARCHIVE</h3>
        {archived.length ? (
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
                  <td style={{ color: "var(--dim)" }}>
                    {fmtRange(c.start, c.end)}
                  </td>
                  <td>{c.name}</td>
                  <td className="model">
                    🏆 {c.champion}
                  </td>
                  <td className="r elo">{c.champion_rating}</td>
                  <td className="r" style={{ color: "var(--dim)" }}>
                    {c.comparisons}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: "var(--dim)", fontSize: 13, padding: "14px 2px" }}>
            No event has been decided yet. That is the honest state of a new
            calendar: the archive fills as events clear their minimum sample
            and their leader separates from the field.
          </div>
        )}
      </div>
      <SiteFooter />
    </>
  );
}
