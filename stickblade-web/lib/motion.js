"use client";
/**
 * The entire JS side of the motion system — three small hooks, no dependency.
 *
 * The redesign originally drove micro-interactions and choreography with
 * framer-motion (~48 kB first-load). That was removed wholesale: every effect
 * is now either a CSS animation (globals.css, "MOTION UTILITIES") or one of
 * these hooks. What CSS genuinely cannot do:
 *
 *   • telling JS-side code (node-skipping, rAF loops) about the reduced-motion
 *     switch before and while the visitor flips it — `useReducedMotion`;
 *   • keeping a node mounted while its CSS leave animation plays, since React
 *     unmounting an element gives CSS nothing to animate — `useSwap`;
 *   • measuring where list items moved between two renders so they can
 *     animate from old to new position (FLIP) — `useFlipList`.
 *
 * Everything here is inert during SSR and honours the same two switches as
 * the CSS: the OS `prefers-reduced-motion` setting and the site's own
 * `data-motion="reduced"` (written by lib/prefs.js).
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { readPrefs, subscribePrefs } from "@/lib/prefs";

/**
 * True when the visitor (OS or ♿ switch) asked for reduced motion.
 *
 * Mirrors framer's `useReducedMotion()`: false during SSR/first paint so the
 * server and the hydrated tree agree, corrected in an effect. Components use
 * it to skip work (not render an ambient node, skip a rAF loop); the CSS
 * guards cover everything that does get rendered.
 */
export function useReducedMotion() {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const sync = (p) => setReduce((p || readPrefs()).motion === "reduced");
    sync();
    const unsub = subscribePrefs(sync);
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const onMq = () => sync();
    mq?.addEventListener?.("change", onMq);
    return () => { unsub(); mq?.removeEventListener?.("change", onMq); };
  }, []);
  return reduce;
}

/**
 * Leave-animated unmount. Returns `[mounted, closing]`:
 * render while `mounted`, tag the node with `data-out` while `closing`, and
 * the CSS `.swap` rule animates the node out before it disappears.
 *
 * `ms` must match the swap-out duration in globals.css (.24s) plus a frame;
 * it only ever controls how long the corpse stays mounted, never the look.
 */
export function useSwap(open, ms = 260) {
  const [mounted, setMounted] = useState(Boolean(open));
  const [closing, setClosing] = useState(false);
  const timer = useRef(null);
  useEffect(() => {
    if (open) {
      clearTimeout(timer.current);
      setMounted(true);
      setClosing(false);
      return undefined;
    }
    if (!mounted) return undefined;
    setClosing(true);
    timer.current = setTimeout(() => {
      setMounted(false);
      setClosing(false);
    }, ms);
    return () => clearTimeout(timer.current);
    // `mounted` is read to avoid starting a close for something never shown;
    // listing it would re-arm the timer on its own state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  return [mounted, closing];
}

/**
 * FLIP for keyed lists (the tournament seed rows): remember each child's box,
 * and after the DOM updates, animate children that moved from old→new with a
 * WAAPI transform. New children have no recorded box, so they simply play
 * their CSS enter animation; removed children are the reason the *other*
 * rows need to glide rather than snap.
 *
 * `key` should change whenever the list order/content changes (a joined id
 * string is enough). Children need a stable `data-flip-id`; they fall back to
 * DOM order otherwise, which defeats the point after a reorder.
 */
export function useFlipList(ref, key) {
  const prev = useRef(new Map());
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || document.documentElement?.dataset?.motion === "reduced") {
      return;
    }
    const next = new Map();
    Array.from(el.children).forEach((child, i) => {
      if (!(child instanceof HTMLElement)) return;
      const id = child.dataset?.flipId ?? String(i);
      const rect = child.getBoundingClientRect();
      next.set(id, rect);
      const before = prev.current.get(id);
      if (!before) return;
      const dx = before.left - rect.left;
      const dy = before.top - rect.top;
      if (dx || dy) {
        child.animate(
          [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
          { duration: 280, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
        );
      }
    });
    prev.current = next;
  }, [key, ref]);
}
