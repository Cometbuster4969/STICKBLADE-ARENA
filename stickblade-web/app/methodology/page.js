"use client";
import DocPage, { Section, P, UL, KV, Code, Src, Pre } from "@/components/DocPage";

/**
 * /methodology — the match loop, the rating model, the eligibility rules
 * and the versioning protocol, condensed from METHODOLOGY.md with file
 * pointers. If this page and METHODOLOGY.md ever disagree, the markdown
 * file in the repository is authoritative.
 */
export default function MethodologyPage() {
  return (
    <DocPage
      title="Methodology"
      current="/methodology"
      lead={<>
        Condensed from <Src path="METHODOLOGY.md" /> (authoritative) and the
        frozen ruleset in <Src path="docs/BENCHMARK_SPEC.md" />. Numbers here
        are constants from the code, cited by file.
      </>}
      evidence={false}
    >
      <Section title="The match loop">
        <KV rows={[
          ["World", <>2-D rigid-body arena (pymunk). Two ragdoll fencers spawn facing each other at equal distance from the centre line; arena variants <Code>normal</Code> / <Code>ice</Code> (low friction) / <Code>low_gravity</Code> (0.35 g). <Src path="stickblade/benchmark.py" /> <Code>physics_spec()</Code>.</>],
          ["Turn", <>Both models receive the state simultaneously and answer in parallel threads (scripted-vs-scripted resolves inline for determinism, <Src path="stickblade/main.py" line={238} />). The engine then simulates <Code>TURN_SECONDS</Code> of physics with both actions applied.</>],
          ["State (macro)", <>Positions, facing, distance, HP, weapon and sharp zones, last events, plus a <Code>ranged_hint</Code> block for bows. <Code>blindfolded</Code> strips the derived spatial hints. Schema versioned as <Code>PROMPT_VERSION</Code> (<Src path="stickblade/brains.py" line={46} />).</>],
          ["Action (macro)", <>One action from the weapon’s vocabulary (thrust, guard, draw_shot, …) + one footwork (advance, retreat, lunge, hop_back, hold). Invalid replies are sanitised to a safe default and counted (<Code>invalid_actions_*</Code>).</>],
          ["Action (joint)", <>Ten joint targets per turn (shoulder/elbow/grip/hips/knees…), optional <Code>fire</Code>. Deliberately harder; ranked in its own cell.</>],
          ["Result", <><Code>kill</Code> (HP ≤ 0), <Code>points</Code> (higher HP at the turn cap), <Code>timeout_draw</Code>, <Code>mutual_destruction</Code>. <Src path="stickblade/main.py" line={520} />.</>],
          ["Lengths", <>sprint 4 · standard 12 · full 24 turns. Ratings are not mixed across lengths in research batches.</>],
        ]} />
      </Section>

      <Section title="Latency, fallback and eligibility">
        <P>
          A model that does not answer in time still has to do <i>something</i>,
          or the match stalls for everyone. The failure ladder is: retry the
          same model with a longer timeout → a “buddy” model of similar tier →
          the scripted mock (<Src path="stickblade/brains.py" line={1027} />).
          Every step is recorded per turn: <Code>model_used</Code>,{" "}
          <Code>provider_used</Code>, <Code>fallback</Code>. What that does to
          the ranking depends on the <b>fallback policy</b> chosen at match
          creation:
        </P>
        <KV rows={[
          ["strict", "Any fallback turn makes the match ranking-ineligible. Used for all research batches. A strict match that fell back is still stored, labelled `excluded`, and counted in the audit."],
          ["operational", "Default for the public arena. Fallback continues, is recorded and is shown on the result card; the match remains eligible."],
          ["demo", "Never ranked."],
        ]} />
        <P>
          <b>Silent fallback</b> — a fallback turn in a strict match that is
          still marked eligible — is a defined defect, counted on
          <Code> /api/data_quality</Code> (<Code>silent_fallback_matches</Code>)
          and asserted to be zero by the calibration audit.
        </P>
      </Section>

      <Section title="Blind voting">
        <UL items={[
          <>Fighters are renamed “Fighter A / B” in the replay itself; the reveal happens after the vote (<Src path="stickblade/server.py" /> <Code>/api/vote</Code>).</>,
          <>Canvas side is a coin flip per match (<Code>flip</Code>); votes are cast on canvas sides and mapped back to models with the same function Elo and Bradley–Terry both use (<Src path="stickblade/ratings.py" line={342} /> <Code>preference_pairs_from_votes</Code>).</>,
          <>Four axes: <b>tactical</b> (ranked), execution, entertainment, deserved; plus 1–5 confidence and a self-declared voter tier (casual / expert). Expert and casual boards are fitted separately and never pooled.</>,
          <>Anti-gaming: one vote per match, rate limits per IP, blind names in the replay, and integrity checks on every replay (<Code>/api/integrity/{"{id}"}</Code>).</>,
        ]} />
      </Section>

      <Section title="Ratings">
        <KV rows={[
          ["Elo (scoreboard)", <>K = 32, start 1000, six-key cell (model × sharp × weapon × mode × arena × blindfolded). Wilson 95 % CI on win rate. Order-dependent by construction, so it is not the scientific claim. <Src path="stickblade/storage.py" line={14} />.</>],
          ["Bradley–Terry (claim)", <>Maximum-likelihood fit over all votes in a cell with a Davidson tie parameter ν (estimated, forced to 0 with no draws), ridge shrinkage 1.0 so a 3–0 record stays finite, ratings centred per connected component, anything outside the main component flagged provisional. Reported on an Elo-like scale <Code>1000 + (400/ln10)·θ</Code> for readability only. <Src path="stickblade/ratings.py" line={69} />.</>],
          ["Uncertainty", <>Bootstrap over the comparison set (default 200 resamples), 2.5 / 97.5 percentiles. Intervals must widen as n falls — pinned by <Code>tests/test_ratings.py::test_more_data_gives_a_tighter_interval</Code>.</>],
          ["Separability", "Two models differ only when the intervals do not overlap. Otherwise they share a tie letter and are described as not separable."],
          ["Objective board", "Physics-derived and vote-independent: damage per turn, hit rate, lethal rate, survival, timeout, invalid-action, fallback rate, latency. Published beside the ratings, never used to rank."],
        ]} />
      </Section>

      <Section title="Data-quality labels">
        <P>
          Every ranking row and every export row is classified by <i>who
          actually decided</i>, not who was asked (<Src path="stickblade/data_quality.py" />):
        </P>
        <KV rows={[
          ["real_provider", "Both sides answered by a real provider (OpenRouter, Groq, OpenAI, Google, …)."],
          ["mixed_provider", "One side real, one side scripted or fallen back to scripted."],
          ["scripted_baseline", "Both sides scripted (bot:*, mock:*). Pipeline calibration; not a model result."],
          ["Model status", <><Code>ranking_eligible</Code> needs ≥ 10 real + ranking-eligible matches in the cell; below that <Code>exploratory_only</Code>; scripted models are <Code>reference_baseline</Code>. Board level: <Code>real</Code> needs ≥ 30 real ranked matches, else <Code>insufficient_real</Code> or <Code>scripted_only</Code>.</>],
        ]} />
      </Section>

      <Section title="Versioning protocol">
        <KV rows={[
          ["BENCHMARK_VERSION", "1.0 — the ruleset. Bumping invalidates comparability."],
          ["PHYSICS_VERSION", "1.0 — timestep, gravity, damping, damage model. Any change bumps it."],
          ["PROMPT_VERSION", <>2 — state schema + system prompt. v1 → v2 on 2026-09-08 was additive (bow mobility hints), a soft cutover: v1 ratings stay readable, v1 and v2 bow cells are not averaged. Ledger in <Src path="AGENTS.md" /> §10.5.</>],
          ["Spec fingerprint", <>SHA-256 over the outcome-affecting parts of the spec, including the prompt version: <Code>09de66effd02</Code> under prompt v2, <Code>029281ed627a</Code> under prompt v1. CI asserts the fingerprint per prompt version.</>],
        ]} />
        <Pre>{`python3 stickblade/benchmark.py --fingerprint   # prints the current fingerprint
curl -s $API/api/benchmark/spec | jq .          # the full frozen ruleset`}</Pre>
      </Section>

      <Section title="Calibration design (real-provider batch)">
        <P>
          The first real-provider run is a calibration of the pipeline, not a
          tournament. <Src path="tools/run_calibration_batch.py" /> builds a
          balanced plan: every unordered pair of 4–6 models × 2 weapons × 2
          arenas × 2 control modes, N matches per pair (20–30 for a powered
          pair), canvas sides alternated per cell so each model plays left and
          right equally, seed = base + index, strict policy, standard length.
          The run ends with an acceptance audit: 100 % provider + model
          identified, 100 % eligibility recorded, zero silent fallback, ≥ 95 %
          token coverage or the gap reported, failed matches retained but not
          ranked, and real-provider evidence present. A scripted dry run fails
          exactly the last check — by construction.
        </P>
      </Section>
    </DocPage>
  );
}
