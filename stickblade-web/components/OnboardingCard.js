"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const DISMISS_KEY = "sb_onboarding_dismissed";

/**
 * First-visit onboarding card. Renders above the fight setup on the
 * main route only. Dismisses permanently via localStorage.
 *
 * Placement rule: only on "/" — /leaderboard, /history, /replay,
 * /tournament get nothing (users hitting those routes typically
 * arrived from a share link and already know what the site is).
 */
export default function OnboardingCard() {
  const pathname = usePathname();
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

  if (!visible) return null;

  return (
    <div style={{
      marginBottom: 16, padding: "18px 20px", borderRadius: 8,
      border: "1px solid var(--gold, #d4b962)",
      background: "linear-gradient(135deg, rgba(212, 185, 98, 0.08), rgba(255,255,255,0.02))",
      position: "relative",
    }}>
      <button
        onClick={dismiss}
        aria-label="Dismiss onboarding"
        style={{
          position: "absolute", top: 8, right: 10,
          background: "transparent", border: "none",
          color: "var(--dim)", cursor: "pointer",
          fontSize: 18, lineHeight: 1, padding: 4,
        }}>
        ×
      </button>
      <h3 style={{
        margin: "0 0 8px", fontSize: 20, letterSpacing: 1,
        color: "var(--gold, #d4b962)", fontFamily: "var(--font-display), sans-serif",
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
      <button
        onClick={dismiss}
        style={{
          padding: "8px 16px", borderRadius: 5,
          border: "1px solid var(--gold, #d4b962)",
          background: "var(--gold, #d4b962)", color: "#000",
          fontWeight: 700, letterSpacing: 1, fontSize: 13,
          cursor: "pointer", textTransform: "uppercase",
        }}>
        Got it →
      </button>
    </div>
  );
}
