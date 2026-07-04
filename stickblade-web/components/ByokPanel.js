"use client";
import { useEffect, useState } from "react";
import {
  readByokKey, writeByokKey,
  readByokEnabled, writeByokEnabled,
  isValidByokFormat, maskKey,
} from "@/lib/byok";

/**
 * Collapsible BYOK settings panel. Lives in the setup panel above the
 * Fight button. Two states:
 *   - default (no key saved): a single "🔑 Use my own OpenRouter key"
 *     button that expands into a paste field + save/cancel
 *   - active (key saved + enabled): a small badge showing the masked
 *     key with "clear" and "disable" actions
 *
 * All storage is localStorage — nothing hits the network from here.
 * page.js reads readByokKey() when about to POST /api/match and only
 * includes the api_key field if the user has enabled BYOK.
 */
export default function ByokPanel() {
  const [saved,   setSaved]   = useState("");
  const [enabled, setEnabled] = useState(false);
  const [open,    setOpen]    = useState(false);
  const [draft,   setDraft]   = useState("");
  const [err,     setErr]     = useState("");

  useEffect(() => {
    setSaved(readByokKey());
    setEnabled(readByokEnabled());
  }, []);

  function save() {
    const k = draft.trim();
    if (!isValidByokFormat(k)) {
      setErr("Keys look like sk-or-v1-... (20+ chars). Paste from openrouter.ai/settings/keys.");
      return;
    }
    writeByokKey(k);
    writeByokEnabled(true);
    setSaved(k);
    setEnabled(true);
    setOpen(false);
    setDraft("");
    setErr("");
  }

  function clear() {
    writeByokKey("");
    writeByokEnabled(false);
    setSaved("");
    setEnabled(false);
    setOpen(false);
    setDraft("");
    setErr("");
  }

  function toggle() {
    const next = !enabled;
    setEnabled(next);
    writeByokEnabled(next);
  }

  // ---- Active state: key saved, ready to fight ----
  if (saved && !open) {
    return (
      <div style={{
        marginTop: 8, padding: "8px 12px", borderRadius: 6,
        border: `1px solid ${enabled ? "var(--gold, #d4b962)" : "var(--line)"}`,
        background: enabled ? "rgba(212, 185, 98, 0.08)" : "rgba(255,255,255,0.02)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        flexWrap: "wrap", gap: 8, fontSize: 13,
      }}>
        <span style={{ color: enabled ? "var(--gold, #d4b962)" : "var(--dim)" }}>
          🔑 <b>{enabled ? "BYOK active" : "BYOK saved but disabled"}</b>
          <span style={{ color: "var(--dim)", marginLeft: 8,
                          fontFamily: "ui-monospace, Consolas, monospace" }}>
            {maskKey(saved)}
          </span>
        </span>
        <span style={{ display: "flex", gap: 8 }}>
          <button onClick={toggle} className="byok-btn"
                  style={{ fontSize: 11, padding: "3px 8px" }}>
            {enabled ? "disable" : "enable"}
          </button>
          <button onClick={() => setOpen(true)} className="byok-btn"
                  style={{ fontSize: 11, padding: "3px 8px" }}>
            change
          </button>
          <button onClick={clear} className="byok-btn"
                  style={{ fontSize: 11, padding: "3px 8px",
                            color: "var(--red-2, #dc5656)" }}>
            clear
          </button>
        </span>
        <style jsx>{`
          .byok-btn {
            background: transparent;
            border: 1px solid var(--line);
            color: var(--text);
            border-radius: 4px;
            cursor: pointer;
            letter-spacing: 1px;
            text-transform: uppercase;
          }
          .byok-btn:hover { background: rgba(255,255,255,0.06); }
        `}</style>
      </div>
    );
  }

  // ---- Default: no key saved yet ----
  if (!open) {
    return (
      <div style={{ marginTop: 8, textAlign: "right" }}>
        <button onClick={() => setOpen(true)}
                style={{
                  background: "transparent", border: "1px dashed var(--line)",
                  color: "var(--dim)", borderRadius: 6,
                  padding: "6px 10px", fontSize: 12, cursor: "pointer",
                  letterSpacing: 1,
                }}>
          🔑 Use my own OpenRouter key (skip free-tier throttling)
        </button>
      </div>
    );
  }

  // ---- Open: paste + save form ----
  return (
    <div style={{
      marginTop: 8, padding: 12, borderRadius: 6,
      border: "1px solid var(--gold, #d4b962)",
      background: "rgba(212, 185, 98, 0.06)",
    }}>
      <div style={{ fontSize: 11, letterSpacing: 2, color: "var(--gold, #d4b962)",
                    fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>
        🔑 Bring your own OpenRouter key
      </div>
      <p style={{ fontSize: 12, color: "var(--dim)", margin: "0 0 8px",
                  lineHeight: 1.5 }}>
        Free-tier accounts get <b>50 req/day per model</b>, shared across every
        user of this site. Paste your own key to bypass that cap — your matches
        will draw from <em>your</em> quota (add $10 credit on OpenRouter to lift
        it to 1000 req/day). Get a key at{" "}
        <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer"
           style={{ color: "var(--gold, #d4b962)" }}>
          openrouter.ai/settings/keys
        </a>.
      </p>
      <p style={{ fontSize: 11, color: "var(--dim)", margin: "0 0 10px",
                  fontStyle: "italic" }}>
        Stored in <b>your browser's localStorage only</b>. Sent to our backend
        as a header on <code>POST /api/match</code> — never logged, never saved
        to the database, never echoed back.
      </p>
      <input
        type="password"
        placeholder="sk-or-v1-…"
        value={draft}
        onChange={(e) => { setDraft(e.target.value); setErr(""); }}
        onKeyDown={(e) => { if (e.key === "Enter") save(); }}
        autoComplete="off"
        spellCheck={false}
        style={{
          width: "100%", padding: "8px 10px", borderRadius: 4,
          border: "1px solid var(--line)", background: "rgba(0,0,0,0.3)",
          color: "var(--text)", fontFamily: "ui-monospace, Consolas, monospace",
          fontSize: 12,
        }}
      />
      {err && (
        <div style={{ marginTop: 6, color: "var(--red-2, #dc5656)", fontSize: 12 }}>
          {err}
        </div>
      )}
      <div style={{ marginTop: 10, display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={() => { setOpen(false); setDraft(""); setErr(""); }}
                style={{ padding: "6px 12px", borderRadius: 4,
                          border: "1px solid var(--line)", background: "transparent",
                          color: "var(--text)", cursor: "pointer", fontSize: 12,
                          letterSpacing: 1 }}>
          cancel
        </button>
        <button onClick={save}
                disabled={!draft.trim()}
                style={{ padding: "6px 12px", borderRadius: 4,
                          border: "1px solid var(--gold, #d4b962)",
                          background: "var(--gold, #d4b962)",
                          color: "#000", cursor: "pointer", fontSize: 12,
                          fontWeight: 700, letterSpacing: 1,
                          opacity: draft.trim() ? 1 : 0.5 }}>
          save & enable
        </button>
      </div>
    </div>
  );
}
