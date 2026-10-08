"use client";
import { useEffect, useRef, useState } from "react";
import {
  motion, useScroll, useTransform, useReducedMotion,
} from "framer-motion";

/* ---------------------------------------------------------------------------
   Motion primitives — one vocabulary for the whole site.

   SPLIT BY PURPOSE, ON PURPOSE:

   • Scroll reveals are CSS (`data-reveal`, globals.css), not framer-motion.
     An observer-driven reveal has to ship the hidden state from the server and
     only release it after hydration + IO fires, which costs a non-JS reader and
     a text-extracting crawler the entire page, and puts LCP behind JS timing.
     `animation-timeline: view()` gives the identical effect with the visible
     state as the default, so no support = plain visible content.

   • framer-motion keeps the jobs CSS genuinely cannot do: scroll-linked
     values (the reading rail, the hero drift), layout transitions (reordering
     tournament seeds, the nav indicator), mount/unmount choreography
     (AnimatePresence), and spring physics on pointer interaction.

   Both halves honour reduced motion twice over: the CSS behind
   `prefers-reduced-motion` + the site's own data-motion switch, and
   `useReducedMotion()` here so JS-side listeners are never even attached.
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

/* Scroll-linked parallax offset. Real scroll math, so this one is JS. */
export function Parallax({ children, speed = 0.15, className = "" }) {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [120 * speed, -120 * speed]);
  return (
    <motion.div ref={ref} className={className} style={reduce ? undefined : { y }}>
      {children}
    </motion.div>
  );
}

/**
 * Scroll-linked hero motion: the hero drifts up, scales down slightly and
 * fades as the setup section takes over.
 *
 * `useScroll({ target })` is measured against the element itself, so no global
 * scroll listener is added. Starts at full opacity and only ever reduces from
 * there, which is why this is safe to render server-side — unlike a reveal, the
 * unhydrated page still shows the hero.
 */
export function HeroScrollFade({ children, className = "", distance = 90 }) {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, -distance]);
  const opacity = useTransform(scrollYProgress, [0, 0.85], [1, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [1, 0.94]);

  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ y, opacity, scale, transformOrigin: "50% 30%", willChange: "transform" }}
    >
      {children}
    </motion.div>
  );
}

export default MotionSection;
