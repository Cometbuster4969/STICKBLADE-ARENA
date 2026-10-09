import "./globals.css";
import { Analytics } from "@vercel/analytics/next";
import localFont from "next/font/local";
import MotionProvider from "@/components/MotionProvider";
import ScrollProgress from "@/components/ScrollProgress";

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

// Big Shoulders: a condensed, engineering-plate display face. Sentence-case
// headings in it read like drawing title blocks — that's why it took over the
// display slot in the "kinematics plate" redesign.
const bigShoulders = localFont({
  src: [
    { path: "../node_modules/@fontsource/big-shoulders/files/big-shoulders-latin-500-normal.woff2",
      weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/big-shoulders/files/big-shoulders-latin-700-normal.woff2",
      weight: "700", style: "normal" },
    { path: "../node_modules/@fontsource/big-shoulders/files/big-shoulders-latin-800-normal.woff2",
      weight: "800", style: "normal" },
  ],
  display: "swap",
  variable: "--font-display",
  preload: true,
});

export const viewport = {
  themeColor: "#e7e9e2",
  width: "device-width",
  initialScale: 1,
};

const SITE_URL = "https://stickblade-arena.vercel.app";
const OG_IMAGE = `${SITE_URL}/og-image.png`;
// Meta description — 152 chars, under Google's 155-160 SERP truncation.
// Names 3 concrete providers so SERP snippet answers "which models"
// without a click. "Open-source, Apache 2.0" answers the second
// implicit question ("can I trust this / is this a rug").
const DESCRIPTION =
  "Physics-based LLM benchmark: GPT-4o, Llama, Kimi and 16+ models " +
  "sword-fight in real physics. Vote blind on who reasoned better. " +
  "Open-source, Apache 2.0.";

export const metadata = {
  metadataBase: new URL(SITE_URL),
  title: "STICKBLADE ARENA — Physics-Based LLM Benchmark",
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
  award: [
    "Featured on the official Pymunk showcase (pymunk.org)",
    "Bronze — Product of the Day, PeerPush",
  ],
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${bigShoulders.variable}`}>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
      </head>
      <body>
        {/* Skip link — the nav is a motion-animated sticky header, so
            keyboard users get a one-press route to the content. */}
        <a href="#main" className="skip-link">Skip to content</a>
        {/* MotionProvider applies the saved ♿ preferences (reduced motion,
            contrast, effects) to <html> before anything animates. All motion
            is CSS-driven — see lib/motion.js for the three hooks on the JS
            side. ScrollProgress is the page-level reading rail. */}
        <MotionProvider>
          <ScrollProgress />
          <main id="main">{children}</main>
        </MotionProvider>
        <Analytics />
      </body>
    </html>
  );
}
