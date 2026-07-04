import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import { Inter, Rajdhani } from "next/font/google";

// Self-hosted via next/font — no external font requests, so our strict
// Content-Security-Policy (which omits fonts.googleapis.com) stays intact.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-ui",
  preload: true,
});

const rajdhani = Rajdhani({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
  variable: "--font-display",
  preload: true,
});

export const viewport = {
  themeColor: "#06070d",
  width: "device-width",
  initialScale: 1,
};

export const metadata = {
  title: "STICKBLADE ARENA — LLM Sword Duels",
  description:
    "Two LLM swordsmen. You choose which part of the blade is sharp. " +
    "Physics decides. Vote blind, build the leaderboard.",
  openGraph: {
    title: "STICKBLADE ARENA",
    description: "Watch LLMs sword-fight with real physics. Vote blind.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "STICKBLADE ARENA",
    description: "Watch LLMs sword-fight with real physics. Vote blind.",
  },
  verification: {
    google: "awdrUcE9p7-7pd54xggYPTKN2pnc_p3n4XvzV1mukqY",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${rajdhani.variable}`}>
      <body>
        <header className="site-head">
          <a href="/" className="logo" aria-label="Stickblade Arena home">
            STICK<span className="blade">BLADE</span> ARENA
          </a>
          <nav aria-label="Primary">
            <a href="/" className="active">Fight</a>
            <a href="/tournament">🏆 Tournament</a>
            <a href="/leaderboard">Leaderboard</a>
            <a href="/history">History</a>
          </nav>
        </header>
        <main>{children}</main>
        <footer className="site-foot">
          <div>
            physics-based LLM benchmark · vote blind · sharp zones change everything
          </div>
          <div style={{ marginTop: 8, fontSize: 12, opacity: 0.75,
                        display: "flex", justifyContent: "center", gap: 14,
                        flexWrap: "wrap" }}>
            <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA"
               target="_blank" rel="noreferrer"
               style={{ color: "inherit", textDecoration: "none" }}>
              ⭐ github
            </a>
            <span>·</span>
            <a href="https://github.com/sponsors/Cometbuster4969"
               target="_blank" rel="noreferrer"
               style={{ color: "inherit", textDecoration: "none" }}>
              ❤ sponsor
            </a>
            <span>·</span>
            <span style={{ color: "inherit" }}>
              free-tier throttled? paste your own key in the setup panel
            </span>
          </div>
        </footer>
        <Analytics />
      </body>
    </html>
  );
}
