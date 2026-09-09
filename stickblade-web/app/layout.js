import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import localFont from "next/font/local";

// Truly self-hosted via next/font/local: the woff2 files ship inside
// @fontsource/* (a normal npm dependency), so the build never reaches out
// to fonts.googleapis.com. That matters twice over — our Content-Security
// Policy omits fonts.googleapis.com, and a build that depends on a third
// party's uptime fails for reasons that have nothing to do with our code.
const inter = localFont({
  src: [
    { path: "../node_modules/@fontsource/inter/files/inter-latin-400-normal.woff2",
      weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/inter/files/inter-latin-500-normal.woff2",
      weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/inter/files/inter-latin-600-normal.woff2",
      weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/inter/files/inter-latin-700-normal.woff2",
      weight: "700", style: "normal" },
  ],
  display: "swap",
  variable: "--font-ui",
  preload: true,
});

const rajdhani = localFont({
  src: [
    { path: "../node_modules/@fontsource/rajdhani/files/rajdhani-latin-500-normal.woff2",
      weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/rajdhani/files/rajdhani-latin-600-normal.woff2",
      weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/rajdhani/files/rajdhani-latin-700-normal.woff2",
      weight: "700", style: "normal" },
  ],
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
// Meta description — 152 chars, under Google's 155-160 SERP truncation.
// Names 3 concrete providers so SERP snippet answers "which models"
// without a click. "Open-source, Apache 2.0" answers the second
// implicit question ("can I trust this / is this a rug"). Prior version
// was 96 chars — 60%% of the CTR budget wasted.
const DESCRIPTION =
  "Physics-based LLM benchmark: GPT-4o, Llama, Kimi and 16+ models " +
  "sword-fight in real physics. Vote blind on who reasoned better. " +
  "Open-source, Apache 2.0.";

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
  // Favicon set — generated from /home/user/logos/stickblade-logo-1-action.png
  // at 16/32/48/180/192/512 sizes. `favicon.ico` is multi-res 16/32/48 so
  // browsers can pick the best. `apple-touch-icon.png` is 180x180 per iOS
  // spec. Android/PWA gets 192 + 512 via site.webmanifest.
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32x32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon-16x16.png", type: "image/png", sizes: "16x16" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180" },
    ],
  },
  manifest: "/site.webmanifest",
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
  license: "https://www.apache.org/licenses/LICENSE-2.0",
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
        {/* Global chrome now lives in <SiteNav/> / <SiteFooter/>, rendered
            by each page. Those are client components, so they can highlight
            the active route and poll live endpoints — the static header and
            footer that used to sit here could do neither. */}
        <main>{children}</main>
        <Analytics />
      </body>
    </html>
  );
}
