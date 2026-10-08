"use client";
/**
 * Compact accessibility switch-set for the site chrome.
 *
 * The redesign leans hard on motion — scroll reveals, springs, a shine sweep
 * on the fight button — so the "Reduced motion" and "No effects" switches are
 * no longer a nicety, they are the escape hatch. A11yControls already existed
 * with exactly this behaviour but was never mounted on any page; here it is
 * wired into the nav, where it is reachable from every screen.
 *
 * `data-motion="reduced"` is consumed by globals.css; MotionProvider reads the
 * same preference to tell framer-motion to skip transform animations.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import A11yControls from "@/components/A11yControls";

export default function MotionControls() {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
      <motion.button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Display and accessibility options"
        title="Display and accessibility options"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "7px 11px", borderRadius: 10,
          border: `1px solid ${open ? "var(--red)" : "var(--line)"}`,
          background: open ? "rgba(255, 51, 85, 0.1)" : "transparent",
          color: open ? "var(--text)" : "var(--dim)",
          fontSize: 12, fontWeight: 600, cursor: "pointer",
          whiteSpace: "nowrap",
        }}
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.96 }}
      >
        ♿ Motion
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
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
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
