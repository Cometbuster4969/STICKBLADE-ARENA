const BASE = process.env.NEXT_PUBLIC_API_BASE;

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
export const getLeaderboard = (sharp, weapon, mode, arena) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  if (mode)   q.set("mode",   mode);
  if (arena)  q.set("arena",  arena);
  const qs = q.toString();
  return api(`/leaderboard${qs ? `?${qs}` : ""}`);
};

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
export const postVote = (id, choice) =>
  api(`/vote/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice }),
  });

// ---------- Tournaments ----------
export const createTournament = (body) =>
  api("/tournament", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getTournament = (id) => api(`/tournament/${id}`);
export const listTournaments = () => api("/tournaments");
