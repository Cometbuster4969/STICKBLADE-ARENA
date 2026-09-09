"use client";
import { useId } from "react";

/* Sharp-zone picker (review item 4).

   "Dangerous zones — the twist" is the mechanic that makes this benchmark
   different from every other LLM arena, and it was previously a plain
   multi-select row of `TIP / EDGE / BACK EDGE / POMMEL` text buttons. This
   renders the weapon schematic with the zones as clickable regions on the
   actual silhouette, plus the helper copy that says what selecting a zone
   means. Selection state is carried by colour AND by a ✓ + the word
   "lethal", so it never relies on colour alone (WCAG 1.4.1). */

const ZONE_COPY = {
  tip:         "Far end of the blade. Thrusts lead with it.",
  edge:        "The side facing the enemy. Slashes lead with it.",
  back_edge:   "The far side of the blade. Rising slashes lead with it.",
  pommel:      "The handle butt. Pommel strikes lead with it.",
  shaft:       "The pole between your hands and the spike.",
  butt:        "The back end of the pole.",
  ball:        "The flail head at any speed.",
  spikes:      "The same head, but only once it is moving FAST.",
  chain:       "The links between handle and head.",
  handle:      "The stick you hold.",
  arrowhead:   "The tip of a FIRED arrow — the archer's kill zone.",
  arrow_shaft: "The side of a fired arrow in flight.",
  bow_limb:    "The stave, when used as a club at point-blank range.",
};

const ZONE_LABEL = {
  tip: "TIP", edge: "EDGE", back_edge: "BACK EDGE", pommel: "POMMEL",
  shaft: "SHAFT", butt: "BUTT", ball: "BALL", spikes: "SPIKES",
  chain: "CHAIN", handle: "HANDLE", arrowhead: "ARROWHEAD",
  arrow_shaft: "ARROW SHAFT", bow_limb: "BOW LIMB",
};

function Zone({ zone, on, onToggle, children }) {
  return (
    <g
      role="button"
      tabIndex={0}
      aria-pressed={on}
      aria-label={`${ZONE_LABEL[zone]} zone — ${on ? "lethal" : "blunt"}. ${ZONE_COPY[zone]}`}
      className="zseg"
      data-on={on ? "true" : "false"}
      onClick={() => onToggle(zone)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle(zone);
        }
      }}
      style={{ cursor: "pointer" }}
    >
      {children}
    </g>
  );
}

const FILL_OFF = "rgba(180,190,215,0.14)";
const STROKE = "#8b91ab";

function SwordSvg({ dagger, zones, on, onToggle }) {
  const bladeEnd = dagger ? 170 : 226;
  const tipStart = bladeEnd - (dagger ? 34 : 52);
  return (
    <svg className="zone-svg" viewBox="0 0 260 92" role="img"
         aria-label={`${dagger ? "Dagger" : "Sword"} zone diagram`}>
      <Zone zone="pommel" on={on("pommel")} onToggle={onToggle}>
        <circle cx="20" cy="46" r="9" fill={on("pommel") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="20" y="76" textAnchor="middle" fontSize="9" fill="#b6bbd0">POMMEL</text>
      </Zone>
      <rect x="29" y="42" width="34" height="8" fill="rgba(180,190,215,0.10)" stroke={STROKE} strokeWidth="1" />
      <Zone zone="back_edge" on={on("back_edge")} onToggle={onToggle}>
        <polygon points={`63,42 ${tipStart},42 ${tipStart},30 63,36`}
                 fill={on("back_edge") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x={(63 + tipStart) / 2} y="24" textAnchor="middle" fontSize="9" fill="#b6bbd0">BACK EDGE</text>
      </Zone>
      <Zone zone="edge" on={on("edge")} onToggle={onToggle}>
        <polygon points={`63,50 ${tipStart},50 ${tipStart},62 63,56`}
                 fill={on("edge") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x={(63 + tipStart) / 2} y="78" textAnchor="middle" fontSize="9" fill="#b6bbd0">EDGE</text>
      </Zone>
      <Zone zone="tip" on={on("tip")} onToggle={onToggle}>
        <polygon points={`${tipStart},30 ${tipStart},62 ${bladeEnd},46`}
                 fill={on("tip") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x={tipStart + 14} y="24" textAnchor="middle" fontSize="9" fill="#b6bbd0">TIP</text>
      </Zone>
      <text x="130" y="90" textAnchor="middle" fontSize="8.5" fill="#4d5168">
        {zones.length} of 4 zones lethal
      </text>
    </svg>
  );
}

function SpearSvg({ zones, on, onToggle }) {
  return (
    <svg className="zone-svg" viewBox="0 0 260 92" role="img" aria-label="Spear zone diagram">
      <Zone zone="butt" on={on("butt")} onToggle={onToggle}>
        <rect x="8" y="40" width="26" height="12" rx="3" fill={on("butt") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="21" y="72" textAnchor="middle" fontSize="9" fill="#b6bbd0">BUTT</text>
      </Zone>
      <Zone zone="shaft" on={on("shaft")} onToggle={onToggle}>
        <rect x="34" y="42" width="160" height="8" fill={on("shaft") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="114" y="72" textAnchor="middle" fontSize="9" fill="#b6bbd0">SHAFT</text>
      </Zone>
      <Zone zone="tip" on={on("tip")} onToggle={onToggle}>
        <polygon points="194,34 194,58 232,46" fill={on("tip") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="205" y="26" textAnchor="middle" fontSize="9" fill="#b6bbd0">TIP</text>
      </Zone>
      <text x="130" y="90" textAnchor="middle" fontSize="8.5" fill="#4d5168">
        {zones.length} of 3 zones lethal
      </text>
    </svg>
  );
}

function FlailSvg({ zones, on, onToggle }) {
  return (
    <svg className="zone-svg" viewBox="0 0 260 92" role="img" aria-label="Flail zone diagram">
      <Zone zone="handle" on={on("handle")} onToggle={onToggle}>
        <rect x="12" y="40" width="56" height="12" rx="4" fill={on("handle") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="40" y="72" textAnchor="middle" fontSize="9" fill="#b6bbd0">HANDLE</text>
      </Zone>
      <Zone zone="chain" on={on("chain")} onToggle={onToggle}>
        <path d="M68 46 q 30 -18 60 0" fill="none" stroke={STROKE} strokeWidth="6" strokeLinecap="round" opacity="0.9" />
        <text x="98" y="26" textAnchor="middle" fontSize="9" fill="#b6bbd0">CHAIN</text>
      </Zone>
      <Zone zone="spikes" on={on("spikes")} onToggle={onToggle}>
        <circle cx="168" cy="46" r="26" fill={on("spikes") ? undefined : "rgba(180,190,215,0.06)"} stroke={STROKE} strokeWidth="1.5" strokeDasharray="3 3" />
        <text x="168" y="18" textAnchor="middle" fontSize="9" fill="#b6bbd0">SPIKES (fast)</text>
      </Zone>
      <Zone zone="ball" on={on("ball")} onToggle={onToggle}>
        <circle cx="168" cy="46" r="15" fill={on("ball") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="168" y="84" textAnchor="middle" fontSize="9" fill="#b6bbd0">BALL</text>
      </Zone>
      <text x="230" y="90" textAnchor="end" fontSize="8.5" fill="#4d5168">
        {zones.length} of 4 zones lethal
      </text>
    </svg>
  );
}

function BowSvg({ zones, on, onToggle }) {
  return (
    <svg className="zone-svg" viewBox="0 0 260 92" role="img" aria-label="Bow zone diagram">
      <Zone zone="bow_limb" on={on("bow_limb")} onToggle={onToggle}>
        <path d="M46 12 q 34 34 0 68" fill="none" stroke={STROKE} strokeWidth="7" strokeLinecap="round" />
        <text x="34" y="88" fontSize="9" fill="#b6bbd0">BOW LIMB</text>
      </Zone>
      <line x1="46" y1="12" x2="46" y2="80" stroke="#4d5168" strokeWidth="1" strokeDasharray="2 3" />
      <Zone zone="arrow_shaft" on={on("arrow_shaft")} onToggle={onToggle}>
        <rect x="60" y="43" width="140" height="6" fill={on("arrow_shaft") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="130" y="70" textAnchor="middle" fontSize="9" fill="#b6bbd0">ARROW SHAFT</text>
      </Zone>
      <Zone zone="arrowhead" on={on("arrowhead")} onToggle={onToggle}>
        <polygon points="200,36 200,56 234,46" fill={on("arrowhead") ? undefined : FILL_OFF} stroke={STROKE} strokeWidth="1.5" />
        <text x="206" y="26" textAnchor="middle" fontSize="9" fill="#b6bbd0">ARROWHEAD</text>
      </Zone>
      <text x="230" y="90" textAnchor="end" fontSize="8.5" fill="#4d5168">
        {zones.length} of 3 zones lethal
      </text>
    </svg>
  );
}

// Zone lists per weapon, so a caller that forgets `allZones` degrades to a
// correct-looking picker instead of throwing on `.map` of undefined.
const DEFAULT_ZONES = {
  sword:  ["tip", "edge", "back_edge", "pommel"],
  dagger: ["tip", "edge", "pommel"],
  spear:  ["tip", "shaft", "butt"],
  flail:  ["ball", "spikes", "chain", "handle"],
  bow:    ["arrowhead", "arrow_shaft", "bow_limb"],
};

export default function SharpZonePicker({ weapon, zones = [], allZones, onToggle }) {
  allZones = allZones && allZones.length
    ? allZones
    : (DEFAULT_ZONES[weapon] || DEFAULT_ZONES.sword);
  const helpId = useId();
  const isOn = (z) => zones.includes(z);
  const Diagram = weapon === "spear" ? SpearSvg
    : weapon === "flail" ? FlailSvg
    : weapon === "bow" ? BowSvg
    : SwordSvg;

  return (
    <div>
      <div className="lbl" id={`${helpId}-lbl`}>Dangerous zones — the twist</div>
      <p className="zone-help" id={helpId} style={{ marginBottom: 10 }}>
        Only the zones you select deal lethal damage; everything else is blunt
        and mostly just pushes. Choose one or more — a fast sharp hit to the
        head is an instant kill, so this single choice decides the whole duel.
      </p>
      <div className="zone-picker">
        <Diagram
          zones={zones}
          on={isOn}
          onToggle={onToggle}
          dagger={weapon === "dagger"}
        />
        <div className="chips" role="group" aria-labelledby={`${helpId}-lbl`}>
          {allZones.map((z) => (
            <button
              key={z}
              type="button"
              className="chip"
              aria-pressed={isOn(z)}
              onClick={() => onToggle(z)}
              title={ZONE_COPY[z]}
              style={{ textAlign: "left" }}
            >
              <b aria-hidden="true">{isOn(z) ? "✓ " : "· "}</b>
              {ZONE_LABEL[z]}
              <span style={{ color: "var(--dim)", marginLeft: 6, textTransform: "none", letterSpacing: 0 }}>
                {isOn(z) ? "lethal" : "blunt"}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
