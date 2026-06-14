// Intentionally empty.
//
// Replaces `next/dist/build/polyfills/polyfill-module` for our browserslist
// (modern evergreen browsers from 2021+). All of the features the Next
// polyfill shimmed — Array.prototype.at/flat/flatMap, Object.fromEntries,
// Object.hasOwn, String.prototype.trimStart/trimEnd, Promise.prototype.finally,
// URL.canParse, Symbol.prototype.description — have been natively supported
// for years.
//
// If you ever need to support older browsers, remove the webpack alias in
// next.config.mjs that points at this file.
export {};
