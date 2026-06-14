"use client";
import { useId } from "react";

const CUSTOM = "__custom__";

/* Dropdown of arena models + free-text custom OpenRouter id.

   IMPORTANT — blind voting:
     The picker DOES NOT show a colored swatch tied to the model. That used to
     leak which model became the GREEN ragdoll vs the BLUE one. The server now
     randomizes the canvas assignment per match, so we keep the picker neutral
     and only show the slot index (1/2). */
export default function ModelPicker({ label, slotIndex, models, value, custom,
                                      onChange, onCustomChange }) {
  const isCustom = value === CUSTOM;
  const selectId = useId();
  const inputId = useId();

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
          color randomized
        </span>
      </label>
      <select
        id={selectId}
        aria-label={label}
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
    </div>
  );
}
export { CUSTOM };
