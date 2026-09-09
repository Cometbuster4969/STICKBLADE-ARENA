/**
 * Accessibility + display preferences.
 *
 * Persisted in localStorage and applied as `data-*` attributes on <html>,
 * so plain CSS can react without any runtime cost:
 *
 *   data-motion="reduced"  → kill animations, transitions, ticker scroll
 *   data-contrast="high"   → stronger borders/text, no low-contrast dim text
 *   data-fx="off"          → no screen shake / flash / particles in the canvas
 *
 * Reduced motion is also auto-detected from the OS setting
 * (prefers-reduced-motion) the first time a visitor lands — we only store
 * an explicit value once the user actively overrides it (§15).
 */
export const MOTION_KEY = "sba.a11y.motion";
export const CONTRAST_KEY = "sba.a11y.contrast";
export const FX_KEY = "sba.a11y.fx";

function read(key, fallback = null) {
  if (typeof window === "undefined") return fallback;
  try {
    return localStorage.getItem(key);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  if (typeof window === "undefined") return;
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* private mode — preference just won't persist */
  }
}

export function readPrefs() {
  if (typeof window === "undefined") {
    return { motion: "full", contrast: "normal", fx: "on" };
  }
  const storedMotion = read(MOTION_KEY);
  let motion = storedMotion;
  if (!motion) {
    // Respect the OS setting until the user states a preference.
    motion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      ? "reduced"
      : "full";
  }
  return {
    motion,
    contrast: read(CONTRAST_KEY) || "normal",
    fx: read(FX_KEY) || "on",
  };
}

export function applyPrefs(prefs) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.motion = prefs.motion === "reduced" ? "reduced" : "full";
  root.dataset.contrast = prefs.contrast === "high" ? "high" : "normal";
  root.dataset.fx = prefs.fx === "off" ? "off" : "on";
}

export function savePref(patch) {
  const current = readPrefs();
  const next = { ...current, ...patch };
  if (patch.motion != null) write(MOTION_KEY, patch.motion);
  if (patch.contrast != null) write(CONTRAST_KEY, patch.contrast);
  if (patch.fx != null) write(FX_KEY, patch.fx);
  applyPrefs(next);
  return next;
}


// ---------------------------------------------------------------- §6 tier
// Self-declared evaluator tier, persisted so returning evaluators are not
// asked on every single vote. This is a LABEL on the vote, not a weight —
// see components/VotePanel.js.
export const TIER_KEY = "sba.voter.tier";

export function getVoterTier() {
  const v = read(TIER_KEY);
  return v === "expert" ? "expert" : "casual";
}

export function setVoterTier(tier) {
  write(TIER_KEY, tier === "expert" ? "expert" : "casual");
}
