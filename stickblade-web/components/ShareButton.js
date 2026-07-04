"use client";
import { useState } from "react";

/**
 * Copy-to-clipboard share button.
 * - Primary path: navigator.clipboard.writeText (needs https + user gesture)
 * - Fallback: window.prompt so the user can copy manually
 * - Shows "✓ Copied!" for 2s then reverts to the original label
 *
 * Props:
 *   url    — string to copy
 *   label  — button text before click (default "📋 Share this fight")
 *   compact — smaller styling for use in table rows / list items
 */
export default function ShareButton({ url, label = "📋 Share this fight",
                                      compact = false }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!url) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        // No Clipboard API (old Safari on non-https, some in-app browsers).
        // window.prompt is universally supported and lets the user manually copy.
        window.prompt("Copy this link:", url);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Permission denied even with API present — fall back to prompt.
      window.prompt("Copy this link:", url);
    }
  }

  const size = compact
    ? { padding: "3px 8px", fontSize: 11 }
    : { padding: "8px 14px", fontSize: 13 };

  return (
    <button
      onClick={copy}
      style={{
        ...size,
        borderRadius: 5,
        border: `1px solid ${copied ? "var(--green, #56dc82)" : "var(--line)"}`,
        background: copied ? "rgba(86, 220, 130, 0.12)" : "transparent",
        color: copied ? "var(--green, #56dc82)" : "var(--text)",
        cursor: "pointer",
        letterSpacing: 1,
        transition: "background 0.15s, color 0.15s, border-color 0.15s",
        whiteSpace: "nowrap",
      }}>
      {copied ? "✓ Copied!" : label}
    </button>
  );
}
