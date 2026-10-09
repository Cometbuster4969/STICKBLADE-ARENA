"use client";
// Shared site chrome (action-plan §23/§28/§35): every page should be able to
// reach the trust report, the live status page, and the public dataset
// dashboard without hunting through the footer of a single screen.
//
// Motion redesign: the header is sticky and condenses as you scroll (padding
// + border tighten, backdrop blur deepens), the active link carries a glow
// pill, and the accessibility switch-set is finally reachable from every page.
// All of it is CSS + transitions — the nav ships zero animation JS.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import MotionControls from "@/components/MotionControls";

const LINKS = [
  ["/", "Fight"],
  ["/tournament", "🏆 Tournament"],
  ["/leaderboard", "📊 Leaderboard"],
  ["/history", "🕘 History"],
  ["/events", "📅 Events"],
  ["/dashboard", "🧪 Dataset"],
  ["/research", "📄 Research"],
  ["/status", "🟢 Status"],
  ["/trust", "🔒 Trust"],
];

export default function SiteNav({ compact = false }) {
  const path = usePathname() || "/";
  const [scrolled, setScrolled] = useState(false);

  // Condense-on-scroll. One passive listener writing a single boolean, and
  // only when it actually crosses the threshold — no per-frame state churn.
  useEffect(() => {
    const onScroll = () => {
      const next = window.scrollY > 24;
      setScrolled((prev) => (prev === next ? prev : next));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className="site-nav"
      aria-label="Site"
      data-hero-in=""
      style={{
        background: scrolled ? "rgba(238, 240, 233, 0.92)" : "rgba(238, 240, 233, 0.8)",
        borderBottomColor: scrolled ? "var(--line-strong)" : "var(--line)",
        transition: "background 0.35s var(--ease-smooth), border-color 0.35s var(--ease-smooth)",
      }}
    >
      <div
        className="site-nav-inner"
        style={{
          paddingTop: scrolled ? 8 : 12,
          paddingBottom: scrolled ? 8 : 12,
          transition: "padding 0.35s var(--ease-smooth)",
        }}
      >
        <Link href="/" className="site-nav-brand" aria-label="Stickblade Arena home">
          <span className="brand-sword" aria-hidden="true">⚔</span>
          <span>STICKBLADE</span>
          <span style={{ color: "var(--red)" }}>ARENA</span>
        </Link>

        <div className="site-nav-links">
          {LINKS.map(([href, label]) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`site-nav-link ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                style={{ position: "relative" }}
              >
                {label}
                {active && <span aria-hidden="true" className="nav-active-glow" />}
              </Link>
            );
          })}
        </div>

        <MotionControls />
      </div>

      <p
        className="site-nav-tag"
        style={{ overflow: "hidden", opacity: scrolled ? 0 : 1,
                 height: scrolled ? 0 : "auto",
                 transition: "opacity 0.3s var(--ease-smooth), height 0.3s var(--ease-smooth)" }}
      >
        Blind-voted LLM duels on deterministic physics, with published integrity data.
      </p>
    </nav>
  );
}

export function SiteFooter() {
  const FOOT = [
    ["/", "Fight"],
    ["/leaderboard", "Leaderboard"],
    ["/history", "History"],
    ["/events", "Events"],
    ["/replay", "Replay a match"],
    ["/tournament", "Tournament"],
    ["/dashboard", "Dataset dashboard"],
    ["/research", "Research"],
    ["/methodology", "Methodology"],
    ["/data", "Data"],
    ["/reproducibility", "Reproducibility"],
    ["/limitations", "Limitations"],
    ["/status", "Status"],
    ["/trust", "Trust & privacy"],
  ];

  return (
    <footer className="site-footer">
      <div className="site-footer-links">
        {FOOT.map(([href, label]) => (
          <a key={href} href={href} data-press style={{ "--hy": "-1px" }}>
            {label}
          </a>
        ))}
        <a href="https://stick-web.vercel.app"
           target="_blank" rel="noreferrer">overview site</a>
        <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA"
           target="_blank" rel="noreferrer">⭐ github</a>
        <a href="https://github.com/sponsors/Cometbuster4969"
           target="_blank" rel="noreferrer">❤ sponsor</a>
      </div>
      <p className="site-footer-note">
        physics-based LLM benchmark · vote blind · sharp zones change
        everything. Free-tier throttled? Paste your own key in the setup
        panel. Every match ships a provenance record (spec / physics / prompt
        version + seed + action log) so any published result can be re-run
        and audited. Rankings come from blind human votes, not self-reported
        scores.
      </p>
    </footer>
  );
}
