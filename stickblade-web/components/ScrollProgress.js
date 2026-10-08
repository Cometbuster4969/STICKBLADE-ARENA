"use client";
/**
 * Top-of-page scroll progress rail.
 *
 * Purely decorative motion feedback: it scales with scroll position so the
 * reader always knows how far into a long page they are. Height stays 2px and
 * it is aria-hidden, so it never competes with content or a screen reader.
 */
import { motion, useScroll, useSpring, useReducedMotion } from "framer-motion";

export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const reduce = useReducedMotion();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 120, damping: 26, restDelta: 0.001,
  });

  return (
    <motion.div
      aria-hidden="true"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: "2px",
        background: "linear-gradient(90deg, var(--red), var(--gold))",
        transformOrigin: "0%",
        scaleX: reduce ? 1 : scaleX,
        zIndex: 200,
        pointerEvents: "none",
      }}
    />
  );
}
