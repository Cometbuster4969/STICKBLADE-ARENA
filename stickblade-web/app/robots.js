// Next.js 15 file-based robots.txt generator. Emitted at /robots.txt
// at build time — no runtime overhead, no crawler mis-configuration risk.
//
// Policy:
//   - Every legitimate crawler is allowed everywhere. There is nothing
//     private on this site; the whole product IS a public leaderboard.
//   - GPTBot / Claude-Web / CCBot / Google-Extended / anthropic-ai are
//     explicitly allowed. Since the entire project positions itself as a
//     public LLM benchmark, being cited in AI-generated answers is a
//     feature, not a leak. AGENTS.md rule #0 lives in the *repo*, not
//     the deployed site — nothing crawlable here is sensitive.
//   - Content-Signal directive (contentsignals.org) declares our
//     AI-usage preferences in a machine-readable way:
//         ai-train=yes  → OK for model training
//         search=yes    → OK for search indexing
//         ai-input=yes  → OK for RAG / grounding in AI answers
//     Same reasoning: this is a public research artifact, we WANT it
//     ingested.

const HOST = "https://stickblade-arena.vercel.app";

export default function robots() {
  return {
    rules: [
      { userAgent: "*", allow: "/" },
      // Explicit per-bot rules for Nilkick's Tier-1 agent-readiness signal.
      { userAgent: "GPTBot", allow: "/" },
      { userAgent: "ChatGPT-User", allow: "/" },
      { userAgent: "OAI-SearchBot", allow: "/" },
      { userAgent: "ClaudeBot", allow: "/" },
      { userAgent: "Claude-Web", allow: "/" },
      { userAgent: "anthropic-ai", allow: "/" },
      { userAgent: "CCBot", allow: "/" },
      { userAgent: "Google-Extended", allow: "/" },
      { userAgent: "PerplexityBot", allow: "/" },
      { userAgent: "cohere-ai", allow: "/" },
    ],
    sitemap: `${HOST}/sitemap.xml`,
    host: HOST,
  };
}
