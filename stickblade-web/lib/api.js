// Empty base = same-origin. The Next server proxies /api/* to the backend
// (see next.config.mjs rewrites), so the browser never needs to know the
// backend's host — which is what makes preview URLs, LAN testing and local
// dev all work with one configuration. Set NEXT_PUBLIC_API_BASE only to
// talk to a backend on another origin.
const BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/+$/, "");

export async function api(path, opts) {
  const r = await fetch(`${BASE}/api${path}`, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const getModels = () => api("/models");
export const getHealth = () => api("/health");

/**
 * Keepalive ping — fires every 5 minutes while a tab is open so the HF
 * Space backend doesn't go to sleep mid-session (cold-starts take 30-60s
 * and were the #1 cause of "LLM timeout" fallbacks in real user matches).
 * Returns a cleanup function. Use in a useEffect.
 */
export function startKeepalive() {
  if (typeof window === "undefined") return () => {};
  const tick = () => { getHealth().catch(() => {}); };
  tick();                                // immediate first ping
  const id = setInterval(tick, 5 * 60 * 1000);
  return () => clearInterval(id);
}

/**
 * Leaderboard rows. Any filter can be null/undefined = don't segment on
 * that axis. When ALL are omitted the backend aggregates per-model across
 * every cell (historic "overall" view).
 *
 * Tier-S commit 2: mode (macro | joint) and arena (normal | ice |
 * low_gravity) are now first-class eval axes. Averaging across them
 * was silent dishonesty — JOINT mode is a totally different control
 * regime, ice arena is totally different physics. Backend validates
 * enum values and 400s on garbage input.
 */
export const getLeaderboard = (sharp, weapon, mode, arena, blindfolded) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  if (blindfolded != null) q.set("blindfolded", String(Boolean(blindfolded)));
  const qs = q.toString();
  return api(`/leaderboard${qs ? `?${qs}` : ""}`);
};

/**
 * Objective-skill leaderboard — Tier-S #3.
 * Rolls up proxy metrics (damage_per_turn, hit_rate, fallback_rate,
 * avg_distance) from the raw match event stream. Independent of the
 * human-vote Elo path. Same 5-axis filters as getLeaderboard.
 */
export const getLeaderboardObjective = (sharp, weapon, mode, arena, blindfolded) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  if (blindfolded != null) q.set("blindfolded", String(Boolean(blindfolded)));
  const qs = q.toString();
  return api(`/leaderboard/objective${qs ? `?${qs}` : ""}`);
};

/**
 * Bradley-Terry ratings with bootstrap confidence intervals (§5).
 * Unlike Elo this refits the whole match set at once, so it is
 * order-independent and comes with an interval per model.
 */
export const getLeaderboardBradleyTerry = (sharp, weapon, mode, arena,
                                           blindfolded, bootstraps = 200,
                                           tier = null) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  if (blindfolded != null) q.set("blindfolded", String(Boolean(blindfolded)));
  if (bootstraps != null) q.set("bootstraps", String(bootstraps));
  // §6: null = every vote; "expert"/"casual" = that tier only.
  if (tier) q.set("tier", tier);
  return api(`/leaderboard/bradley_terry?${q.toString()}`);
};

/**
 * Full per-model metric table (§5): win / preference / damage / lethality /
 * survival / timeout / invalid-action / fallback / latency.
 */
export const getModelStats = (sharp, weapon, mode, arena, blindfolded) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  if (blindfolded != null) q.set("blindfolded", String(Boolean(blindfolded)));
  const qs = q.toString();
  return api(`/model_stats${qs ? `?${qs}` : ""}`);
};

/**
 * Data-quality report for a leaderboard cell (next-step priority 2):
 * `summary.evidence_level` ∈ scripted_only | insufficient_real | real, plus
 * a per-model breakdown (real / mixed / scripted matches, fallback count,
 * missing-token count, last match, benchmark version).
 */
export const getDataQuality = (sharp, weapon, mode, arena, blindfolded) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  if (blindfolded != null) q.set("blindfolded", String(Boolean(blindfolded)));
  const qs = q.toString();
  return api(`/data_quality${qs ? `?${qs}` : ""}`);
};

/**
 * Recurring event calendar + champions archive (§31).
 * The schedule is derived server-side (no cron, no table to desync); an
 * undecided event reports *why* instead of naming a champion anyway.
 */
export const getEvents = (past = 3, future = 4) =>
  api(`/events?past=${past}&future=${future}`);

export const getEvent = (id) => api(`/events/${encodeURIComponent(id)}`);

export const getRecent = () => api("/recent");
export const getMatch = (id) => api(`/match/${id}`);
/**
 * Head-to-head record for two model ids (order-insensitive).
 * Used by the wait-screen H2H card. Returns
 * { total, a_wins, b_wins, draws, avg_turns, recent[], a_name, b_name }.
 * The card should just hide itself when total === 0 (no prior duels).
 */
export const getHeadToHead = (a, b) => {
  const q = new URLSearchParams({ a, b });
  return api(`/head_to_head?${q.toString()}`);
};
export const getReplay = (id) => api(`/replay/${id}`);
export const createMatch = (body) =>
  api("/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
/**
 * Cast a vote.
 *
 * `choice` is the TACTICAL vote — the only axis that moves a rating. The
 * optional axes (execution / entertainment / deserved) and the 1-5
 * confidence rating are collected separately so the dataset can measure
 * "fought intelligently" against "was fun to watch" instead of conflating
 * them (action-plan §6).
 */
/**
 * Cast a vote. `extra` may carry the optional axes, the 1-5 confidence
 * rating, and `voter_tier` ("casual" | "expert", §6).
 */
export const postVote = (id, choice, extra = {}) =>
  api(`/vote/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice, ...extra }),
  });

/**
 * Cancel a queued/running match (action-plan §13). The backend stops at
 * the next turn boundary — it cannot abort an API call already in flight.
 */
export const cancelMatch = (id) =>
  api(`/match/${id}/cancel`, { method: "POST" });

// ---------- Benchmark specification + integrity (§1, §8) ----------
export const getBenchmarkSpec = () => api("/benchmark/spec");
export const getIntegrity = (id) => api(`/integrity/${id}`);

// ---------- Observability (§19, §35) ----------
export const getMetrics = () => api("/metrics");
export const getStatus = () => api("/status");

/** Absolute URL for the dataset export (§27). */
export const exportUrl = (fmt = "json", params = {}) => {
  const q = new URLSearchParams({ fmt, ...params });
  return `${BASE}/api/export?${q.toString()}`;
};

/**
 * The landing-page sample fight (§3). Served as a static asset so the
 * "watch a sample fight" button works even when the backend is asleep or
 * a provider is throttled.
 */
export async function getDemoReplay() {
  const r = await fetch("/demo_replay.json");
  if (!r.ok) return null;
  return r.json();
}

// ---------- Tournaments ----------
export const createTournament = (body) =>
  api("/tournament", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getTournament = (id) => api(`/tournament/${id}`);
export const listTournaments = () => api("/tournaments");
