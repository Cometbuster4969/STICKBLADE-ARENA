"use client";
import { useEffect, useState } from "react";

/**
 * Shareable matches (action-plan §30).
 *
 * Every finished match should be one click from a link that explains
 * itself: winner, weapon, arena, sharp zone and the two model names after
 * reveal. Plus a copyable embed for forum/blog posts.
 */
const SITE = "https://stickblade-arena.vercel.app";

function buildShareText(result, replay) {
  const meta = replay?.meta || {};
  const names = result?.names || {};
  const a = names[result?.canvas_a_model] || result?.canvas_a_model || "?";
  const b = names[result?.canvas_b_model] || result?.canvas_b_model || "?";
  const winner = result?.engine_winner_side === "draw"
    ? "Draw"
    : (result?.engine_winner_side === "a" ? a : b);
  return [
    `${a} vs ${b}`,
    `${(meta.weapon || "sword").toUpperCase()} duel on ${(meta.arena || "normal").replace("_", " ")}`,
    `sharp: ${(meta.sharp || []).join("+") || "—"}`,
    `winner: ${winner}`,
  ].join(" · ");
}

export default function ShareBar({ matchId, result, replay }) {
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState("");
  const [showEmbed, setShowEmbed] = useState(false);

  useEffect(() => {
    if (!matchId) return;
    setUrl(`${SITE}/replay?id=${matchId}`);
  }, [matchId]);

  async function copy(text, what) {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        window.prompt("Copy this:", text);
      }
      setCopied(what);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      window.prompt("Copy this:", text);
    }
  }

  if (!matchId) return null;
  const text = buildShareText(result, replay);
  const embed = `<iframe src="${SITE}/replay?id=${matchId}&embed=1" `
    + `width="960" height="600" loading="lazy" title="Stickblade Arena match"`
    + ` style="border:1px solid #262a3f;border-radius:12px"></iframe>`;

  const btn = {
    padding: "6px 10px", fontSize: 12, borderRadius: 6, cursor: "pointer",
    border: "1px solid var(--line)", background: "transparent",
    color: "var(--text)", whiteSpace: "nowrap", minHeight: 34,
  };

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                  alignItems: "center" }}>
      <button style={btn} onClick={() => copy(url, "link")}
              aria-label="Copy link to this match">
        {copied === "link" ? "✓ Copied!" : "🔗 Copy link"}
      </button>
      <button style={btn} onClick={() => copy(text + " " + url, "text")}
              aria-label="Copy a one-line summary">
        {copied === "text" ? "✓ Copied!" : "📝 Copy summary"}
      </button>
      <a style={{ ...btn, textDecoration: "none", display: "inline-flex",
                  alignItems: "center" }}
         target="_blank" rel="noreferrer"
         href={`https://x.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`}>
        𝕏 Post
      </a>
      <a style={{ ...btn, textDecoration: "none", display: "inline-flex",
                  alignItems: "center" }}
         target="_blank" rel="noreferrer"
         href={`https://www.reddit.com/submit?title=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`}>
        Reddit
      </a>
      <button style={btn} onClick={() => setShowEmbed((v) => !v)}
              aria-expanded={showEmbed}
              aria-label="Show embeddable iframe code">
        &lt;/&gt; Embed
      </button>
      {showEmbed && (
        <button style={btn} onClick={() => copy(embed, "embed")}>
          {copied === "embed" ? "✓ Copied!" : "Copy embed code"}
        </button>
      )}
    </div>
  );
}
