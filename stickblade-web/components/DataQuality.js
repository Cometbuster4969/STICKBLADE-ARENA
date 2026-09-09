"use client";

/**
 * Data-quality labels (next-step priority 2).
 *
 * The infrastructure is validated; the model conclusions are not — and a
 * leaderboard that does not say so will be read as if they were. Two pieces:
 *
 *   <DataQualityBanner summary={...} />
 *     Sits above every ranking. Reads `evidence_level` from
 *     /api/data_quality (also embedded in the Bradley–Terry and model_stats
 *     payloads) and says, in one sentence, whether the numbers below are a
 *     scripted baseline, too little real data, or real-provider evidence.
 *
 *   <EvidenceChip dq={row.data_quality} />
 *     Per row. "Scripted baseline" / "Mixed-provider" / "Real-provider" with
 *     a tooltip carrying the counts the next-step plan asks for: matches by
 *     class, ranking-eligible count, fallback count, missing-token count,
 *     last updated date, benchmark version.
 *
 * Labels are taken from the API verbatim so a wording change happens in one
 * place (stickblade/data_quality.py).
 */

const TONE = {
  scripted_baseline: { fg: "var(--dim)",   bg: "rgba(255,255,255,0.06)", border: "var(--line)" },
  mixed_provider:    { fg: "var(--gold, #d4b962)", bg: "rgba(212,185,98,0.12)", border: "rgba(212,185,98,0.45)" },
  real_provider:     { fg: "var(--green)", bg: "rgba(86,220,130,0.12)", border: "rgba(86,220,130,0.45)" },
};

export function fmtDate(epoch) {
  if (!epoch) return "—";
  try {
    return new Date(epoch * 1000).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

export function EvidenceChip({ dq, compact = false }) {
  if (!dq) return null;
  const tone = TONE[dq.evidence] || TONE.scripted_baseline;
  const short = dq.evidence === "real_provider" ? "Real"
    : dq.evidence === "mixed_provider" ? "Mixed" : "Scripted";
  const tip = [
    `${dq.evidence_label} · ${dq.status_label}`,
    `real-provider matches: ${dq.real_provider_matches ?? 0}`,
    `mixed-provider matches: ${dq.mixed_provider_matches ?? 0}`,
    `scripted matches: ${dq.scripted_matches ?? 0}`,
    `ranking-eligible: ${dq.ranking_eligible_matches ?? 0}`,
    `real + ranking-eligible: ${dq.real_ranked_matches ?? 0}`,
    `fallback matches: ${dq.fallback_matches ?? 0}`,
    `missing token usage: ${dq.token_missing_matches ?? 0}`,
    `last match: ${fmtDate(dq.last_match_at)}`,
    `benchmark: v${(dq.benchmark_versions || []).join(", v") || "?"}`,
  ].join("\n");
  return (
    <span
      title={tip}
      aria-label={tip.replace(/\n/g, "; ")}
      style={{
        display: "inline-block", whiteSpace: "nowrap",
        fontSize: compact ? 10 : 10.5, fontWeight: 700, letterSpacing: 0.4,
        padding: compact ? "1px 5px" : "2px 7px", borderRadius: 4,
        color: tone.fg, background: tone.bg, border: `1px solid ${tone.border}`,
        textTransform: "uppercase",
      }}
    >
      {compact ? short : dq.evidence_label}
      {dq.status === "exploratory_only" && (
        <span style={{ marginLeft: 4, opacity: 0.8 }} aria-hidden="true">·&nbsp;exploratory</span>
      )}
    </span>
  );
}

/** Per-row meta line: N, real N, fallback, missing tokens, updated. */
export function EvidenceMeta({ dq }) {
  if (!dq) return null;
  const bits = [];
  if (dq.real_provider_matches) bits.push(`${dq.real_provider_matches} real`);
  if (dq.mixed_provider_matches) bits.push(`${dq.mixed_provider_matches} mixed`);
  if (dq.scripted_matches) bits.push(`${dq.scripted_matches} scripted`);
  if (dq.fallback_matches) bits.push(`${dq.fallback_matches} fallback`);
  if (dq.token_missing_matches) bits.push(`${dq.token_missing_matches} no-token`);
  if (dq.last_match_at) bits.push(`upd ${fmtDate(dq.last_match_at)}`);
  if (!bits.length) return null;
  return (
    <span style={{ color: "var(--mute)", fontSize: 10.5, whiteSpace: "nowrap" }}>
      {bits.join(" · ")}
    </span>
  );
}

export default function DataQualityBanner({ summary, cell = "this cell", style }) {
  if (!summary) return null;
  const lvl = summary.evidence_level;
  const strong = lvl !== "real";
  const tone = lvl === "real" ? TONE.real_provider
    : lvl === "insufficient_real" ? TONE.mixed_provider
    : TONE.scripted_baseline;
  const headline = lvl === "scripted_only"
    ? "Scripted baseline only — these are not model results."
    : lvl === "insufficient_real"
    ? "Insufficient real-provider data — treat every ranking as exploratory."
    : "Real-provider data — rankings still require separable intervals.";
  return (
    <div
      role={strong ? "status" : undefined}
      aria-live={strong ? "polite" : undefined}
      style={{
        display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "baseline",
        padding: "10px 12px", borderRadius: 8, margin: "0 0 12px",
        border: `1px solid ${tone.border}`, background: tone.bg, fontSize: 12.5,
        ...style,
      }}
    >
      <b style={{ color: tone.fg, letterSpacing: 0.3 }}>
        {lvl === "real" ? "✓" : "⚠"} {headline}
      </b>
      <span style={{ color: "var(--dim)" }}>{summary.note}</span>
      <span style={{ color: "var(--mute)", fontSize: 11.5, width: "100%" }}>
        {cell}: {summary.matches} matches ·{" "}
        {summary.real_provider_matches} real-provider ·{" "}
        {summary.mixed_provider_matches} mixed ·{" "}
        {summary.scripted_matches} scripted ·{" "}
        {summary.real_ranked_matches}/{summary.min_real_for_board} real ranked needed ·{" "}
        fallback {summary.fallback_matches} ·{" "}
        token coverage {summary.token_coverage == null ? "n/a" : `${Math.round(summary.token_coverage * 100)}%`} ·{" "}
        last match {fmtDate(summary.last_match_at)} ·{" "}
        benchmark v{(summary.benchmark_versions || []).join(", v") || "?"}
        {" · "}
        <b style={{ color: "var(--text-2)" }}>infrastructure validated</b>
        {" ≠ "}
        <b style={{ color: summary.model_conclusions_validated ? "var(--green)" : "var(--red-2)" }}>
          model conclusions {summary.model_conclusions_validated ? "validated" : "not validated"}
        </b>
      </span>
    </div>
  );
}
