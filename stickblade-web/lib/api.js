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
export const getLeaderboard = (sharp) =>
  api(`/leaderboard${sharp ? `?sharp=${sharp}` : ""}`);
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
