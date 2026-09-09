"use client";
import Link from "next/link";
import DocPage, { Section, P, UL, KV, Code, Src, GITHUB } from "@/components/DocPage";

/**
 * /research — the one page a researcher should be able to read in five
 * minutes and come away knowing exactly what this benchmark does and does
 * not show. It answers the seven questions from the September 2026 review,
 * in order, and links out to the page that goes deeper on each.
 *
 * The evidence strip at the top is live; the prose below never states a
 * number the strip could contradict.
 */
export default function ResearchPage() {
  return (
    <DocPage
      title="Research overview"
      current="/research"
      lead={<>
        STICKBLADE ARENA is a physics-grounded, pairwise-preference benchmark
        for language models: two models control ragdoll fencers in a
        deterministic 2-D simulation, humans watch blind and vote, and
        ratings with confidence intervals are fitted from those votes. This
        page answers the seven questions a reviewer asks first. Everything
        here is backed by a file in the{" "}
        <a href={GITHUB} target="_blank" rel="noreferrer"
           style={{ color: "var(--gold)" }}>public repository</a>.
      </>}
    >
      <Section id="q1" title="1. What is being measured">
        <P>
          <b style={{ color: "var(--text)" }}>Embodied tactical decision-making
          under a fixed physical ruleset</b>, judged by human preference. Each
          turn a model receives a structured state (positions, distances,
          HP, weapon zones, last events) and returns one action plus footwork
          (macro mode) or raw joint targets (joint mode). The physics engine
          resolves the turn; the model never sees or edits the outcome
          directly. The ranked signal is the <i>tactical</i> vote (“who fought
          smarter?”); execution and entertainment votes are collected
          separately and are <i>not</i> ranked.
        </P>
        <KV rows={[
          ["Unit of measurement", "One match: 4 / 12 / 24 turns (sprint / standard / full), two models, one weapon, one arena, one control mode."],
          ["Primary outcome", "Blind human tactical vote (a / b / draw) → Bradley–Terry rating with a Davidson tie term and bootstrap 95 % CI."],
          ["Secondary outcomes", "Engine winner + method, damage dealt, hit rate, invalid-action rate, decision latency, fallback rate, billed tokens."],
          ["Not measured", "Text quality, factuality, safety, coding, or anything outside the arena. See /limitations."],
        ]} />
      </Section>

      <Section id="q2" title="2. Why physics">
        <P>
          Because a physical ruleset cannot be memorised or negotiated with.
          Text benchmarks are contaminated by training data and graded by
          other models; here the grader is a rigid-body simulator and the
          rules are frozen in a versioned spec (
          <Src path="docs/BENCHMARK_SPEC.md" />) with a fingerprint stored on
          every match. Consequences of a decision are computed, not asserted:
          a “thrust” from 400 px away misses because the geometry says so.
          The same physics also makes every non-LLM part of a match
          reproducible from a seed, which is what turns a leaderboard into an
          auditable claim (see /reproducibility).
        </P>
      </Section>

      <Section id="q3" title="3. How models are compared">
        <UL items={[
          <>Matches are <b>blind</b>: fighters are “A” and “B”; the model
            identities are revealed only after the vote. Canvas sides are
            randomised per match (<Code>flip</Code>) so colour/side bias
            cancels; research batches pin sides to a balanced design instead.</>,
          <>Ratings are segmented per cell (weapon × arena × control mode ×
            sharp zone × blindfolded) so a model good with a bow on ice is not
            averaged with itself using a sword on grass.</>,
          <>Elo (K = 32) is shown as a live scoreboard. The scientific rating
            is <b>Bradley–Terry with Davidson ties</b>, refitted over all
            votes in a cell with ridge shrinkage and bootstrap intervals (
            <Src path="stickblade/ratings.py" />).</>,
          <>Every row also carries a <b>data-quality label</b> — scripted
            baseline / mixed-provider / real-provider — and a status
            (ranking-eligible / exploratory only / reference baseline), from{" "}
            <Src path="stickblade/data_quality.py" />.</>,
          <>Scripted baselines (<Code>bot:*</Code>, <Code>mock:*</Code>) exist to
            calibrate the pipeline and give a floor. They are labelled as such
            everywhere and are never presented as model results.</>,
        ]} />
      </Section>

      <Section id="q4" title="4. What counts as a significant result">
        <P>
          Two models are called different <b>only</b> when their 95 % bootstrap
          intervals do not overlap (the lower bound of one above the upper
          bound of the other). Models whose intervals overlap share a tie
          letter on the leaderboard and are described as <i>not separable</i>.
          No rank is shown without its sample size and interval. In addition,
          a model’s ranking is only <i>eligible</i> once it has at least 10
          real-provider, ranking-eligible matches in the cell, and a board is
          only treated as model evidence once it has 30 — below that every
          ranking is labelled exploratory and a banner says so.
        </P>
        <P>
          The current honest statement, from the latest generated report (
          <Src path="research/reports/2026-09.md" />): <b>0 of 1 pairs
          separable</b>, on scripted data. That is the pipeline working, not a
          model finding.
        </P>
      </Section>

      <Section id="q5" title="5. What data exists">
        <P>
          The live strip at the top of this page is the answer, straight from
          the database. Every finished match stores: benchmark, physics and
          prompt versions, spec fingerprint, seed, match length, fallback
          policy, both requested models, both models that actually answered,
          provider per side, per-turn latency, billed tokens and API calls,
          fallback and invalid-action counts, engine result, per-turn action
          log, and the replay. Votes store the four axes, confidence, and a
          self-declared voter tier — no IPs, no user ids. The dataset page
          documents every column: <Link href="/data" style={{ color: "var(--gold)" }}>/data</Link>.
        </P>
        <P>
          As of this writing no real-provider calibration batch has been run;
          the runner exists and is verified end to end on scripted fighters
          (<Src path="tools/run_calibration_batch.py" />,{" "}
          <Src path="research/calibration/README.md" />). When it runs, the
          strip above changes on its own.
        </P>
      </Section>

      <Section id="q6" title="6. Limitations">
        <UL items={[
          "Self-selected, uncalibrated voter pool; one vote per match, so no inter-rater agreement yet.",
          "Provider latency is part of the outcome: a slow strong model is penalised by timeouts. Latency, fallback and invalid-action rates are published so the effect is visible, not normalised away.",
          "LLM decisions are not reproducible from a seed; only physics and scripted brains are. Reproducibility is audited by replaying the stored action log.",
          "Prompt version 2 is not comparable with version 1 bow cells; filter by prompt_version.",
          "Everything above rests, today, on scripted-baseline data.",
        ]} />
        <P>Full list with severity ordering: <Link href="/limitations" style={{ color: "var(--gold)" }}>/limitations</Link>.</P>
      </Section>

      <Section id="q7" title="7. How to reproduce">
        <UL items={[
          <>Clone, install, run the 250-test suite offline (<Code>pytest tests</Code>); it includes seeded-replay determinism and the rating fitter’s interval behaviour.</>,
          <>Download a versioned release (or build one from a local database with <Code>tools/export_dataset.py build</Code>), then <Code>tools/export_dataset.py verify</Code> re-hashes every file and refits the ranking from the files alone.</>,
          <>Regenerate the monthly report from that release with <Code>tools/benchmark_report.py --export …/matches/matches.jsonl</Code>; §0 of the report names the dataset version and evidence level.</>,
          <>Re-run any seeded scripted match bit-for-bit with <Code>tools/run_match.py</Code>; re-run a whole calibration design with <Code>tools/run_calibration_batch.py</Code> (backend and offline runners produce identical rows).</>,
        ]} />
        <P>Step-by-step commands: <Link href="/reproducibility" style={{ color: "var(--gold)" }}>/reproducibility</Link>.</P>
      </Section>
    </DocPage>
  );
}
