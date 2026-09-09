"use client";
import IntegrityBadge from "@/components/IntegrityBadge";
import ShareBar from "@/components/ShareBar";

/**
 * Match result scorecard (action-plan §14).
 *
 * Everything a reviewer needs in one compact panel: winner, final HP,
 * method, the human tactical vote, per-fighter operational stats
 * (latency, invalid actions, fallback, provider actually used), the
 * provenance record, and the actions they'd want next (rematch, share).
 *
 * Colour is never the only signal: fighters are always labelled A/B and
 * named after the reveal (§15).
 */
function Cell({ k, v, title }) {
  return (
    <div className="cell" title={title}>
      <div className="k">{k}</div>
      <div className="v">{v ?? "—"}</div>
    </div>
  );
}

export default function ResultScorecard({ matchId, voteResult, replay,
                                          integrity, onRematch, onCompare }) {
  if (!voteResult) return null;
  const meta = replay?.meta || {};
  const prov = meta.provenance || {};
  const tel = meta.telemetry || {};
  const finalHp = meta.result?.final_hp || {};
  const names = voteResult.names || {};
  const aModel = voteResult.canvas_a_model;
  const bModel = voteResult.canvas_b_model;
  const nameA = names[aModel] || aModel;
  const nameB = names[bModel] || bModel;

  const winnerSide = voteResult.engine_winner_side;
  const hpA = finalHp["Fighter A"];
  const hpB = finalHp["Fighter B"];

  const stat = (side) => {
    const t = tel[side] || {};
    const providers = Object.keys(t.providers_used || {}).join(", ");
    return {
      latency: t.latency_ms_avg != null ? `${Math.round(t.latency_ms_avg)} ms` : "—",
      invalid: t.invalid_actions ?? "—",
      fallback: t.fallback_turns ?? "—",
      providers: providers || "—",
    };
  };
  const sa = stat("a");
  const sb = stat("b");

  return (
    <div className="panel reveal-card" aria-live="polite">
      <span className="panel-title">
        <span className="tick" /> Match Scorecard
      </span>

      <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap",
                    alignItems: "center" }}>
        <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: 0.5 }}>
          {winnerSide === "draw"
            ? "Draw"
            : `Fighter ${String(winnerSide || "").toUpperCase()} wins`}
        </span>
        <span className="badge">{voteResult.method}</span>
        <span className="badge">{meta.total_turns ?? voteResult.turns ?? "?"} turns</span>
        <IntegrityBadge matchId={matchId} compact />
      </div>

      {voteResult.commentary && (
        <div style={{
          padding: "10px 14px", marginTop: 12, borderRadius: 6,
          background: "rgba(255, 197, 71, 0.08)",
          border: "1px dashed var(--gold, #ffc547)",
          fontSize: 13, lineHeight: 1.55, color: "var(--text)",
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1.5,
                         color: "var(--gold, #ffc547)", textTransform: "uppercase",
                         display: "block", marginBottom: 4 }}>
            🎙 AI Commentator Post-Fight Roast
          </span>
          "{voteResult.commentary}"
        </div>
      )}

      <div className="scorecard">
        <Cell k="Fighter A (green)" v={nameA}
              title="Model that rendered as Fighter A" />
        <Cell k="Fighter B (blue)" v={nameB}
              title="Model that rendered as Fighter B" />
        <Cell k="Final HP" v={`${hpA ?? "?"} / ${hpB ?? "?"}`}
              title="Fighter A HP / Fighter B HP" />
        <Cell k="Decision latency (avg)"
              v={`${sa.latency} · ${sb.latency}`}
              title="Mean per-turn model response time, A / B" />
        <Cell k="Invalid actions" v={`${sa.invalid} · ${sb.invalid}`}
              title="Turns where the model emitted an out-of-vocabulary action" />
        <Cell k="Fallback turns" v={`${sa.fallback} · ${sb.fallback}`}
              title="Turns played by a scripted brain after provider failure" />
        <Cell k="Providers used" v={`${sa.providers} · ${sb.providers}`}
              title="Which infrastructure actually served the decisions" />
        <Cell k="Human tactical vote"
              v={voteResult.user_choice
                 ? `Fighter ${String(voteResult.user_choice).toUpperCase()}`
                 : "recorded"}
              title="The vote that moved the rating" />
        <Cell k="Elo delta"
              v={[aModel, bModel]
                .map((m) => {
                  const d = voteResult.elo_change?.[m];
                  if (d == null) return null;
                  return `${d >= 0 ? "+" : ""}${d}`;
                })
                .filter(Boolean)
                .join(" / ") || "not ranked"}
              title={voteResult.exclusion_reason || "Elo change (K=32)"} />
      </div>

      {voteResult.ranking_excluded && (
        <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 6,
                      border: "1px solid rgba(255, 197, 71, 0.35)",
                      background: "rgba(255, 197, 71, 0.06)",
                      fontSize: 12, color: "var(--dim)" }}>
          ⚠ <b>Not ranked:</b> {voteResult.exclusion_reason} — the vote was
          still recorded.
        </div>
      )}

      <table className="prov-table" style={{ marginTop: 12 }}>
        <tbody>
          <tr>
            <td>benchmark</td>
            <td>v{prov.benchmark_version} · physics v{prov.physics_version} ·
              prompt v{prov.prompt_version}</td>
          </tr>
          <tr>
            <td>config</td>
            <td>{prov.weapon} · {prov.arena} · {prov.mode}
              {prov.blindfolded ? " · blindfolded" : ""} · sharp {prov.sharp}</td>
          </tr>
          <tr>
            <td>seed / fingerprint</td>
            <td>{prov.seed ?? "unseeded"} · <code>{prov.spec_fingerprint}</code></td>
          </tr>
        </tbody>
      </table>

      <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap",
                    alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {onRematch && (
            <button className="btn-secondary" onClick={onRematch}>
              ⟲ Rematch
            </button>
          )}
          {onCompare && (
            <button className="btn-secondary" onClick={onCompare}>
              ⚔ Compare another matchup
            </button>
          )}
        </div>
        <ShareBar matchId={matchId} result={voteResult} replay={replay} />
      </div>

      {integrity != null && <IntegrityBadge matchId={matchId} />}
    </div>
  );
}
