/**
 * BYOK (bring-your-own-key) helpers.
 *
 * Users can paste their own OpenRouter key to bypass the server's free-tier
 * quota (50 req/day per model per account, which the whole app shares).
 * With BYOK enabled, their matches draw from THEIR quota, not ours.
 *
 * Storage: localStorage only. Never sent anywhere except back to our own
 * backend as the api_key field on POST /api/match. The backend does NOT
 * log, persist, or echo it back — see MatchReq.api_key in server.py.
 *
 * Format hint: OpenRouter keys look like `sk-or-v1-<48 alphanumerics>`.
 * We accept anything starting with `sk-` and ≥20 chars (also covers
 * OpenAI-compatible passthrough proxies).
 */
const KEY_LS  = "sba.byok.openrouter";
const ENABLED_LS = "sba.byok.enabled";

export function readByokKey() {
  if (typeof window === "undefined") return "";
  try { return localStorage.getItem(KEY_LS) || ""; } catch { return ""; }
}

export function writeByokKey(k) {
  if (typeof window === "undefined") return;
  try {
    if (k) localStorage.setItem(KEY_LS, k);
    else   localStorage.removeItem(KEY_LS);
  } catch {}
}

export function readByokEnabled() {
  if (typeof window === "undefined") return false;
  try { return localStorage.getItem(ENABLED_LS) === "1"; } catch { return false; }
}

export function writeByokEnabled(on) {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(ENABLED_LS, on ? "1" : "0"); } catch {}
}

export function isValidByokFormat(k) {
  return typeof k === "string" && k.trim().startsWith("sk-") && k.trim().length >= 20;
}

/**
 * Mask a key for display: sk-or-v1-ABCD...WXYZ
 * Never render the full key back to the user in DOM (paste-once-only
 * would be safer, but users need to be able to verify it saved).
 */
export function maskKey(k) {
  if (!k) return "";
  const t = k.trim();
  if (t.length <= 12) return t.slice(0, 4) + "…";
  return t.slice(0, 10) + "…" + t.slice(-4);
}
