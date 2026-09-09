/**
 * Headless smoke test for the replay player, including the §10 research
 * debug overlay (`public/player.js`).
 *
 * Why this exists: the player is a vanilla `<script>` that binds to fixed
 * DOM ids, so the Next build never executes it — a typo in a draw call
 * would only surface as a blank arena in a real browser. And the debug
 * overlay exercises code paths (per-body hitboxes, blade geometry, event
 * playback) that the normal renderer never touches, so an exception there
 * would take down the whole replay for the user.
 *
 * It stubs just enough DOM to run `initPlayer()` against the checked-in
 * demo replay, turns the overlay on, drives a few frames, and asserts the
 * draw-call mix looks like a real frame. No browser, no deps:
 *
 *     node stickblade-web/scripts/check-player.mjs
 */
import fs from "node:fs";
import vm from "node:vm";

import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(HERE, "..");

const replay = JSON.parse(
  fs.readFileSync(path.join(WEB, "public/demo_replay.json"), "utf8"));

const calls = [];
function makeCtx() {
  const noop = () => {};
  const rec = (name) => (...a) => { calls.push(name); return undefined; };
  return {
    canvas: { width: 1280, height: 720 },
    setTransform: noop, drawImage: noop, save: noop, restore: noop,
    beginPath: noop, moveTo: rec("moveTo"), lineTo: rec("lineTo"),
    arc: rec("arc"), stroke: rec("stroke"), fill: rec("fill"),
    fillRect: rec("fillRect"), strokeRect: noop, fillText: rec("fillText"),
    measureText: () => ({ width: 40 }), createLinearGradient: () => ({ addColorStop: noop }),
    roundRect: noop, rect: noop, closePath: noop, clip: noop, translate: noop,
    scale: noop, rotate: noop, quadraticCurveTo: noop, bezierCurveTo: noop,
    ellipse: noop, setLineDash: noop, createRadialGradient: () => ({ addColorStop: noop }),
    fillStyle: "", strokeStyle: "", lineWidth: 1, font: "", textAlign: "",
    globalAlpha: 1, lineCap: "", globalCompositeOperation: "", shadowBlur: 0,
    shadowColor: "", lineJoin: "",
  };
}
function el(id) {
  return {
    id, value: "1", textContent: "", style: {}, tagName: "DIV",
    clientWidth: 1280, clientHeight: 720, width: 1280, height: 720,
    classList: { add: () => {}, remove: () => {}, toggle: () => {} },
    getContext: () => makeCtx(),
    addEventListener: () => {}, removeEventListener: () => {},
    setAttribute: () => {}, getAttribute: () => null,
    appendChild: () => {}, focus: () => {}, click: () => {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1280, height: 720 }),
    max: "100", min: "0", step: "1", checked: false,
  };
}
const els = {};
const document = {
  getElementById: (id) => (els[id] ||= el(id)),
  createElement: (t) => el(t),
  addEventListener: () => {}, removeEventListener: () => {},
  head: { appendChild: () => {} }, body: { appendChild: () => {} },
};
let rafCount = 0;
const sandbox = {
  document, console,
  window: { devicePixelRatio: 1, addEventListener: () => {}, removeEventListener: () => {},
            matchMedia: () => ({ matches: false, addEventListener: () => {} }) },
  requestAnimationFrame: (fn) => { if (rafCount++ < 3) setTimeout(() => fn(rafCount * 16), 0); return rafCount; },
  cancelAnimationFrame: () => {},
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
  AudioContext: undefined, webkitAudioContext: undefined,
  Image: function () { return { onload: null, src: "" }; },
  performance: { now: () => 0 },
  Math, Date, JSON, Number, String, Array, Object, Set, Map, isNaN, parseFloat, parseInt,
};
sandbox.window.document = document;
sandbox.globalThis = sandbox;
const code = fs.readFileSync(path.join(WEB, "public/player.js"), "utf8");
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: "player.js" });
const api = vm.runInContext("initPlayer", sandbox)(replay);
console.log("initPlayer ok:", !!api, "isAlive:", api.isAlive && api.isAlive());
// Toggle the §10 overlay and drive several frames through it.
sandbox.window.__sbDebugToggle();
console.log("debug on:", sandbox.window.__sbDebug.on);
api.play && api.play();
setTimeout(() => {
  console.log("draw calls recorded:", calls.length);
  const kinds = {};
  for (const c of calls) kinds[c] = (kinds[c] || 0) + 1;
  console.log("primitive mix:", kinds);
  console.log("isAlive after frames:", api.isAlive && api.isAlive());
  if (calls.length < 100) { console.error("FAIL: too few draw calls"); process.exit(1); }
  console.log("PASS");
}, 200);
