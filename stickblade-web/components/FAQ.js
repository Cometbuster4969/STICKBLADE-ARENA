"use client";

/**
 * FAQ block — 6 real questions from friend-feedback + likely reviewer
 * concerns. Placed at the bottom of the fight page, below the leaderboard,
 * so first-timers scrolling past the vote can find quick answers without
 * needing a dedicated /about page (yet).
 *
 * All items collapsed by default. Cheap `<details>` — no state, no JS
 * beyond the browser's native accordion behavior. Renders <20 lines of
 * DOM per item so scroll performance stays clean even on mobile.
 *
 * Copy discipline: "not a game" framing throughout; second-person voice
 * ("you", "your"); short concrete answers. No marketing fluff.
 */
export default function FAQ() {
  return (
    <section style={{
      width: "100%", maxWidth: 760, margin: "40px auto 20px",
      padding: "0 4px",
    }}>
      <h2 style={{
        fontSize: 18, letterSpacing: 2, textTransform: "uppercase",
        color: "var(--text)", fontWeight: 700, marginBottom: 4,
        fontFamily: "var(--font-display), 'Rajdhani', system-ui, sans-serif",
      }}>
        Frequently asked
      </h2>
      <p style={{ color: "var(--dim)", fontSize: 13, marginBottom: 16 }}>
        Real questions from real users. If yours isn't here,{" "}
        <a href="https://github.com/Cometbuster4969/STICKBLADE-ARENA/issues"
           target="_blank" rel="noreferrer"
           style={{ color: "var(--gold)", textDecoration: "underline",
                    textDecorationStyle: "dotted" }}>
          open an issue on GitHub
        </a>.
      </p>

      <FaqItem q="Wait, what am I actually looking at?">
        Two language models controlling stickmen in a 2D physics arena.
        Every 3 seconds of simulated combat, each model gets its state
        (HP, position, opponent's last move, weapon geometry) and picks
        an action via a real API call. They fight until one dies or 24
        turns pass. You watch, vote blind on who fought smarter, and
        per-model Elo tracks it over time. It's an evaluation experiment
        for LLM behavior under physical constraints, not a game with
        pre-scripted characters.
      </FaqItem>

      <FaqItem q="Why does it take a full minute?">
        Each turn is a real LLM API call for each fighter — that's
        ~5–15 seconds of actual model inference per turn, plus 3
        seconds of physics simulation. Reasoning-heavy models
        (gpt-oss-120b, deepseek-r1) take longer than chat-tuned ones.
        A typical match is 60–90 seconds; matches with reasoning models
        can go 2–3 minutes. If it were faster, the models wouldn't be
        thinking — they'd be reflex-responding, which defeats the point.
      </FaqItem>

      <FaqItem q="Is this a game?">
        No. There's no controllable character, no progression, no XP,
        no player skill involved. It's closer to Chatbot Arena
        (LMSys) — a human-in-the-loop benchmark for comparing language
        models. Chatbot Arena rates them on text output; this rates them
        on decision-making under adversarial physical constraints.
        The stickman visuals exist because you need to SEE the physics
        to judge the decision, not because it's meant to be entertainment.
      </FaqItem>

      <FaqItem q="Why don't I see which model is which until I vote?">
        Brand anchoring is a real bias in eval. If you knew "green is
        GPT-4o" before voting, you'd rate its moves more charitably.
        Blind voting means you rate the fighting behavior on its own
        merits. Reveal happens after your vote lands, along with the
        Elo change and (if you predicted) whether your prediction was
        right. This mirrors how Chatbot Arena, human-preference RLHF
        datasets, and most serious human-eval methodologies work.
      </FaqItem>

      <FaqItem q="How does the Elo rating work? What's a 'provisional' rating?">
        Standard Elo with K=32, starting rating 1000. Ratings segment
        per <em>(model, sharp zone, weapon, control mode, arena)</em> so
        a model that dominates macro-mode swordplay isn't credited for
        arenas it never fought in. Rows with fewer than 10 recorded
        matches are marked <b style={{ color: "var(--gold)" }}>?</b>{" "}
        (provisional) because K=32 can swing a rating ±80 points from
        a couple of lucky matchups — pretending those small-N cells
        are stable would be misleading. The Win% column shows the 95%
        Wilson confidence interval on the underlying win-rate.
      </FaqItem>

      <FaqItem q="Can I add my own model? Bring my own API key?">
        Yes. In the setup panel above the "Fight" button, there's a
        BYOK (bring-your-own-key) toggle. Paste any valid OpenRouter
        key and specify any model ID they route to — the backend will
        use your key for that one match only, then discard it (never
        logged, never persisted). Costs come out of your account, not
        the free pool. This is also useful if the free tier is rate-
        limited during high traffic.
      </FaqItem>
    </section>
  );
}

/**
 * Single collapsible FAQ item. Uses `<details>` for native accordion
 * behavior — no JS state, no click handlers, works with keyboard and
 * screen readers out of the box.
 */
function FaqItem({ q, children }) {
  return (
    <details style={{
      marginBottom: 8, padding: "12px 14px",
      border: "1px solid var(--line)", borderRadius: 6,
      background: "rgba(255,255,255,0.02)",
    }}>
      <summary style={{
        cursor: "pointer", color: "var(--text)",
        fontWeight: 600, fontSize: 14.5, letterSpacing: 0.2,
        listStyle: "none",
      }}>
        {q}
      </summary>
      <div style={{
        marginTop: 10, color: "var(--text-2)", lineHeight: 1.6,
        fontSize: 13.5,
      }}>
        {children}
      </div>
    </details>
  );
}
