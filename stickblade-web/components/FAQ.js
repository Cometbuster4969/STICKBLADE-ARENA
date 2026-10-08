"use client";
import { useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { MotionSection } from "@/components/MotionSection";

/**
 * FAQ block — 6 real questions from friend-feedback + likely reviewer
 * concerns. Placed at the bottom of the fight page, below the leaderboard,
 * so first-timers scrolling past the vote can find quick answers.
 *
 * Motion redesign: each item is still a native <details>/<summary>, so the
 * accordion keeps its zero-JS keyboard + screen-reader semantics; framer-motion
 * only animates the height/opacity of the answer body (and is skipped entirely
 * under reduced motion). Items stagger in as the section scrolls into view.
 */
const ITEMS = [
  {
    q: "Wait, what am I actually looking at?",
    a: <>Two language models controlling stickmen in a 2D physics arena.
        Every 3 seconds of simulated combat, each model gets its state
        (HP, position, opponent's last move, weapon geometry) and picks
        an action via a real API call. They fight until one dies or 24
        turns pass. You watch, vote blind on who fought smarter, and
        per-model Elo tracks it over time. It's an evaluation experiment
        for LLM behavior under physical constraints, not a game with
        pre-scripted characters.</>,
  },
  {
    q: "Why does it take a full minute?",
    a: <>Each turn is a real LLM API call for each fighter — that's
        ~5–15 seconds of actual model inference per turn, plus 3
        seconds of physics simulation. Reasoning-heavy models
        (gpt-oss-120b, deepseek-r1) take longer than chat-tuned ones.
        A typical match is 60–90 seconds; matches with reasoning models
        can go 2–3 minutes. If it were faster, the models wouldn't be
        thinking — they'd be reflex-responding, which defeats the point.</>,
  },
  {
    q: "Is this a game?",
    a: <>No. There's no controllable character, no progression, no XP,
        no player skill involved. It's closer to Chatbot Arena
        (LMSys) — a human-in-the-loop benchmark for comparing language
        models. Chatbot Arena rates them on text output; this rates them
        on decision-making under adversarial physical constraints.
        The stickman visuals exist because you need to SEE the physics
        to judge the decision, not because it's meant to be entertainment.</>,
  },
  {
    q: "Why don't I see which model is which until I vote?",
    a: <>Brand anchoring is a real bias in eval. If you knew "green is
        GPT-4o" before voting, you'd rate its moves more charitably.
        Blind voting means you rate the fighting behavior on its own
        merits. Reveal happens after your vote lands, along with the
        Elo change and (if you predicted) whether your prediction was
        right. This mirrors how Chatbot Arena, human-preference RLHF
        datasets, and most serious human-eval methodologies work.</>,
  },
  {
    q: "How does the Elo rating work? What's a 'provisional' rating?",
    a: <>Standard Elo with K=32, starting rating 1000. Ratings segment
        per <em>(model, sharp zone, weapon, control mode, arena)</em> so
        a model that dominates macro-mode swordplay isn't credited for
        arenas it never fought in. Rows with fewer than 10 recorded
        matches are marked <b style={{ color: "var(--gold)" }}>?</b>{" "}
        (provisional) because K=32 can swing a rating ±80 points from
        a couple of lucky matchups — pretending those small-N cells
        are stable would be misleading. The Win% column shows the 95%
        Wilson confidence interval on the underlying win-rate.</>,
  },
  {
    q: "Can I add my own model? Bring my own API key?",
    a: <>Yes. In the setup panel above the "Fight" button, there's a
        BYOK (bring-your-own-key) toggle. Paste any valid OpenRouter
        key and specify any model ID they route to — the backend will
        use your key for that one match only, then discard it (never
        logged, never persisted). Costs come out of your account, not
        the free pool. This is also useful if the free tier is rate-
        limited during high traffic.</>,
  },
];

export default function FAQ() {
  return (
    <MotionSection>
      <section style={{
        width: "100%", maxWidth: 760, margin: "40px auto 20px",
        padding: "0 4px",
      }}>
        <h2 style={{
          fontSize: 22, letterSpacing: 1, textTransform: "uppercase",
          color: "var(--text)", fontWeight: 700, marginBottom: 6, textAlign: "center",
          fontFamily: "var(--font-display), 'Rajdhani', system-ui, sans-serif",
        }}>
          Frequently asked
        </h2>
        <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 20, textAlign: "center" }}>
          Real questions from real users. If yours isn't here,{" "}
          <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA/issues"
             target="_blank" rel="noreferrer"
             style={{ color: "var(--gold)", textDecoration: "underline",
                      textDecorationStyle: "dotted" }}>
            open an issue on GitHub
          </a>.
        </p>

        {ITEMS.map((it, i) => (
          <FaqItem key={it.q} q={it.q} index={i}>{it.a}</FaqItem>
        ))}
      </section>
    </MotionSection>
  );
}

/**
 * Single collapsible item. Native <details> drives open/close (keyboard,
 * screen readers, and URL-fragment targeting all keep working); the answer
 * body animates its height on top of that.
 */
function FaqItem({ q, children, index = 0 }) {
  const [open, setOpen] = useState(false);
  const bodyRef = useRef(null);
  const reduce = useReducedMotion();

  return (
    /* The <details> itself is a plain element: a reveal that ships inline
       opacity:0 would make an accordion question unreadable — and
       unopenable — until JS runs. The answer body below is fine to animate,
       because it only exists after a client-side open. */
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      data-reveal="up"
      style={{
        marginBottom: 8,
        border: `1px solid ${open ? "var(--line-strong)" : "var(--line)"}`,
        borderRadius: 12,
        background: open ? "rgba(255,255,255,0.035)" : "rgba(255,255,255,0.02)",
        overflow: "hidden",
        transition: "background 0.3s var(--ease-smooth), border-color 0.3s var(--ease-smooth)",
        "--r-in": `${index * 20}px`,
      }}
    >
      <summary style={{
        cursor: "pointer", color: "var(--text)",
        fontWeight: 600, fontSize: 14.5, letterSpacing: 0.2,
        listStyle: "none", display: "flex", alignItems: "center",
        justifyContent: "space-between", gap: 12,
        padding: "12px 14px",
      }}>
        <span>{q}</span>
        <motion.span
          aria-hidden="true"
          animate={{ rotate: open ? 45 : 0, color: open ? "var(--red)" : "var(--dim)" }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontSize: 18, lineHeight: 1, flexShrink: 0 }}
        >
          +
        </motion.span>
      </summary>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            ref={bodyRef}
            key="body"
            initial={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            animate={reduce ? { opacity: 1 } : { height: "auto", opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div style={{
              padding: "0 14px 14px",
              color: "var(--text-2)", lineHeight: 1.65,
              fontSize: 13.5,
            }}>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </details>
  );
}
