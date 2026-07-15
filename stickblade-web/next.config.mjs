import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

// Resolve the absolute path of Next's hard-coded legacy-JS polyfill module
// so we can alias it to an empty stub. Wrapped in a try so a future Next
// refactor that removes/renames the file doesn't break the build.
let nextPolyfillModulePath = null;
try {
  nextPolyfillModulePath = require.resolve(
    "next/dist/build/polyfills/polyfill-module"
  );
} catch {
  /* polyfill module gone in a future Next version — nothing to alias */
}

/** @type {import('next').NextConfig} */

// --- Security headers -------------------------------------------------------
// CSP allows Next.js (which requires 'unsafe-inline' for its hydration data
// and injected styles) plus Vercel Analytics and the HF Space backend.
// Trusted Types is added in Report-Only so we don't break Next's runtime,
// but still satisfies the Lighthouse "Mitigate DOM-based XSS" advisory.
const API_ORIGIN = "https://pioneer37-stickman-arena.hf.space";

const ContentSecurityPolicy = [
  "default-src 'self'",
  // Next.js injects inline scripts for hydration data; Vercel Analytics
  // beacon comes from va.vercel-scripts.com.
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://va.vercel-scripts.com",
  "script-src-elem 'self' 'unsafe-inline' https://va.vercel-scripts.com",
  // Inline styles are emitted by Next's CSS-in-JS and style tags.
  "style-src 'self' 'unsafe-inline'",
  "style-src-elem 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${API_ORIGIN} https://va.vercel-scripts.com https://vitals.vercel-insights.com`,
  "media-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "manifest-src 'self'",
  "upgrade-insecure-requests",
].join("; ");

const ReportOnlyTrustedTypes = [
  "require-trusted-types-for 'script'",
  "trusted-types nextjs default 'allow-duplicates'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: ContentSecurityPolicy },
  { key: "Content-Security-Policy-Report-Only", value: ReportOnlyTrustedTypes },
  // Clickjacking — frame-ancestors above is the modern equivalent, XFO is
  // kept for very old browsers.
  { key: "X-Frame-Options", value: "DENY" },
  // Cross-origin isolation.
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  // MIME-sniff protection.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Strict referrer policy.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Lock down powerful APIs we don't use.
  {
    key: "Permissions-Policy",
    value: [
      "accelerometer=()",
      "ambient-light-sensor=()",
      "autoplay=()",
      "battery=()",
      "camera=()",
      "display-capture=()",
      "document-domain=()",
      "encrypted-media=()",
      "fullscreen=(self)",
      "geolocation=()",
      "gyroscope=()",
      "magnetometer=()",
      "microphone=()",
      "midi=()",
      "payment=()",
      "picture-in-picture=()",
      "publickey-credentials-get=()",
      "screen-wake-lock=()",
      "sync-xhr=()",
      "usb=()",
      "xr-spatial-tracking=()",
    ].join(", "),
  },
  // HSTS — Vercel serves HTTPS everywhere, so this is safe.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "X-DNS-Prefetch-Control", value: "on" },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Modern browsers only — keeps the SWC/Next polyfill list (Array.prototype.at,
  // flat, flatMap, Object.fromEntries, Object.hasOwn, String trimStart/trimEnd)
  // out of the client bundle. See package.json#browserslist.
  compress: true,
  env: {
    // Point this at your deployed FastAPI backend (HF Space URL).
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
  // Strip Next.js's hard-coded legacy-JS polyfill module from the client
  // bundle (~11 KiB) since our browserslist only targets modern browsers
  // that already implement Array.prototype.at/flat/flatMap, Object.fromEntries,
  // Object.hasOwn, String.prototype.trimStart/trimEnd, etc.
  webpack: (config, { isServer }) => {
    if (!isServer && nextPolyfillModulePath) {
      const stub = path.resolve(__dirname, "empty-polyfills.js");
      config.resolve = config.resolve || {};
      // Alias by both the bare module specifier (in case anything imports it
      // directly) and the absolute resolved path (which is what Next's own
      // internal relative import `'../build/polyfills/polyfill-module'`
      // resolves to). Suffixing with `$` makes the match exact.
      config.resolve.alias = {
        ...(config.resolve.alias || {}),
        "next/dist/build/polyfills/polyfill-module$": stub,
        [nextPolyfillModulePath]: stub,
      };
    }
    return config;
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      // Long-cache immutable Next static assets (already default on Vercel,
      // but explicit doesn't hurt).
      {
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
      // RFC 8288 Link headers on the homepage — pointers agents can use to
      // discover useful resources without parsing HTML. Three declared:
      //   - `describedby` → /llms.txt (short site description for LLMs)
      //   - `alternate`   → /llms-full.txt (full ref content, type=text/markdown)
      //   - `service-doc` → OpenAPI schema at the backend (agent-consumable API contract)
      //     (currently /docs on FastAPI; when we ship /openapi.json versioned, swap.)
      // These are additive — no browser cares, but agent readers (Nilkick,
      // Cloudflare Markdown-for-Agents, custom crawlers) find them cleanly.
      {
        source: "/",
        headers: [
          {
            key: "Link",
            value: [
              '</llms.txt>; rel="describedby"; type="text/markdown"',
              '</llms-full.txt>; rel="alternate"; type="text/markdown"; title="Full reference (llms-full.txt)"',
              '<https://pioneer37-stickman-arena.hf.space/docs>; rel="service-doc"; type="text/html"; title="Backend API docs (FastAPI)"',
            ].join(", "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
