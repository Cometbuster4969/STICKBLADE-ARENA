// Next.js 15 file-based sitemap generator. Emitted at /sitemap.xml at
// build time. Kept minimal on purpose — only the routes worth ranking:
// the fight page, the leaderboard, the tournament bracket, the history
// list. Replay pages (/replay?id=...) are per-match and infinite; no
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
  ];
}
