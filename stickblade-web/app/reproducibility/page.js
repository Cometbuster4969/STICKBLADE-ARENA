"use client";
import DocPage, { Section, P, UL, KV, Code, Src, Pre } from "@/components/DocPage";

/**
 * /reproducibility — the exact commands. Each block is something that was
 * actually run in the repository, with what it should print.
 */
export default function ReproducibilityPage() {
  return (
    <DocPage
      title="Reproducibility"
      current="/reproducibility"
      lead={<>
        What can be re-run, what cannot, and the commands for each. Nothing
        below needs an API key, a database or a deployed server except where
        it says so.
      </>}
      evidence={false}
    >
      <Section title="What is and is not reproducible">
        <KV rows={[
          ["Physics + scripted brains", <>Bit-for-bit from a seed. Pinned by <Code>tests/test_replay_determinism.py</Code>, including the case where the server asks for pre-fight quips first (a 2026-09-09 fix — quips used to advance the decision RNG).</>],
          ["LLM decisions", "Not reproducible from a seed (providers are non-deterministic). Every decision is stored in the action log, so a published match is re-simulated from the log, not by re-calling the provider."],
          ["Ratings", <><Code>tools/export_dataset.py verify</Code> refits Bradley–Terry from a release’s <Code>matches</Code> + <Code>votes</Code> and compares point estimates with the manifest. Tampering with one vote fails it (tested).</>],
          ["Spec", <>The fingerprint is recomputed from code on every CI run and asserted per prompt version (<Src path=".github/workflows/ci.yml" />).</>],
        ]} />
      </Section>

      <Section title="0. Set up (offline, ~1 minute)">
        <Pre>{`git clone https://github.com/Cometbuster4969/STICKBLADE-ARENA
cd STICKBLADE-ARENA
pip install -r stickblade/requirements.txt pytest
export SDL_VIDEODRIVER=dummy          # headless pygame
python3 -m pytest tests -q            # expect: 25x passed`}</Pre>
      </Section>

      <Section title="1. Re-run a seeded match bit-for-bit">
        <Pre>{`./tools/run_match.py simulate --a bot:pro --b mock:duelist --seed 20260909 \\
    --weapon bow --arena ice --length sprint --fallback-policy strict --out /tmp/m.json
./tools/run_match.py verify /tmp/m.json        # replay integrity audit
python3 stickblade/benchmark.py --fingerprint  # 09de66effd02 under prompt v2`}</Pre>
        <P>Run it twice; the frames and action log are identical.</P>
      </Section>

      <Section title="2. Re-run the calibration design">
        <Pre>{`# offline dry run (scripted fighters, ~10 s) — the committed one is research/calibration/dry-run/
python3 tools/run_calibration_batch.py run --local \\
    --models bot:pro,mock:duelist,bot:greedy,bot:distance --n 16 --length sprint \\
    --out-dir /tmp/cal --run-id cal-dryrun-2026-09-09
# expect audit: 5 ✅, 1 ❌ (real_provider_evidence_present) → NOT ACCEPTED

# same plan through a running backend lands identical rows (verified 24/24)
python3 tools/run_calibration_batch.py run --backend http://localhost:8000 \\
    --plan /tmp/cal/plan.json --out-dir /tmp/cal_backend`}</Pre>
      </Section>

      <Section title="3. Rebuild and verify a dataset release">
        <Pre>{`python3 tools/export_dataset.py build --backend https://pioneer37-stickman-arena.hf.space \\
    --out-dir research/exports --version v2026.09.09 --replays 500
python3 tools/export_dataset.py verify research/exports/v2026.09.09
# expect: hashes OK · row counts match · ratings refit point estimates match · RESULT: VERIFIED`}</Pre>
      </Section>

      <Section title="4. Regenerate the report">
        <Pre>{`python3 tools/benchmark_report.py --export research/exports/v2026.09.09/matches/matches.jsonl \\
    --out /tmp/report.md
# §0 of the report names dataset version, benchmark/prompt versions, fingerprint and evidence level`}</Pre>
      </Section>

      <Section title="5. Recompute the leaderboard from the API">
        <Pre>{`curl -s "$API/api/leaderboard/bradley_terry?weapon=sword&mode=macro&bootstraps=500" | jq '.rows[] | {model, rating, ci_low, ci_high, matches, data_quality}'
curl -s "$API/api/data_quality" | jq .summary`}</Pre>
        <P>
          Every row carries <Code>matches</Code>, <Code>ci_low</Code>/<Code>ci_high</Code> and a{" "}
          <Code>data_quality</Code> block. No rank is shown without them.
        </P>
      </Section>

      <Section title="Where the constants live">
        <UL items={[
          <><Src path="stickblade/benchmark.py" /> — versions, spec, fingerprint, <Code>verify_replay()</Code></>,
          <><Src path="stickblade/ratings.py" /> — Bradley–Terry / Davidson, bootstrap, vote → pair mapping</>,
          <><Src path="stickblade/data_quality.py" /> — evidence classes, eligibility thresholds (10 per model, 30 per board)</>,
          <><Src path="stickblade/brains.py" line={46} /> — <Code>PROMPT_VERSION</Code>; ledger in <Src path="AGENTS.md" /> §10.5</>,
          <><Src path="tools/simcore.py" /> — the headless match loop every tool shares</>,
        ]} />
      </Section>
    </DocPage>
  );
}
