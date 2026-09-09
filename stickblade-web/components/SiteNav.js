"use client";
// Shared site chrome (action-plan §23/§28/§35): every page should be able to
// reach the trust report, the live status page, and the public dataset
// dashboard without hunting through the footer of a single screen. The arena
// has exactly one entry point (the fight page) — everything else is one click
// away or invisible, which is how a "we publish our integrity numbers" claim
// turns into a navigation dead end.
import Link from "next/link";
import { usePathname } from "next/navigation";

// Superset of the old layout-level nav, which linked only Fight /
// Tournament / Leaderboard / History. Nothing that used to be reachable
// from the header is dropped here.
const LINKS = [
  ["/", "⚔ Fight"],
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
  return (
    <nav className="site-nav" aria-label="Site">
      <div className="site-nav-inner">
        <Link href="/" className="site-nav-brand" aria-label="Stickblade Arena home">
          <span aria-hidden="true">⚔</span> STICKBLADE ARENA
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
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>
      {!compact && (
        <p className="site-nav-tag">
          Blind-voted LLM duels · deterministic physics · published integrity data
        </p>
      )}
    </nav>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-links">
        <Link href="/">Fight</Link>
        <Link href="/leaderboard">Leaderboard</Link>
        <Link href="/history">History</Link>
        <Link href="/events">Events</Link>
        <Link href="/replay">Replay a match</Link>
        <Link href="/tournament">Tournament</Link>
        <Link href="/dashboard">Dataset dashboard</Link>
        <Link href="/research">Research</Link>
        <Link href="/methodology">Methodology</Link>
        <Link href="/data">Data</Link>
        <Link href="/reproducibility">Reproducibility</Link>
        <Link href="/limitations">Limitations</Link>
        <Link href="/status">Status</Link>
        <Link href="/trust">Trust &amp; privacy</Link>
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
