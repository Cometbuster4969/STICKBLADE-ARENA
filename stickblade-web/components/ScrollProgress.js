/**
 * Top-of-page scroll progress rail.
 *
 * Purely decorative motion feedback: it scales with scroll position so the
 * reader always knows how far into a long page they are. Height stays 2px and
 * it is aria-hidden, so it never competes with content or a screen reader.
 *
 * The whole component is one class: `rail-progress` on a `scroll(root)`
 * timeline in globals.css (linear, so the rail is the page position itself —
 * the old spring was smoothing the input, not the meaning). Browsers without
 * scroll timelines, and visitors with reduced motion, simply get no rail;
 * `@supports` + the reduced guards skip the transform entirely.
 */
export default function ScrollProgress() {
  return <div aria-hidden="true" className="scroll-rail" />;
}
