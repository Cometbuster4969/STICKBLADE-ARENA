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
  // Meta
  "meta-llama/llama-3.3-70b-instruct:free":       "Llama 3.3 70B (free)",
  "meta-llama/llama-3.2-3b-instruct:free":        "Llama 3.2 3B (free)",
  // Qwen
  "qwen/qwen3-next-80b-a3b-instruct:free":        "Qwen3 Next 80B (free)",
  "qwen/qwen3-coder:free":                        "Qwen3 Coder 480B (free)",
  // OpenAI (gpt-oss + paid mini)
  "openai/gpt-oss-120b:free":                     "GPT-OSS 120B (free)",
  "openai/gpt-oss-20b:free":                      "GPT-OSS 20B (free)",
  "openai/gpt-4o-mini":                           "GPT-4o mini",
  // Google
  "google/gemma-4-31b-it:free":                   "Gemma 4 31B (free)",
  "google/gemma-4-26b-a4b-it:free":               "Gemma 4 26B A4B (free)",
  // Nous
  "nousresearch/hermes-3-llama-3.1-405b:free":    "Hermes 3 405B (free)",
  // NVIDIA
  "nvidia/nemotron-3-super-120b-a12b:free":       "Nemotron 3 Super 120B (free)",
  "nvidia/nemotron-3-ultra-550b-a55b:free":       "Nemotron 3 Ultra 550B (free)",
  "nvidia/nemotron-3-nano-30b-a3b:free":          "Nemotron 3 Nano 30B (free)",
  "nvidia/nemotron-nano-9b-v2:free":              "Nemotron Nano 9B (free)",
  // Others
  "poolside/laguna-m.1:free":                     "Poolside Laguna M.1 (free)",
  "poolside/laguna-xs.2:free":                    "Poolside Laguna XS.2 (free)",
  "cohere/north-mini-code:free":                  "Cohere North Mini Code (free)",
  "cognitivecomputations/dolphin-mistral-24b-venice-edition:free": "Dolphin Venice 24B (free)",
  "liquid/lfm-2.5-1.2b-instruct:free":            "LiquidAI LFM2.5 1.2B (free)",
  // No-API mocks
  "mock:duelist":                                 "Mock Duelist (no API)",
  "mock:berserker":                               "Mock Berserker (no API)",
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
