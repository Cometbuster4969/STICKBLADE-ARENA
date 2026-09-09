"use client";

/**
 * Bradley-Terry rating table with confidence intervals (action-plan §5).
 *
 * Elo answers "who is winning right now" and is fine for that. It cannot
 * answer the question a researcher actually asks — "is this difference
 * real?" — because it has no interval and depends on arrival order. This
 * table fits all voted matches in the cell at once and shows where each
 * model plausibly sits.
 *
 * The important UI decision is the tie-letter column. Publishing a sorted
 * list invites readers to read rank order as a result; two models whose
 * intervals overlap are NOT separated by the data, so they share a letter
 * and the note underneath says so explicitly. Overlapping rows are also
 * dimmed identically so the eye doesn't invent a gap that isn't there.
 */
import { useState } from "react";
import { EvidenceChip, EvidenceMeta } from "@/components/DataQuality";

/**
 * Group rows into statistical-tie bands (compact letter display).
 *
 * Rows are sorted by rating descending. Walking down the list, a row joins
 * the current band when its CI overlaps anything already in the band;
 * otherwise it starts a new band. This is a greedy transitive closure —
 * cheap, stable, and it errs towards "not separable", which is the honest
 * direction to err.
 */
export function tieBands(rows) {
  const sorted = [...rows].sort((a, b) => b.rating - a.rating);
  const bands = [];
  let cur = null;
  for (const r of sorted) {
    if (cur && r.ci_low <= cur.max_hi) {
      cur.max_hi = Math.max(cur.max_hi, r.ci_high);
      cur.rows.push(r);
    } else {
      cur = { max_hi: r.ci_high, rows: [r] };
      bands.push(cur);
    }
  }
  return bands.map((b, i) => ({
    letter: String.fromCharCode(97 + i),          // a, b, c, ...
    rows: b.rows,
  }));
}

function CIBar({ row, min, max }) {
  const span = Math.max(1, max - min);
  const left = ((row.ci_low - min) / span) * 100;
  const width = Math.max(1.5, ((row.ci_high - row.ci_low) / span) * 100);
  const mid = ((row.rating - min) / span) * 100;
  const tone = row.provisional
    ? "rgba(212,185,98,0.55)"
    : "rgba(86,220,130,0.75)";
  return (
    <div
      title={`95% CI ${row.ci_low} – ${row.ci_high}`}
      style={{
        position: "relative", height: 8, width: 92,
        background: "rgba(255,255,255,0.06)",
        borderRadius: 3, overflow: "hidden",
      }}
    >
      <div style={{
        position: "absolute", left: `${left}%`, width: `${width}%`,
        top: 0, bottom: 0, background: tone, borderRadius: 2,
      }} />
      <div style={{
        position: "absolute", left: `${mid}%`, top: 0, bottom: 0,
        width: 2, background: "var(--text)", opacity: 0.9,
      }} />
    </div>
  );
}

export default function RatingTable({ rows, comparisons, bootstraps }) {
  const [sortKey, setSortKey] = useState("rating");
  if (!rows?.length) {
    return (
      <div style={{ color: "var(--dim)", fontSize: 13, padding: "18px 4px", textAlign: "center" }}>
        no voted matches in this cell yet — Bradley-Terry needs comparisons
      </div>
    );
  }

  const bands = tieBands(rows);
  const letterOf = {};
  for (const b of bands) for (const r of b.rows) letterOf[r.model] = b.letter;

  const sorted = [...rows].sort((a, b) =>
    sortKey === "rating" ? b.rating - a.rating
      : sortKey === "ci_low" ? b.ci_low - a.ci_low
        : (b.preference_rate ?? -1) - (a.preference_rate ?? -1));

  const lo = Math.min(...rows.map((r) => r.ci_low));
  const hi = Math.max(...rows.map((r) => r.ci_high));
  const multi = bands.length > 1;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="lb">
        <thead>
          <tr>
            <th title="Rows sharing a letter are NOT statistically separated — their 95% intervals overlap.">
              Tie
            </th>
            <th>Model</th>
            <th className="r" style={{ cursor: "pointer" }}
                onClick={() => setSortKey("rating")}>Rating</th>
            <th title="95% bootstrap confidence interval">95% CI</th>
            <th title="Who actually made the decisions: real providers, a mix, or scripted baselines. Hover for counts.">Evidence</th>
            <th className="r" title="Voted matches this model appears in">N</th>
            <th className="r" title="Human preference rate: wins + half the draws, over voted matches">
              Pref
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.model}
                style={r.provisional ? { opacity: 0.8 } : undefined}>
              <td style={{ color: "var(--gold, #d4b962)", fontWeight: 700 }}>
                {multi || r.provisional ? letterOf[r.model] : ""}
              </td>
              <td className="model">
                {r.name || r.model}
                {r.provisional && (
                  <span
                    title={`Provisional — ${r.matches} comparison${r.matches === 1 ? "" : "s"}, or not connected to the main field. Needs ≥10 in one connected component.`}
                    style={{
                      marginLeft: 6, fontSize: "0.72em", padding: "1px 5px",
                      borderRadius: 3, background: "rgba(212,185,98,0.15)",
                      color: "var(--gold, #d4b962)", fontWeight: 700,
                    }}
                  >
                    ?
                  </span>
                )}
                {r.component_size && r.component > 0 && (
                  <span title={`Only ${r.component_size} models are connected by comparisons in this cell. Ratings from different components are not comparable.`}
                        style={{ marginLeft: 6, fontSize: "0.72em", color: "var(--dim)" }}>
                    ⚠ island
                  </span>
                )}
              </td>
              <td className="r elo">{r.rating}</td>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <CIBar row={r} min={lo} max={hi} />
                  <span style={{ color: "var(--dim)", fontSize: "0.85em",
                                 fontVariantNumeric: "tabular-nums" }}>
                    {r.ci_low}–{r.ci_high}
                  </span>
                </div>
              </td>
              <td>
                <EvidenceChip dq={r.data_quality} />
                <div><EvidenceMeta dq={r.data_quality} /></div>
              </td>
              <td className="r" style={{ color: "var(--dim)" }}>{r.matches}</td>
              <td className="r" style={{ color: "var(--dim)" }}>
                {r.preference_rate == null
                  ? "—"
                  : `${Math.round(r.preference_rate * 100)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 10,
                    padding: "0 4px", letterSpacing: 0.3, lineHeight: 1.7 }}>
        Fitted by maximum likelihood over {comparisons ?? "—"} comparison
        {comparisons === 1 ? "" : "s"}
        {bootstraps ? ` · ${bootstraps} bootstrap resamples` : ""}.
        Intervals overlap → the data cannot separate those models, so they
        share a letter; read them as tied, not ranked.
        <b style={{ color: "var(--gold, #d4b962)" }}> ?</b> = provisional ·
        <b> ⚠ island</b> = too few connecting comparisons to compare against
        the rest of the field.
        <br />
        Scale is Elo-like (400/ln10 per logit, centred on 1000) for
        readability only — this is not Elo and the numbers are not comparable
        to the Elo column.
      </div>
    </div>
  );
}
