"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

const DISMISS_KEY = "sb_onboarding_dismissed";

/**
 * First-visit onboarding card. Renders above the fight setup on the
 * main route only. Dismisses permanently via localStorage.
 *
 * Placement rule: only on "/" — /leaderboard, /history, /replay,
 * /tournament get nothing (users hitting those routes typically
 * arrived from a share link and already know what the site is).
 *
 * Motion: it slides in after the hero settles and collapses away on dismiss
 * rather than vanishing mid-scroll, so removing it doesn't jump the page.
 */
export default function OnboardingCard() {
  const pathname = usePathname();
  const reduce = useReducedMotion();
  // Start hidden so SSR + first client paint agree; reveal after we've
  // checked localStorage in useEffect. Prevents a hydration flash.
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (pathname !== "/") return;
    try {
      if (localStorage.getItem(DISMISS_KEY) !== "1") setVisible(true);
    } catch {
      // localStorage blocked (private mode etc.) — show the card anyway.
      // Worst case they see it every visit until they use a normal window.
      setVisible(true);
    }
  }, [pathname]);

  function dismiss() {
    setVisible(false);
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch {}
  }

  return (
    <AnimatePresence initial={false}>
      {visible && (
        <motion.div
          layout={!reduce}
          initial={reduce ? { opacity: 1 } : { opacity: 0, y: -16, height: 0 }}
          animate={{ opacity: 1, y: 0, height: "auto" }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, y: -12, height: 0, marginBottom: 0 }}
          transition={{ duration: 0.45, delay: reduce ? 0 : 0.35, ease: [0.16, 1, 0.3, 1] }}
          style={{
            overflow: "hidden",
            borderRadius: 16,
            border: "1px solid rgba(255, 184, 48, 0.3)",
            background:
              "linear-gradient(135deg, rgba(255, 184, 48, 0.07), rgba(255, 51, 85, 0.03) 60%, rgba(255,255,255,0.02))",
            position: "relative",
          }}
        >
          <div style={{ padding: "18px 20px" }}>
            <motion.button
              onClick={dismiss}
              aria-label="Dismiss onboarding"
              whileHover={reduce ? {} : { rotate: 90, scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
              style={{
                position: "absolute", top: 8, right: 10,
                background: "transparent", border: "none",
                color: "var(--dim)", cursor: "pointer",
                fontSize: 18, lineHeight: 1, padding: 4,
              }}>
              ×
            </motion.button>
            <h3 style={{
              margin: "0 0 8px", fontSize: 20, letterSpacing: 1,
              color: "var(--gold)", fontFamily: "var(--font-display), sans-serif",
            }}>
              ⚔️ STICKBLADE ARENA
            </h3>
            <p style={{ margin: "0 0 6px", fontSize: 15, fontWeight: 600, color: "var(--text)" }}>
              Two AIs enter. One leaves. You decide who fought smarter.
            </p>
            <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--dim)", lineHeight: 1.55 }}>
              Pick two language models, choose a weapon and sharp zone, and watch
              them duel in real-time physics. Vote blind — you won&apos;t know which
              model is which until after you judge the fight. Elo rankings update live.
            </p>
            <motion.button
              onClick={dismiss}
              whileHover={reduce ? {} : { scale: 1.04, x: 3 }}
              whileTap={{ scale: 0.97 }}
              style={{
                padding: "9px 18px", borderRadius: 10,
                border: "1px solid var(--gold)",
                background: "var(--gold)", color: "#0b0a06",
                fontWeight: 700, letterSpacing: 1, fontSize: 13,
                cursor: "pointer", textTransform: "uppercase",
              }}>
              Got it →
            </motion.button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
