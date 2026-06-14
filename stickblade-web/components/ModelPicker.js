"use client";
import { useId } from "react";

const CUSTOM = "__custom__";

/* Dropdown of arena models + free-text custom OpenRouter id. */
export default function ModelPicker({ label, models, value, custom,
                                      onChange, onCustomChange, accent }) {
  const isCustom = value === CUSTOM;
  const selectId = useId();
  const inputId = useId();

  // Visually de-emphasize the "(green)/(blue)" suffix and color the dot.
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(label || "");
  const main = m ? m[1] : label;
  const sub = m ? m[2] : null;

  return (
    <div>
      <label
        htmlFor={selectId}
        className="lbl"
        style={{ display: "flex", alignItems: "center", gap: 8 }}
      >
        {accent && (
          <span
            aria-hidden="true"
            style={{
              width: 8, height: 8, borderRadius: 2,
              background: accent,
              boxShadow: `0 0 10px ${accent}`,
              display: "inline-block",
            }}
          />
        )}
        <span style={{ color: "var(--dim)" }}>{main}</span>
        {sub && (
          <span style={{ color: accent || "var(--dim)", letterSpacing: 1 }}>
            · {sub}
          </span>
        )}
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
