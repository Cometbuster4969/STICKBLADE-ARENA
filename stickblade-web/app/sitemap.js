// Next.js 15 file-based sitemap generator. Emitted at /sitemap.xml at
// build time. Kept minimal on purpose — only the routes worth ranking:
// the fight page, the leaderboard, the tournament bracket, the history
// list, and the three credibility pages (dataset dashboard, trust, status). Replay pages (/replay?id=...) are per-match and infinite; no
// value in listing them here (Google won't like them anyway, and Vercel
// analytics shows the org traffic goes to root + /leaderboard).

const HOST = "https://stickblade-arena.vercel.app";
const now = new Date();

export default function sitemap() {
  return [
    {
      url: HOST,
      lastModified: now,
      changeFrequency: "daily",  // Leaderboard on root, matches finish hourly
      priority: 1.0,
    },
    {
      url: `${HOST}/leaderboard`,
      lastModified: now,
      changeFrequency: "hourly", // Elo shifts every completed vote
      priority: 0.9,
    },
    {
      url: `${HOST}/tournament`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.7,
    },
    {
      url: `${HOST}/history`,
      lastModified: now,
      changeFrequency: "hourly",
      priority: 0.6,
    },
    {
      // Action-plan §28: the public dataset dashboard is the page a
      // researcher lands on from a citation, so it has to be indexable.
      url: `${HOST}/dashboard`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.6,
    },
    {
      // §23 / §35 — trust + status. Low commercial value, high credibility
      // value: someone evaluating whether to trust our numbers searches for
      // exactly these.
      url: `${HOST}/trust`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.4,
    },
    // Next-step priority 5: the five research pages a reviewer or citing
    // paper lands on. Monthly — prose changes with the methodology, not
    // with match volume.
    ...["research", "methodology", "data", "reproducibility", "limitations"].map((p) => ({
      url: `${HOST}/${p}`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    })),
    {
      url: `${HOST}/status`,
      lastModified: now,
      changeFrequency: "hourly",
      priority: 0.4,
    },
  ];
}
