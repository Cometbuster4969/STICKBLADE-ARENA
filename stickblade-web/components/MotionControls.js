"use client";
/**
 * Compact accessibility switch-set for the site chrome.
 *
 * The redesign leans hard on motion — scroll reveals, presses, a shine sweep
 * on the fight button — so the "Reduced motion" and "No effects" switches are
 * no longer a nicety, they are the escape hatch. A11yControls already existed
 * with exactly this behaviour but was never mounted on any page; here it is
 * wired into the nav, where it is reachable from every screen.
 *
 * `data-motion="reduced"` is consumed by globals.css (every animation here is
 * CSS, so there is nothing else to notify). The popover's in/out choreography
 * is a `.swap` class + useSwap, which keeps the node mounted just long enough
 * for the leave keyframes to play.
 */
import { useState } from "react";
import { useSwap } from "@/lib/motion";
import A11yControls from "@/components/A11yControls";

export default function MotionControls() {
  const [open, setOpen] = useState(false);
  const [mounted, closing] = useSwap(open);

  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Display and accessibility options"
        title="Display and accessibility options"
        data-press
        style={{
          "--ph": "1.04", "--pt": "0.96",
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "7px 11px", borderRadius: 10,
          border: `1px solid ${open ? "var(--red)" : "var(--line)"}`,
          background: open ? "var(--wash-2)" : "transparent",
          color: open ? "var(--text)" : "var(--dim)",
          fontSize: 12, fontWeight: 600, cursor: "pointer",
          whiteSpace: "nowrap",
          transition: "transform 0.24s var(--ease-spring), border-color 0.2s, background 0.2s, color 0.2s",
        }}
      >
        ♿ Motion
      </button>

      {mounted && (
        <div
          className="swap"
          data-out={closing ? "" : undefined}
          style={{
            position: "absolute", top: "calc(100% + 10px)", right: 0,
            padding: 14, borderRadius: 14, zIndex: 300,
            background: "var(--bg-2-solid)",
            border: "1px solid var(--line-strong)",
            boxShadow: "var(--shadow-soft)",
            whiteSpace: "nowrap",
          }}
        >
          <A11yControls />
        </div>
      )}
    </div>
  );
}
