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
 * Leaderboard rows. Either filter is optional; pass both for the most
 * specific board (per-sharp-zone within a single weapon).
 */
export const getLeaderboard = (sharp, weapon) => {
  const q = new URLSearchParams();
  if (sharp)  q.set("sharp",  sharp);
  if (weapon) q.set("weapon", weapon);
  const qs = q.toString();
  return api(`/leaderboard${qs ? `?${qs}` : ""}`);
};

export const getRecent = () => api("/recent");
export const getMatch = (id) => api(`/match/${id}`);
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
