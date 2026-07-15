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

const SITE_URL = "https://stickblade-arena.vercel.app";
const OG_IMAGE = `${SITE_URL}/og-image.png`;
const DESCRIPTION =
  "Physics-based LLM benchmark. Two AIs sword-fight, you vote blind. " +
  "Elo tracks who fought smarter.";

export const metadata = {
  // metadataBase makes all relative URLs in `openGraph.images` etc.
  // resolve against the canonical origin. Vercel preview deploys still
  // work because Next only uses this as a fallback base, not an override.
  metadataBase: new URL(SITE_URL),
  title: "STICKBLADE ARENA — Physics-Based LLM Benchmark",
  // Same one-liner across <meta>, OpenGraph, and Twitter so link previews
  // on every platform tell the same story. "Benchmark" is the first content
  // word deliberately — matches how pymunk's showcase page and Google's
  // AI Overview both describe the project, and reads as research-adjacent
  // to a serious ML audience without losing the game-y hook.
  description: DESCRIPTION,
  keywords: [
    "LLM benchmark", "AI evaluation", "physics simulation",
    "spatial reasoning", "Elo leaderboard", "language model comparison",
    "pymunk", "GPT-OSS", "Llama", "Groq", "OpenRouter",
  ],
  authors: [{ name: "Ayush Kumar", url: "https://github.com/Cometbuster4969" }],
  creator: "Ayush Kumar",
  openGraph: {
    title: "STICKBLADE ARENA — Physics-Based LLM Benchmark",
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "Stickblade Arena",
    type: "website",
    locale: "en_US",
    // 1200x630 is the canonical OG size — same aspect for Twitter's
    // summary_large_image, LinkedIn's link preview, and Facebook's
    // Sharing Debugger. Under 8MB (we're ~660KB) so no platform trims it.
    images: [
      {
        url: OG_IMAGE,
        width: 1200,
        height: 630,
        alt: "Two stickmen sword-fighting in a cyberpunk arena — one cyan, one magenta, mid-clash. Elo counter 1247 in the corner.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "STICKBLADE ARENA",
    description: DESCRIPTION,
    images: [OG_IMAGE],
  },
  verification: {
    google: "awdrUcE9p7-7pd54xggYPTKN2pnc_p3n4XvzV1mukqY",
  },
  alternates: {
    canonical: SITE_URL,
  },
};

// schema.org JSON-LD — machine-readable metadata for Google, Perplexity,
// ChatGPT, and other AI aggregators that index the open web. We got a
// spontaneous Google AI Overview mention *without* this markup; adding
// it should make future mentions more accurate (right description, right
// author, right category).
const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Stickblade Arena",
  alternateName: "STICKBLADE ARENA",
  url: SITE_URL,
  description: DESCRIPTION,
  applicationCategory: "DeveloperApplication",
  applicationSubCategory: "LLM Benchmark",
  operatingSystem: "Web",
  browserRequirements: "Requires JavaScript. Requires HTML5.",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  author: {
    "@type": "Person",
    name: "Ayush Kumar",
    url: "https://github.com/Cometbuster4969",
  },
  image: OG_IMAGE,
  screenshot: OG_IMAGE,
  isAccessibleForFree: true,
  license: "https://opensource.org/licenses/MIT",
  softwareVersion: "1.3.0",
  keywords: "LLM benchmark, AI evaluation, physics-based reasoning, Elo leaderboard",
  // Featured / awarded — schema.org/award is the right slot for these.
  award: [
    "Featured on the official Pymunk showcase (pymunk.org)",
    "Bronze — Product of the Day, PeerPush",
  ],
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${rajdhani.variable}`}>
      <head>
        {/* schema.org JSON-LD. Rendered in <head> as a plain <script type=
            "application/ld+json"> — this is the canonical way per Google's
            structured-data docs. Using dangerouslySetInnerHTML because JSX
            escapes the JSON otherwise and breaks the parser. */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
      </head>
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
