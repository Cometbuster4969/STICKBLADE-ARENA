"use client";
import { useId } from "react";
import { normalizeModel } from "@/lib/models";

const CUSTOM = "__custom__";

/* Dropdown of arena models + free-text custom OpenRouter id.

   IMPORTANT — blind voting:
     The picker DOES NOT show a colored swatch tied to the model. That used to
     leak which model became the GREEN ragdoll vs the BLUE one. The server
     randomizes the canvas assignment per match, so we keep the picker neutral
     and only show the slot index (1/2). Terminology is deliberately "Model 1"
     / "Model 2" here: the Fighter A / Fighter B names belong to the replay and
     the vote, and mixing the two was one of the review's terminology findings.

   METADATA LINE (review item 5):
     provider · latency budget · availability, straight from /api/models.
     A 60-90s match reads as a hang unless the cost of a turn is visible at
     the point of choice instead of buried in the FAQ. Every value is derived
     server-side (brains._PROVIDER_HOST / _timeout_for / the 429 cooldown
     map) so it can't drift from what the engine actually does. */
export default function ModelPicker({ label, slotIndex, models, value, custom,
                                      onChange, onCustomChange,
                                      mode = "macro" }) {
  const isCustom = value === CUSTOM;
  const selectId = useId();
  const inputId = useId();
  const metaId = useId();

  // Normalized defensively: stale backends send only {id, name}, and every
  // render path below assumes the full metadata row. est_turn_s is the one
  // field that can't be re-derived, so when it's absent the latency segment
  // hides instead of printing "up to undefineds per turn".
  const picked = normalizeModel(models.find((m) => m.id === value)) || null;
  const latencyText = !picked
    ? null
    : picked.no_api
      ? "no API call — instant"
      : Number.isFinite(picked.est_turn_s)
        ? `up to ${picked.est_turn_s}s per turn`
        : null;

  return (
    <div>
      <label
        htmlFor={selectId}
        className="lbl"
        style={{ display: "flex", alignItems: "center", gap: 8 }}
      >
        {slotIndex != null && (
          <span
            aria-hidden="true"
            style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              width: 18, height: 18, borderRadius: 4,
              background: "var(--bg-3)",
              border: "1px solid var(--line-strong)",
              color: "var(--text-2)",
              fontSize: 11, fontWeight: 700, letterSpacing: 0,
            }}
          >{slotIndex}</span>
        )}
        <span style={{ color: "var(--dim)" }}>{label}</span>
        <span
          style={{ color: "var(--mute)", fontSize: 10, letterSpacing: 1,
                   marginLeft: "auto" }}
          title="The canvas color (green/blue) is randomized per match for blind voting"
        >
          canvas side randomized
        </span>
      </label>
      <select
        id={selectId}
        aria-label={label}
        aria-describedby={picked ? metaId : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
        <option value={CUSTOM}>✏ Custom model id…</option>
      </select>
      {isCustom && (
        <input
          id={inputId}
          aria-label={`${label} custom model id`}
          type="text"
          placeholder="OpenRouter id, e.g. qwen/qwen3-coder:free"
          value={custom}
          onChange={(e) => onCustomChange(e.target.value)}
          style={{ marginTop: 6 }}
          autoFocus
        />
      )}
      {picked && (
        <div className="model-meta" id={metaId}>
          <span>{picked.provider}</span>
          {latencyText && (
            <>
              <span aria-hidden="true">·</span>
              <span>{latencyText}</span>
            </>
          )}
          {picked.reasoning && (
            <>
              <span aria-hidden="true">·</span>
              <span>reasoning</span>
            </>
          )}
          {/* Capability at the point of choice (review item 4): the scripted
              baselines have no joint form, so pairing one with Joint control
              means it is driven by the macro executor. The sim handles it
              instead of erroring, but the user should know before pressing
              Fight rather than reading it in the replay. */}
          {mode === "joint" && picked.modes && !picked.modes.includes("joint") && (
            <span className="badge warn"
                  title="This baseline only speaks macro moves. In a Joint match it is executed by the macro move controller, not by raw joint control.">
              macro only
            </span>
          )}
          {picked.cooldown_s > 0 ? (
            <span className="badge off" title="Upstream provider rate-limited this model recently; the engine will fail over to a buddy model.">
              throttled {picked.cooldown_s}s
            </span>
          ) : picked.no_api ? (
            <span className="badge">scripted</span>
          ) : (
            <span className="badge ok">
              {picked.tier === "free" ? "free tier" : "paid"}
            </span>
          )}
        </div>
      )}
      {isCustom && (
        <div className="model-meta">
          <span className="badge warn">BYOK/custom</span>
          <span>latency unknown — not on the curated roster</span>
        </div>
      )}
    </div>
  );
}
export { CUSTOM };
