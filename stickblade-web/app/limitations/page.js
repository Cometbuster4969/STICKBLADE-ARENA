"use client";
import DocPage, { Section, P, UL, KV, Code, Src } from "@/components/DocPage";

/**
 * /limitations — in decreasing order of severity, with what is being done
 * about each and what is not. Mirrors METHODOLOGY.md §7, plus the two that
 * matter most right now: the data is scripted, and the calibration has not
 * been run.
 */
const ITEMS = [
  ["1. The rankings rest on scripted baselines",
   "As of this writing no real-provider calibration batch has been run, so every leaderboard row is a scripted baseline or a pipeline test. The live banner on every ranking page says so and will change on its own once real matches land. Nothing on this site should be read as evidence about any language model until it does.",
   "Runner built and verified end to end (tools/run_calibration_batch.py). Blocked on provider keys on the backend."],
  ["2. Self-selected voter pool, one vote per match",
   "Visitors are not a calibrated panel and each match is voted on once, so there is no inter-rater agreement (κ). Vote noise is measurable through the bootstrap intervals; selection bias is not.",
   "Expert and casual tiers are fitted separately, never pooled. A multi-vote sample track is planned; not built."],
  ["3. Provider latency is part of the outcome",
   "A model that answers slowly falls back or times out and is penalised, independent of its tactical quality. Fast providers are therefore favoured.",
   "Latency, fallback and invalid-action rates are published beside every rating and per turn in the actions table. Strict policy excludes any fallen-back match from ranking. The effect is measured, not corrected."],
  ["4. LLM decisions are not seed-reproducible",
   "Only physics and scripted brains replay bit-for-bit. A published match is re-simulated from its stored action log, which reproduces the fight but not the model call.",
   "Provenance (model used, provider, tokens, latency) is stored per turn so the call is at least auditable."],
  ["5. Prompt version 2 is not comparable with version 1 bow cells",
   "The 2026-09-08 bump added movement hints for ranged play. It was additive, but v1 and v2 bow ratings measure slightly different questions.",
   "Every row carries prompt_version; fits are per version. The fingerprint changed with it (029281ed627a → 09de66effd02) and CI now asserts it per version."],
  ["6. Small, rotating free-tier roster",
   "The public roster leans on free OpenRouter and Groq tiers, which rotate and throttle. Coverage of frontier paid models is thin unless a visitor brings their own key.",
   "BYOK is supported per match; keys are never stored. The calibration design targets 4–6 models across ~3 providers, not the whole roster."],
  ["7. No adversarial layer",
   "There is no prompt-injection or jailbreak evaluation. Out of scope for a competitive-play rating; stated so it is not assumed.",
   "None planned."],
  ["8. Objective metrics are proxies",
   "Damage per turn, hit rate and the like are physics-derived and vote-independent, but they measure aggression as readily as skill. They are published beside ratings and never used to rank.",
   "Kept as a separate board with that caveat attached."],
];

export default function LimitationsPage() {
  return (
    <DocPage
      title="Limitations"
      current="/limitations"
      lead={<>
        What this benchmark cannot show, in decreasing order of severity, and
        what is being done about each. Source of record: <Src path="METHODOLOGY.md" /> §7
        and <Src path="research/reports/2026-09.md" />.
      </>}
    >
      {ITEMS.map(([h, what, doing]) => (
        <Section key={h} title={h}>
          <P>{what}</P>
          <KV rows={[["Mitigation", doing]]} />
        </Section>
      ))}
      <Section title="Language policy">
        <UL items={[
          "No leaderboard rank is shown without its sample size and interval.",
          "No pair of models is called different unless their 95 % intervals do not overlap; otherwise they share a tie letter and are “not separable”.",
          "Scripted baselines are labelled as such on every row, every export and every report, and are never presented as model results.",
          <>Every report names its dataset version, benchmark version, prompt version and spec fingerprint (<Code>tools/benchmark_report.py</Code> §0).</>,
          "“Infrastructure validated” and “model conclusions validated” are separate claims; today only the first is true.",
        ]} />
      </Section>
    </DocPage>
  );
}
