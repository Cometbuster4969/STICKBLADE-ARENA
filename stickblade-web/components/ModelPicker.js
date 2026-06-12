"use client";
import { useState } from "react";

const CUSTOM = "__custom__";

/* Dropdown of arena models + free-text custom OpenRouter id. */
export default function ModelPicker({ label, models, value, custom,
                                      onChange, onCustomChange, accent }) {
  const isCustom = value === CUSTOM;
  return (
    <div>
      <label className="lbl" style={accent ? { color: accent } : undefined}>
        {label}
      </label>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
        <option value={CUSTOM}>✏ Custom model id…</option>
      </select>
      {isCustom && (
        <input
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
