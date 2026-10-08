"use client";
import { motion, useReducedMotion } from "framer-motion";
import { StaggerContainer, StaggerItem } from "@/components/MotionSection";

/* Weapon + arena option cards (review item 3).

   The old setup rendered `🗡 SWORD` / `❄ ICE` as bare labels in a segmented
   control, which forced users to leave the match screen and read the README
   to know what they were picking. Each option now carries the one line that
   actually changes how the duel plays.

   Motion: cards stagger in as the group scrolls into view, lift on hover, and
   the selected card carries a sliding accent rail. All of it is skipped under
   reduced motion (useReducedMotion) so the picker stays instant for those
   visitors. Copy is consistent with stickblade/weapons.py WEAPON_HINTS and
   main.py's arena modifiers. */

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
  const reduce = useReducedMotion();
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
              <motion.button
                type="button"
                className="card"
                role="radio"
                aria-checked={on}
                onClick={() => onChange(id)}
                title={info.desc}
                whileHover={reduce ? {} : { y: -3 }}
                whileTap={reduce ? {} : { scale: 0.98 }}
                transition={{ type: "spring", stiffness: 320, damping: 24 }}
                style={{ position: "relative", overflow: "hidden", width: "100%", height: "100%" }}
              >
                {on && (
                  <motion.span
                    aria-hidden="true"
                    layoutId={`card-rail-${legend}`}
                    style={{
                      position: "absolute", left: 0, top: 0, bottom: 0, width: 2,
                      background: "linear-gradient(180deg, var(--red), var(--gold))",
                    }}
                    transition={{ type: "spring", stiffness: 400, damping: 34 }}
                  />
                )}
                <span className="card-name">
                  <motion.span
                    aria-hidden="true"
                    display="inline-block"
                    animate={on && !reduce ? { scale: [1, 1.25, 1] } : {}}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    style={{ marginRight: 2 }}
                  >
                    {info.icon}
                  </motion.span>{" "}{info.label}
                </span>
                <span className="card-desc">{info.desc}</span>
              </motion.button>
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
