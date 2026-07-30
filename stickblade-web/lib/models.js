/**
 * Model display-name helper.
 *
 * The backend already resolves ids to friendly names in most responses
 * (`/api/models` returns `{id, name}`, `/api/leaderboard` rows carry
 * `r.name`, `/api/recent` and `/api/vote` bake names in server-side).
 * This module is the LAST-LINE fallback for any place we accidentally
 * render a raw id — e.g. a custom user-typed OpenRouter model that
 * isn't in ARENA_MODELS. Prefer server-provided names when available;
 * only reach for `displayName(id)` when you don't have one.
 *
 * Map is kept in sync with stickblade/config.py's ARENA_MODELS.
 * When adding a new model to the backend, also add it here.
 */
export const DISPLAY_NAMES = {
  // OpenRouter :free tier — every slug live-probed 2026-07-28.
  // Kept in sync with backend config.py ARENA_MODELS. When OpenRouter
  // rotates a slug off :free (they do this every few weeks on flagship
  // models), REMOVE the entry here + in config.py rather than leave it
  // as a dead link — every 404'd request costs users ~20s of retry-
  // ladder time before falling to a buddy model.
  // OpenAI
  "openai/gpt-oss-20b:free":                      "GPT-OSS 20B",
  "openai/gpt-4o-mini":                           "GPT-4o mini",
  // Google
  "google/gemma-4-31b-it:free":                   "Gemma 4 31B",
  "google/gemma-4-26b-a4b-it:free":               "Gemma 4 26B A4B",
  // NVIDIA
  "nvidia/nemotron-3-super-120b-a12b:free":       "Nemotron 3 Super 120B",
  "nvidia/nemotron-3-ultra-550b-a55b:free":       "Nemotron 3 Ultra 550B",
  "nvidia/nemotron-3-nano-30b-a3b:free":          "Nemotron 3 Nano 30B",
  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": "Nemotron 3 Nano Omni Reasoning",
  "nvidia/nemotron-nano-9b-v2:free":              "Nemotron Nano 9B",
  // Others
  "cohere/north-mini-code:free":                  "Cohere North Mini Code",
  "poolside/laguna-xs-2.1:free":                  "Poolside Laguna XS 2.1",
  "openrouter/free":                              "OpenRouter Auto-Router",
  // No-API mocks
  "mock:duelist":                                 "Mock Duelist (no API)",
  "mock:berserker":                               "Mock Berserker (no API)",
  "bot:random":                                   "🎲 Random Bot (baseline)",
  "bot:greedy":                                   "⚡ Greedy Attacker (baseline)",
  "bot:distance":                                 "📏 Distance Bot (baseline)",
  "bot:pro":                                      "🏆 Scripted Pro (baseline)",
};

/**
 * Best-effort display name for a model id. Returns the id itself if
 * we don't recognize it — that's fine for BYOK / custom-typed ids
 * where the user knows what they entered anyway.
 */
export function displayName(id) {
  if (!id) return "";
  return DISPLAY_NAMES[id] || id;
}
