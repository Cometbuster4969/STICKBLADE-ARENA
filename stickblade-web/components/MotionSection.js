"use client";

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
   • Press feedback, loops, entrances, swaps, collapses and the reading rail
     all became CSS the day framer-motion was dropped (~48 kB first-load
     saved). The only JS left on the motion budget is in lib/motion.js:
     reduced-motion awareness, swap-out unmount timing, and a FLIP for the
     tournament seed list.
   • The "kinematics plate" pass made reveals OPT-IN per section: sections no
     longer announce themselves on scroll by default (fade-up-per-section is
     the most recycled pattern in generated frontends). Pages read calm;
     motion answers input.

   All of it honours reduced motion at the layer that owns it: the CSS behind
   `prefers-reduced-motion` + the site's own data-motion switch. Nothing here
   needs JS to stand down — the inert state is the default state.
--------------------------------------------------------------------------- */

/* Reveal a block as it crosses the fold — opt-in: pass `direction` to get
   the animation, leave it off and the section is simply there (which is what
   most sections on most pages do now). */
export function MotionSection({
  children, className = "", delay = 0, as = "div", direction = null,
  style, ref, ...props
}) {
  const Comp = as;
  return (
    <Comp
      ref={ref}
      {...(direction ? { "data-reveal": direction } : null)}
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

/* One staggered child. The parent drives timing; this opts in — pass
   direction={null} to park an item without any reveal. */
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


export default MotionSection;
