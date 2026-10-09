/* HeroPlate — the hero's "figure". Not decorative art: a motion-study plate
   of what the benchmark actually measures. Two stick fighters (drawn in the
   same green/blue inks the canvas paints P1/P2 with), the weapon, and the
   red dashed annotation for the lethal tip arc — the way an engineering
   drawing calls out geometry. Every label states a real rule of the engine
   (sword tip contact, sharp-mode kill, 24-turn cap, blind vote); nothing is
   invented numbers.

   Rendered as inline SVG so it costs zero requests, scales crisp, and paints
   before hydration. Pure markup: no client hooks needed. */

const INK = "var(--text)";
const DIM = "var(--dim)";
const RED = "var(--red)";
const GREEN = "var(--green)";
const BLUE = "var(--blue)";
const FAINT = "var(--line)";

// A stick figure at (x, y-foot) with the torso leaning `lean` px toward the
// opponent and the weapon arm raised to (hx, hy). Stylised like the engine's
// ragdolls: circle head, straight limbs.
function Fighter({ x, y, lean, hand, color, flip = false }) {
  const hip = [x + lean * 0.4, y - 42];
  const neck = [x + lean, y - 66];
  const head = [neck[0] + (flip ? -3 : 3), neck[1] - 10];
  const s = flip ? -1 : 1;
  return (
    <g stroke={color} strokeWidth="2.4" strokeLinecap="round" fill="none">
      {/* legs: front planted, back trailing */}
      <path d={`M${hip} L${x + 20 * s} ${y} M${hip} L${x - 26 * s} ${y}`} />
      {/* torso */}
      <path d={`M${hip} L${neck}`} />
      {/* back arm guarding, weapon arm reaching the hand point */}
      <path d={`M${neck} L${x - 14 * s} ${neck[1] + 16} M${neck} L${hand[0]} ${hand[1]}`} />
      <circle cx={head[0]} cy={head[1]} r="8.5" fill={color} stroke="none" />
    </g>
  );
}

export default function HeroPlate() {
  const tip = [300, 148];
  return (
    <figure className="hero-plate">
      <svg viewBox="0 0 460 300" role="img" aria-label="Schematic plate: two stick fighters at weapon-tip distance, the lethal arc around the sword tip annotated in red.">
        {/* corner ticks: the plate framing */}
        <g stroke={INK} strokeWidth="1" opacity="0.55">
          <path d="M14 14 h14 M14 14 v14 M446 14 h-14 M446 14 v14 M14 286 h14 M14 286 v-14 M446 286 h-14 M446 286 v-14" />
        </g>
        {/* ground line, with the faint tick ruler of a study plate */}
        <line x1="34" y1="252" x2="426" y2="252" stroke={INK} strokeWidth="1.4" opacity="0.7" />
        <g stroke={DIM} strokeWidth="1" opacity="0.55">
          {Array.from({ length: 20 }, (_, i) => (
            <line key={i} x1={42 + i * 20} y1="252" x2={42 + i * 20} y2={i % 5 === 0 ? 244 : 248} />
          ))}
        </g>

        {/* P1 lunging (green) — hand holds the sword at the arc's start */}
        <Fighter x={150} y={252} lean={22} hand={[212, 168]} color={GREEN} />
        {/* P2 back-pedalling (blue) */}
        <Fighter x={352} y={252} lean={-14} hand={[322, 150]} color={BLUE} flip />

        {/* weapons: P1's blade thrusts toward the tip; P2's guards high */}
        <g strokeLinecap="round">
          <line x1="212" y1="168" x2={tip[0]} y2={tip[1]} stroke={GREEN} strokeWidth="3" />
          <line x1="205" y1="175" x2="219" y2="161" stroke={GREEN} strokeWidth="2" />
          <line x1="322" y1="150" x2="344" y2="108" stroke={BLUE} strokeWidth="3" />
          <line x1="315" y1="150" x2="329" y2="164" stroke={BLUE} strokeWidth="2" />
        </g>

        {/* the lethal tip arc — red dashed, drawn the way the engine annotates
            the sharp-hit zone */}
        <circle cx={tip[0]} cy={tip[1]} r="34" fill={RED} fillOpacity="0.07" stroke={RED} strokeWidth="1.3" strokeDasharray="5 4" />
        {/* swing trace from P1's shoulder through the tip */}
        <path d="M172 150 Q236 96 300 148" fill="none" stroke={RED} strokeWidth="1.1" strokeDasharray="2 5" opacity="0.5" />

        {/* leader-line callouts, mono like instrument labels */}
        <g stroke={FAINT} strokeWidth="1">
          <path d={`M${tip[0] + 26} ${tip[1] - 24} L392 92 L424 92`} fill="none" />
          <path d="M150 214 L84 224 L52 224" fill="none" />
        </g>
        <g fontFamily="ui-monospace, SFMono-Regular, Consolas, monospace" fontSize="10" fill={DIM}>
          <text x="424" y="86" textAnchor="end" fill={RED}>TIP · SHARP HIT</text>
          <text x="52" y="220" textAnchor="start">P1 · LUNGE</text>
          <text x="352" y="228" textAnchor="middle" fill={BLUE}>P2 · GUARD</text>
        </g>

        {/* the one measurement that is real: the turn budget */}
        <g stroke={DIM} strokeWidth="1" opacity="0.8">
          <line x1="150" y1="272" x2="352" y2="272" />
          <line x1="150" y1="266" x2="150" y2="278" />
          <line x1="352" y1="266" x2="352" y2="278" />
        </g>
        <rect x="216" y="263" width="72" height="17" fill="var(--bg-2-solid)" />
        <text x="252" y="276" textAnchor="middle" fontFamily="ui-monospace, SFMono-Regular, Consolas, monospace" fontSize="10.5" fill={DIM}>≤ 24 turns</text>
      </svg>
      <figcaption>
        <span>Fig. 1 — sword duel, tip distance</span>
        <span>Vote is blind: names reveal after</span>
      </figcaption>
    </figure>
  );
}
