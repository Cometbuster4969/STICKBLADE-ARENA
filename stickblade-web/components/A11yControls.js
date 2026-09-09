"use client";
import { useEffect, useState } from "react";
import { readPrefs, savePref } from "@/lib/prefs";

/**
 * Accessibility controls (action-plan §15).
 *
 * Three switches that matter for this product specifically:
 *   • Reduced motion — the replay, ticker and panels animate constantly.
 *   • High contrast  — the UI leans on dark glass panels and dim text.
 *   • Effects off    — screen shake, hit flashes and particles (vestibular).
 *
 * Reduced motion is pre-set from the OS `prefers-reduced-motion` setting
 * on first load; the toggle lets a visitor override either way.
 */
export default function A11yControls({ compact = false }) {
  const [prefs, setPrefs] = useState({ motion: "full", contrast: "normal",
                                       fx: "on" });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const p = readPrefs();
    setPrefs(p);
    // Apply immediately: the OS setting should win from the first paint
    // even before the user opens this menu.
    import("@/lib/prefs").then((m) => m.applyPrefs(p));
  }, []);

  const toggle = (key, onValue, offValue) => {
    const next = savePref({ [key]: prefs[key] === onValue ? offValue : onValue });
    setPrefs(next);
  };

  const btn = (active, label) => ({
    padding: "6px 10px",
    fontSize: 12,
    borderRadius: 6,
    cursor: "pointer",
    whiteSpace: "nowrap",
    border: `1px solid ${active ? "var(--green)" : "var(--line)"}`,
    background: active ? "rgba(52, 245, 160, 0.12)" : "transparent",
    color: active ? "var(--green)" : "var(--dim)",
    ...label,
  });

  const body = (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                  alignItems: "center" }}>
      <button
        type="button"
        aria-pressed={prefs.motion === "reduced"}
        onClick={() => toggle("motion", "reduced", "full")}
        style={btn(prefs.motion === "reduced")}
        title="Disable animations and transitions"
      >
        {prefs.motion === "reduced" ? "✓ " : ""}Reduced motion
      </button>
      <button
        type="button"
        aria-pressed={prefs.contrast === "high"}
        onClick={() => toggle("contrast", "high", "normal")}
        style={btn(prefs.contrast === "high")}
        title="Stronger borders and text contrast"
      >
        {prefs.contrast === "high" ? "✓ " : ""}High contrast
      </button>
      <button
        type="button"
        aria-pressed={prefs.fx === "off"}
        onClick={() => toggle("fx", "off", "on")}
        style={btn(prefs.fx === "off")}
        title="Disable screen shake, flashes and particles"
      >
        {prefs.fx === "off" ? "✓ " : ""}No effects
      </button>
    </div>
  );

  if (compact) {
    return (
      <div style={{ marginTop: 8 }}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          style={{ fontSize: 12, color: "var(--dim)", background: "none",
                   border: "none", cursor: "pointer", textDecoration: "underline" }}
        >
          ♿ Accessibility options
        </button>
        {open && <div style={{ marginTop: 8 }}>{body}</div>}
      </div>
    );
  }
  return body;
}
