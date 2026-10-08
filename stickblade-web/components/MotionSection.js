"use client";
import { useEffect, useState } from "react";
import { useReducedMotion } from "@/lib/motion";

/* ---------------------------------------------------------------------------
   Motion primitives — one vocabulary for the whole site.

   Everything here renders plain elements carrying data-attributes or a CSS
   class; the animation itself lives in globals.css ("MOTION UTILITIES" and
   the scroll-reveal block). That is deliberate:

   • Reveals must not be observer-driven. An IO/framer reveal ships markup
     with inline opacity:0 from the server and only un-hides it after
     hydration — blank for no-JS readers and crawlers, LCP hostage to JS
     timing. `animation-timeline: view()` gives the identical effect with the
     visible state as the default; no support = plain visible content.
   • Press feedback, loops, entrances, swaps, collapses, the reading rail and
     the hero scroll-fade all became CSS the day framer-motion was dropped
     (~48 kB first-load saved). The only JS left on the motion budget is in
     lib/motion.js: reduced-motion awareness, swap-out unmount timing, and a
     FLIP for the tournament seed list.

   Both halves honour reduced motion twice over: the CSS behind
   `prefers-reduced-motion` + the site's own data-motion switch, and
   useReducedMotion() here so ambient nodes are never even attached.
--------------------------------------------------------------------------- */

/* Reveal a block as it crosses the fold. */
export function MotionSection({
  children, className = "", delay = 0, as = "div", direction = "up",
  style, ref, ...props
}) {
  const Comp = as;
  return (
    <Comp
      ref={ref}
      data-reveal={direction}
      style={{ ...style, ...(delay ? { "--r-in": `${Math.round(delay * 340)}px` } : null) }}
      className={className}
      {...props}
    >
      {children}
    </Comp>
  );
}

/**
 * Parent of a sequence of items; children stagger via range offsets.
 *
 * `staggerDelay` is kept in seconds for call-site compatibility, but it does
 * not become a timer — it sets `--r-step`, the scroll distance between one
 * sibling's reveal and the next. That is the honest translation for a
 * scroll-driven animation: the gap stays the same *spatial* distance whether
 * you scroll quickly or slowly, which is what makes a stagger feel deliberate
 * instead of laggy.
 */
export function StaggerContainer({
  children, className = "", as = "div", reveal = false, direction = "up",
  staggerDelay = 0.08, style, ...props
}) {
  const Comp = as;
  return (
    <Comp
      className={className}
      data-reveal-stagger=""
      {...(reveal ? { "data-reveal": direction } : null)}
      style={{ ...style, "--r-step": `${Math.round(staggerDelay * 450)}px` }}
      {...props}
    >
      {children}
    </Comp>
  );
}

/* One staggered child. The parent drives timing; this only opts in. */
export function StaggerItem({ children, className = "", as = "div", direction = "up", ...props }) {
  const Comp = as;
  return (
    <Comp className={className} data-reveal={direction} {...props}>
      {children}
    </Comp>
  );
}

/* Card that reveals on scroll and lifts on hover — the lift is a CSS
   transition so it survives without view() support. */
export function MotionCard({ children, className = "", delay = 0, hover = true, style, ...props }) {
  return (
    <div
      data-reveal="scale"
      data-lift={hover ? "" : undefined}
      className={className}
      style={{ ...style, ...(delay ? { "--r-in": `${Math.round(delay * 340)}px` } : null) }}
      {...props}
    >
      {children}
    </div>
  );
}

/* Directional slide-in. */
export function SlideIn({ children, direction = "left", className = "", delay = 0, ...props }) {
  return (
    <MotionSection as="div" direction={direction} delay={delay} className={className} {...props}>
      {children}
    </MotionSection>
  );
}

/* Hero entrance — time-based, plays on load, no scroll timeline and no JS
   needed, so above-the-fold copy is never waiting on hydration. */
export function HeroAnimation({ children, className = "", delay = 0, style, ...props }) {
  return (
    <div
      data-hero-in=""
      className={className}
      style={{ ...style, "--hero-delay": `${delay}s` }}
      {...props}
    >
      {children}
    </div>
  );
}

/* Ambient glow orb. Decorative, blurred, and removed entirely when the
   visitor turns effects off — the animation is a CSS transform loop rather
   than a JS one, so it costs no main-thread time. */
export function FloatingOrb({
  size = 300, color = "rgba(255, 51, 85, 0.06)", top, left, right, bottom,
}) {
  const reduce = useReducedMotion();
  const fxOff = useEffectsOff();
  if (reduce || fxOff) return null;
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        width: size, height: size, borderRadius: "50%",
        background: `radial-gradient(circle, ${color}, transparent 70%)`,
        filter: "blur(60px)", pointerEvents: "none",
        top, left, right, bottom, zIndex: 0,
        animation: "orb-drift 14s ease-in-out infinite",
      }}
    />
  );
}

/* data-fx="off" is written by lib/prefs.js; honouring it here means the
   "No effects" switch removes these ambient layers, not just the canvas FX.
   Read after mount (the attribute does not exist during SSR) and re-read on
   every toggle, so the orbs disappear the instant the switch flips. */
function useEffectsOff() {
  const [off, setOff] = useState(false);
  useEffect(() => {
    const read = () => setOff(document.documentElement?.dataset?.fx === "off");
    read();
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-fx"] });
    return () => obs.disconnect();
  }, []);
  return off;
}

/* Scroll-linked parallax offset — CSS `animation-timeline: view()` with the
   shift distance passed through --px (same mapping the framer version used:
   ±120px × speed across the element's cover range). The class is inert where
   the timeline is unsupported or motion is reduced, so nothing to gate in JS. */
export function Parallax({ children, speed = 0.15, className = "" }) {
  return (
    <div className={`parallax ${className}`.trim()} style={{ "--px": `${Math.round(120 * speed)}px` }}>
      {children}
    </div>
  );
}

/**
 * Scroll-linked hero motion: the hero drifts up, scales down slightly and
 * fades as the setup section takes over — `hero-out` on a `scroll(root)`
 * timeline in globals.css (0 → 65vh of page scroll).
 *
 * Safe to render server-side: like the reveals, the *default* style is the
 * final state, and the animation only expresses the leaving phase. The
 * unhydrated page still shows the hero.
 */
export function HeroScrollFade({ children, className = "" }) {
  return <div className={`hero-scroll-fade ${className}`.trim()}>{children}</div>;
}

export default MotionSection;
