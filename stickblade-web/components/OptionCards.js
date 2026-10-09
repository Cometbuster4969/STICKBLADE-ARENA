"use client";
import { StaggerContainer, StaggerItem } from "@/components/MotionSection";

/* Weapon + arena option cards (review item 3).

   The old setup rendered `🗡 SWORD` / `❄ ICE` as bare labels in a segmented
   control, which forced users to leave the match screen and read the README
   to know what they were picking. Each option now carries the one line that
   actually changes how the duel plays.

   Motion: cards stagger in as the group scrolls into view, press on hover,
   and the selected card's accent rail scales in (`.card-rail`, globals.css).
   Reduced motion flattens all of it through the CSS guards — no JS-side
   branch needed. Copy is consistent with stickblade/weapons.py WEAPON_HINTS
   and main.py's arena modifiers. */

export const WEAPON_INFO = {
  sword:  { icon: "🗡", label: "Sword",  desc: "Balanced reach and damage — the reference weapon." },
  dagger: { icon: "🔪", label: "Dagger", desc: "Very short range, light and fast — must clinch (<70)." },
  spear:  { icon: "🥄", label: "Spear",  desc: "Longest melee reach (~100px) — kill zone is 120-180." },
  flail:  { icon: "⛓", label: "Flail",  desc: "Momentum weapon — spin_up first, then the ball hits hard." },
  bow:    { icon: "🏹", label: "Bow",    desc: "Projectile timing and aim — arrows drop, lead your shots." },
};

export const ARENA_INFO = {
  normal:      { icon: "🏟", label: "Normal", desc: "Standard stone floor physics." },
  ice:         { icon: "❄", label: "Ice",    desc: "~3× less friction — lunges overshoot, slides last." },
  low_gravity: { icon: "🌙", label: "Low G", desc: "35% gravity — floaty jumps, arrows drop far less." },
};

export const WEAPON_ORDER = ["sword", "dagger", "spear", "flail", "bow"];
export const ARENA_ORDER = ["normal", "ice", "low_gravity"];

function CardGroup({ legend, items, value, onChange, columns }) {
  return (
    <div>
      <div className="lbl" id={`${legend}-legend`}>{legend}</div>
      <StaggerContainer
        className="cards"
        role="radiogroup"
        aria-labelledby={`${legend}-legend`}
        staggerDelay={0.05}
        style={columns ? { gridTemplateColumns: columns } : undefined}
      >
        {items.map(([id, info]) => {
          const on = value === id;
          return (
            <StaggerItem key={id} direction="scale">
              <button
                type="button"
                className="card"
                role="radio"
                aria-checked={on}
                data-on={on ? "" : undefined}
                data-press
                onClick={() => onChange(id)}
                title={info.desc}
                style={{
                  "--hy": "-3px", "--ph": "1.015", "--pt": "0.98",
                  position: "relative", overflow: "hidden", width: "100%", height: "100%",
                }}
              >
                {/* One rail per card, toggled by [data-on]: the framer
                    layoutId version teleported a single node between cards,
                    which needs a layout engine. A rail that scales in place
                    reads the same and costs nothing. */}
                <span aria-hidden="true" className="card-rail" />
                <span className="card-name">
                  <span className="card-ico" aria-hidden="true" style={{ display: "inline-block", marginRight: 2 }}>
                    {info.icon}
                  </span>{" "}{info.label}
                </span>
                <span className="card-desc">{info.desc}</span>
              </button>
            </StaggerItem>
          );
        })}
      </StaggerContainer>
    </div>
  );
}

export function WeaponPicker({ value, onChange }) {
  return (
    <CardGroup
      legend="Weapon"
      items={WEAPON_ORDER.map((w) => [w, WEAPON_INFO[w]])}
      value={value}
      onChange={onChange}
    />
  );
}

export function ArenaPicker({ value, onChange }) {
  return (
    <CardGroup
      legend="Arena"
      items={ARENA_ORDER.map((a) => [a, ARENA_INFO[a]])}
      value={value}
      onChange={onChange}
    />
  );
}
