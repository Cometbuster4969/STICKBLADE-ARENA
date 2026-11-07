import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Vitest config for the arena frontend.
 *
 * Three things here are load-bearing and non-obvious:
 *
 * 1. `oxc: { lang: "jsx" }` — THE one that matters. Every component in this
 *    app is a plain `.js` file containing JSX (Next compiles it with SWC,
 *    which infers the loader from content, not from the extension). Vite 8
 *    infers its parser language from the file extension alone
 *    (`.js` → `js`, JSX syntax off), so without this override every test
 *    dies with `PARSE_ERROR: Unexpected JSX expression` on the first `<div>`
 *    — even though `@vitejs/plugin-react` is installed and configured.
 *
 * 2. `include: /\.jsx?$/` on the React plugin — same root cause, opposite
 *    direction: plugin-react's default include filters (\.jsx? and \.tsx)
 *    would otherwise skip `.js` and never apply the automatic JSX runtime.
 *
 * 3. The `@/` alias, mirroring `jsconfig.json` — components import
 *    `@/lib/prefs`, and Node cannot resolve that on its own.
 */
const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react({ include: /\.jsx?$/ })],
  resolve: { alias: { "@": root } },
  // See note 1 above. Scoped to .js/.jsx: dependency code is plain JS and
  // parses fine as-is, but re-parsing it as JSX is harmless, and leaving it
  // unset is what breaks the app's own components.
  oxc: { lang: "jsx" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.js"],
    include: ["tests/**/*.test.{js,jsx}"],
  },
});
