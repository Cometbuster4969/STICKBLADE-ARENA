"use client";
/**
 * Applies the saved accessibility preferences before anything animates.
 *
 * lib/prefs.js writes data-motion / data-contrast / data-fx on <html>, and
 * every animation in this codebase — the reveal system, the motion utilities,
 * the canvas FX — reads those attributes. So the only job left for a
 * provider is to run applyPrefs() once on mount (A11yControls moved behind
 * the nav popover, so nothing else does it first) and keep the HTML in sync
 * with later toggles. Reduced-motion-aware JS reads the prefs itself via
 * lib/motion.js; no context or config tree is needed.
 */
import { useEffect } from "react";
import { readPrefs, applyPrefs, subscribePrefs } from "@/lib/prefs";

export default function MotionProvider({ children }) {
  useEffect(() => {
    const initial = readPrefs();
    applyPrefs(initial);
    return subscribePrefs(applyPrefs);
  }, []);
  return children;
}
