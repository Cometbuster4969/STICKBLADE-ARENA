"use client";
import { Suspense, useEffect, useId, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getModels, createTournament, getTournament, listTournaments,
} from "@/lib/api";

const WEAPON_ZONES = {
  sword:  ["tip", "edge", "back_edge", "pommel"],
  dagger: ["tip", "edge", "back_edge", "pommel"],
  spear:  ["tip", "shaft", "butt"],
  flail:  ["ball", "spikes", "chain", "handle"],
  bow:    ["arrowhead", "arrow_shaft", "bow_limb"],
};
const WEAPONS = [
  ["sword",  "🗡 SWORD"], ["dagger", "🔪 DAGGER"], ["spear", "⊥ SPEAR"],
  ["flail",  "⛓ FLAIL"], ["bow",    "🏹 BOW"],
];
const ARENAS = [
  ["normal", "🏟 NORMAL"], ["ice", "❄ ICE"], ["low_gravity", "🌙 LOW G"],
];

export default function TournamentRoute() {
  return (
    <Suspense fallback={<div style={{ color: "var(--dim)" }}>Loading…</div>}>
      <TournamentPage />
    </Suspense>
  );
}

function TournamentPage() {
  const params = useSearchParams();
  const router = useRouter();
  const tid = params.get("id");
  return tid
    ? <BracketView tid={tid} onPickOther={(id) => router.push(`/tournament?id=${id}`)} />
    : <CreateBracket onCreated={(id) => router.push(`/tournament?id=${id}`)} />;
}

/* =========================================================================
 *  Create-bracket form
 * ========================================================================= */
function CreateBracket({ onCreated }) {
  const [allModels, setAllModels] = useState([]);
  const [picked, setPicked] = useState([]);    // model id list, in seed order
  const [size, setSize] = useState(8);
  const [weapon, setWeapon] = useState("sword");
  const [sharp, setSharp] = useState(["tip"]);
  const [arena, setArena] = useState("normal");
  const [mode, setMode] = useState("macro");
  const [name, setName] = useState("Friday Night Brawl");
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    getModels().then(setAllModels).catch((e) => setErr(e.message));
    listTournaments().then(setRecent).catch(() => {});
  }, []);

  const pickWeapon = (w) => { setWeapon(w); setSharp([WEAPON_ZONES[w][0]]); };

  const toggleModel = (id) => {
    setPicked((p) => {
      if (p.includes(id)) return p.filter((x) => x !== id);
      if (p.length >= size) return p;          // cap at bracket size
      return [...p, id];
    });
  };
  const move = (id, dir) => {
    setPicked((p) => {
      const i = p.indexOf(id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= p.length) return p;
      const np = p.slice();
      [np[i], np[j]] = [np[j], np[i]];
      return np;
    });
  };

  async function start() {
    setErr(""); setBusy(true);
    try {
      if (picked.length !== size)
        throw new Error(`pick exactly ${size} models (currently ${picked.length})`);
      const r = await createTournament({
        name, models: picked, weapon, sharp, arena, mode,
      });
      onCreated(r.tournament_id);
    } catch (e) {
      setErr(e.message); setBusy(false);
    }
  }

  return (
    <>
      <section className="tagline" style={{ marginBottom: 8 }}>
        <h1>🏆 Tournament</h1>
        <p>Bracket of {size} models · single elimination · pure carnage.</p>
      </section>

      <div className="row">
        {/* Setup panel */}
        <div className="panel glow-red">
          <div className="panel-head">
            <span className="panel-title"><span className="tick" /> Bracket Setup</span>
          </div>

          <div>
            <label className="lbl">Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                   aria-label="Tournament name" />
          </div>

          <div>
            <label className="lbl">Bracket size</label>
            <div className="zones">
              {[4, 8].map((s) => (
                <div key={s}
                  role="button" tabIndex={0} aria-pressed={size === s}
                  className={"zone" + (size === s ? " on" : "")}
                  onClick={() => { setSize(s); setPicked((p) => p.slice(0, s)); }}>
                  {s} models
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="lbl">Weapon</label>
            <div className="zones">
              {WEAPONS.map(([w, label]) => (
                <div key={w} className={"zone" + (weapon === w ? " on" : "")}
                  role="button" tabIndex={0} aria-pressed={weapon === w}
                  onClick={() => pickWeapon(w)}>{label}</div>
              ))}
            </div>
          </div>

          <div>
            <label className="lbl">Arena</label>
            <div className="zones">
              {ARENAS.map(([a, label]) => (
                <div key={a} className={"zone" + (arena === a ? " on" : "")}
                  role="button" tabIndex={0} aria-pressed={arena === a}
                  onClick={() => setArena(a)}>{label}</div>
              ))}
            </div>
          </div>

          <div>
            <label className="lbl">Control mode</label>
            <div className="zones">
              <div className={"zone" + (mode === "macro" ? " on" : "")}
                role="button" tabIndex={0} aria-pressed={mode === "macro"}
                onClick={() => setMode("macro")}>🎯 MACRO</div>
              <div className={"zone" + (mode === "joint" ? " on" : "")}
                role="button" tabIndex={0} aria-pressed={mode === "joint"}
                onClick={() => setMode("joint")}>🧠 JOINT</div>
            </div>
          </div>

          <div>
            <label className="lbl">Dangerous zones</label>
            <div className="zones">
              {WEAPON_ZONES[weapon].map((z) => (
                <div key={z}
                  role="button" tabIndex={0} aria-pressed={sharp.includes(z)}
                  className={"zone" + (sharp.includes(z) ? " on" : "")}
                  onClick={() => setSharp((s) =>
                    s.includes(z) ? (s.length > 1 ? s.filter((x) => x !== z) : s) : [...s, z])}>
                  {z.replace("_", " ").toUpperCase()}
                </div>
              ))}
            </div>
          </div>

          <button className="fight-btn" onClick={start} disabled={busy || picked.length !== size}>
            {busy ? "⚙ Queuing" : `🏆 Start ${size}-Bracket`}
          </button>
          {err && <div className="status" style={{ color: "var(--red-2)" }}>✖ {err}</div>}
        </div>

        {/* Pick the field */}
        <div className="panel glow-blue">
          <div className="panel-head">
            <span className="panel-title gold">
              <span className="tick" /> Seed the Field ({picked.length} / {size})
            </span>
          </div>
          <p style={{ color: "var(--dim)", fontSize: 13 }}>
            Order matters: top of the list = #1 seed (faces the bottom seed in round 1).
          </p>

          {/* picked / seeded list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 10 }}>
            {picked.map((id, i) => (
              <div key={id} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                background: "var(--bg-3)", borderRadius: "var(--radius-xs)",
                border: "1px solid var(--line)",
              }}>
                <span style={{
                  width: 22, height: 22, borderRadius: 4, display: "inline-flex",
                  alignItems: "center", justifyContent: "center", fontWeight: 800,
                  background: "var(--bg-2-solid)", color: "var(--gold)", fontSize: 12,
                }}>{i + 1}</span>
                <span style={{ flex: 1 }}>{allModels.find((m) => m.id === id)?.name || id}</span>
                <button onClick={() => move(id, -1)} disabled={i === 0}
                  style={{ width: "auto", padding: "4px 8px", fontSize: 12 }}
                  aria-label="Move up">▲</button>
                <button onClick={() => move(id, +1)} disabled={i === picked.length - 1}
                  style={{ width: "auto", padding: "4px 8px", fontSize: 12 }}
                  aria-label="Move down">▼</button>
                <button onClick={() => toggleModel(id)}
                  style={{ width: "auto", padding: "4px 8px", fontSize: 12,
                           color: "var(--red-2)", borderColor: "var(--red-2)" }}
                  aria-label="Remove">×</button>
              </div>
            ))}
            {!picked.length && (
              <div style={{ color: "var(--dim)", fontSize: 13, textAlign: "center", padding: 8 }}>
                no models chosen yet — click to add from below
              </div>
            )}
          </div>

          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <label className="lbl">Available models</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {allModels.map((m) => {
                const isOn = picked.includes(m.id);
                const full = picked.length >= size && !isOn;
                return (
                  <button key={m.id}
                    onClick={() => toggleModel(m.id)}
                    disabled={full}
                    style={{
                      width: "auto", padding: "6px 10px", fontSize: 12,
                      background: isOn ? "rgba(255,197,71,0.10)" : "var(--bg-3)",
                      borderColor: isOn ? "var(--gold)" : "var(--line)",
                      color: isOn ? "var(--gold)" : "var(--text-2)",
                    }}>
                    {isOn ? "✓ " : "+ "}{m.name}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Recent tournaments */}
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title"><span className="tick" /> Recent Brackets</span>
        </div>
        {!recent.length
          ? <div style={{ color: "var(--dim)", fontSize: 13, padding: 8 }}>
              no tournaments yet — start one above
            </div>
          : (
            <table className="lb">
              <thead><tr><th>Name</th><th>Size</th><th>Weapon</th><th>Status</th><th>Champion</th><th></th></tr></thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id}>
                    <td>{t.name || "—"}</td>
                    <td className="r">{t.size}</td>
                    <td>{t.weapon || "sword"}</td>
                    <td><StatusPill status={t.status} /></td>
                    <td className="model" style={{ color: t.winner_name ? "var(--gold)" : "var(--dim)" }}>
                      {t.winner_name || (t.status === "done" ? "—" : `R${t.current_round || 0}`)}
                    </td>
                    <td><a className="mlink" href={`/tournament?id=${t.id}`}>▶ view</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </>
  );
}

function StatusPill({ status }) {
  const color = status === "done" ? "var(--green)"
              : status === "running" ? "var(--gold)"
              : status === "error" ? "var(--red-2)"
              : "var(--text-2)";
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 999,
      border: `1px solid ${color}`, color, fontSize: 11, fontWeight: 700,
      letterSpacing: 1, textTransform: "uppercase",
    }}>{status}</span>
  );
}

/* =========================================================================
 *  Bracket viewer (?id=…)
 * ========================================================================= */
function BracketView({ tid, onPickOther }) {
  const [t, setT] = useState(null);
  const [err, setErr] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const data = await getTournament(tid);
        if (cancelled) return;
        setT(data);
        // poll every 2.5 s while running; 30 s once done
        const next = data.status === "done" || data.status === "error" ? 30000 : 2500;
        pollRef.current = setTimeout(tick, next);
      } catch (e) {
        setErr(e.message);
      }
    };
    tick();
    return () => { cancelled = true; clearTimeout(pollRef.current); };
  }, [tid]);

  if (err) return <div className="status">✖ {err}</div>;
  if (!t) return <div style={{ color: "var(--dim)" }}>Loading bracket…</div>;

  const maxRound = Math.log2(t.size);
  const rounds = [];
  for (let r = 1; r <= maxRound; r++) {
    rounds.push(t.matches.filter((m) => m.round === r));
  }

  const nameOf = (id) => t.model_names[id] || id || "—";
  const champion = t.winner_model;

  // "Match 3 of 7 in progress — Llama vs DeepSeek"
  // Heuristic for THE current match: has both fighters + a match_id +
  // no winner yet. There's typically only one at a time because the
  // tournament worker runs bracket matches sequentially. Also count
  // completed / total for the "N of M" hint.
  const allBracketMatches = t.matches.filter(
    (m) => m.model_a && m.model_b);
  const completed = allBracketMatches.filter((m) => m.winner_model).length;
  const total = allBracketMatches.length;
  const current = t.status === "running"
    ? allBracketMatches.find((m) => !m.winner_model && m.match_id)
    : null;

  return (
    <>
      <section className="tagline" style={{ marginBottom: 8 }}>
        <h1>🏆 {t.name || "Bracket"}</h1>
        <p>
          {t.size}-model single elimination
          <span className="dot">·</span>
          {t.weapon}
          <span className="dot">·</span>
          sharp: {t.sharp}
          <span className="dot">·</span>
          arena: {t.arena}
          <span className="dot">·</span>
          mode: {t.mode}
          <span className="dot">·</span>
          <StatusPill status={t.status} />
        </p>
      </section>

      {current && (
        <div className="panel" style={{
          padding: "12px 16px", textAlign: "center",
          border: "1px solid var(--gold, #d4b962)",
          background: "rgba(212,185,98,0.06)",
          animation: "sb-pulse 1.8s ease-in-out infinite",
        }}>
          <div style={{ fontSize: 11, letterSpacing: 3, color: "var(--gold, #d4b962)",
                        textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
            🥊 Match {completed + 1} of {total} in progress
          </div>
          <div style={{ fontSize: 15, color: "var(--text)" }}>
            <b>{nameOf(current.model_a)}</b>
            <span style={{ color: "var(--dim)", margin: "0 10px" }}>vs</span>
            <b>{nameOf(current.model_b)}</b>
          </div>
          <style jsx>{`
            @keyframes sb-pulse {
              0%, 100% { box-shadow: 0 0 0 0 rgba(212,185,98,0.4); }
              50%      { box-shadow: 0 0 0 8px rgba(212,185,98,0);  }
            }
          `}</style>
        </div>
      )}

      {champion && (
        <div className="panel" style={{ textAlign: "center", padding: 18,
          background: "radial-gradient(600px 200px at 50% 0%, rgba(255,197,71,0.18), transparent 70%), var(--bg-2)" }}>
          <div style={{ fontSize: 11, letterSpacing: 3, color: "var(--gold)",
                        textTransform: "uppercase", marginBottom: 4, fontWeight: 700 }}>
            🥇 Champion
          </div>
          <div style={{ fontSize: 24, fontWeight: 800,
                        fontFamily: "var(--font-display)", letterSpacing: 2 }}>
            {nameOf(champion)}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 20, overflowX: "auto", paddingBottom: 8 }}>
        {rounds.map((roundMatches, ri) => (
          <div key={ri} style={{
            minWidth: 260, display: "flex", flexDirection: "column",
            justifyContent: "space-around", gap: 12,
          }}>
            <div style={{
              fontSize: 11, letterSpacing: 2, color: "var(--dim)",
              textTransform: "uppercase", fontWeight: 700, textAlign: "center",
            }}>
              {ri === rounds.length - 1 ? "Final"
                : ri === rounds.length - 2 ? "Semifinals"
                : ri === 0 ? "Round 1"
                : `Round ${ri + 1}`}
            </div>
            {roundMatches.map((m) => (
              <BracketCard key={m.id} m={m} nameOf={nameOf}
                isCurrent={current && current.id === m.id} />
            ))}
            {!roundMatches.length && (
              <div style={{ color: "var(--dim)", fontSize: 12, textAlign: "center" }}>
                pending
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
        <button onClick={() => onPickOther("")} style={{ width: "auto" }}>
          ← Back to all tournaments
        </button>
      </div>
    </>
  );
}

function BracketCard({ m, nameOf, isCurrent = false }) {
  const aWon = m.winner_model && m.winner_model === m.model_a;
  const bWon = m.winner_model && m.winner_model === m.model_b;
  const pending = !m.winner_model;
  const cardStyle = {
    border: isCurrent
      ? "1px solid var(--gold, #d4b962)"
      : "1px solid var(--line)",
    borderRadius: "var(--radius-sm)",
    background: "var(--bg-2)",
    overflow: "hidden",
    boxShadow: pending ? "none" : "0 6px 20px rgba(0,0,0,0.35)",
    animation: isCurrent ? "sb-card-pulse 1.6s ease-in-out infinite" : "none",
    // Fully-pending future matches (no fighters assigned yet, e.g. Round 2
    // slots before Round 1 finishes) get muted so users know they're
    // waiting on upstream results.
    opacity: (!m.model_a || !m.model_b) ? 0.55 : 1,
  };
  const rowStyle = (won, lost) => ({
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "10px 12px", fontSize: 13,
    background: won ? "rgba(255,197,71,0.10)" : "transparent",
    color: lost ? "var(--mute)" : "var(--text)",
    fontWeight: won ? 700 : 500,
    borderBottom: "1px solid var(--line)",
  });
  return (
    <div style={cardStyle}>
      <div style={rowStyle(aWon, bWon)}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {aWon && "🥇 "}{nameOf(m.model_a)}
        </span>
        {pending && <span style={{ color: "var(--dim)", fontSize: 10 }}>vs</span>}
      </div>
      <div style={{ ...rowStyle(bWon, aWon), borderBottom: "none" }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {bWon && "🥇 "}{nameOf(m.model_b)}
        </span>
        {m.match_id && (
          <a className="mlink" style={{ fontSize: 11 }}
             href={`/replay?id=${m.match_id}`}>watch ▶</a>
        )}
      </div>
      <style jsx>{`
        @keyframes sb-card-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(212,185,98,0.5); }
          50%      { box-shadow: 0 0 0 6px rgba(212,185,98,0);  }
        }
      `}</style>
    </div>
  );
}
