# Contributing to STICKBLADE ARENA

Thanks for wanting to help. This is a solo-maintained research project, so the
goal of this document is to make a good first PR easy and a bad one
impossible.

**Read [AGENTS.md](./AGENTS.md) before you start.** It is written for AI
agents but applies to humans too: reading order, the citation rule, and the
anti-sycophancy protocol are all there.

---

## The three rules

1. **No claim without a `file:line` citation.** "I think there's no rate
   limit" is not a contribution. Grep first, then say `server.py:RL_MATCHES_PER_HOUR`.
2. **Never change the physics or the prompt without bumping a version.**
   `stickblade/benchmark.py` owns `BENCHMARK_VERSION` and `PHYSICS_VERSION`;
   `stickblade/brains.py` owns `PROMPT_VERSION`. Changing constants without a
   bump silently invalidates every published result and the spec fingerprint
   is the tripwire.
3. **Tests are not optional.** The suite runs in ~35 s with no network and no
   API key. If your change touches the engine, add or extend a test.

---

## Getting set up

```bash
# backend
cd stickblade
pip install -r requirements.txt
pip install pytest                     # not in requirements.txt on purpose
sudo apt-get install -y libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 \
                        libsdl2-ttf-2.0-0 libfreetype6   # pygame/pymunk

# frontend
cd ../stickblade-web && npm install
```

Run everything:

```bash
python3 -m pytest tests -q                 # 193 cases, headless, offline
cd stickblade-web && npm run build         # must pass before any frontend PR
./tools/run_match.py verify stickblade-web/public/demo_replay.json
```

The suite is headless because CI has no display: `tests/conftest.py` sets
`SDL_VIDEODRIVER=dummy` and relaxes the production rate limits so rapid-fire
API tests don't hit `503 arena is busy`.

---

## Where things live

| Area | Files |
|---|---|
| Frozen spec + provenance + replay audit | `stickblade/benchmark.py` |
| Replay forensics / exploit detection | `stickblade/anti_gaming.py` |
| Physics, weapons, damage | `config.py`, `weapons.py`, `combat.py`, `moves.py`, `ragdoll.py` |
| Match loop, telemetry, action log | `main.py`, `recorder.py` |
| Model adapters, prompting, retry ladder | `brains.py`, `joint_mode.py`, `bots.py` |
| Elo, storage, migrations | `storage.py`, `storage_supabase.py`, `supabase_schema.sql` |
| Ratings with uncertainty (Bradley–Terry) | `stickblade/ratings.py` |
| Recurring events + champions | `stickblade/events.py` |
| Cost accounting + access model | `stickblade/costs.py` |
| State-representation ablations | `stickblade/ablations.py`, `tools/run_ablation.py` |
| HTTP API | `server.py` |
| Offline research CLIs | `tools/` (`run_match.py` is the entry point) |
| Frontend | `stickblade-web/app`, `stickblade-web/components` |

---

## What a good PR looks like

- **One concern per PR.** A physics tweak and a CSS refactor do not belong together.
- **Explain the measurement, not the vibe.** If you claim an improvement,
  include the command a reviewer can run and the numbers it produced.
- **New columns need a migration.** Schema changes go in
  `stickblade/supabase_schema.sql` as an idempotent
  `alter table … add column if not exists` block, *and* in the SQLite
  migration path in `storage.py`.
- **Don't weaken the blind election.** Model names must never appear in
  `/api/match`, the live match payload, or a pre-vote replay. Tests in
  `tests/test_blind_identity.py` enforce this.
- **Don't log API keys.** `tests/test_byok.py` asserts a BYOK key never
  reaches the response, the DB, the replay JSON, the battle log, stdout, or
  any export endpoint. `server._safe_err()` exists to scrub provider errors.
- **Frontend**: keep accessibility attributes (`role`, `aria-*`, focus rings)
  and respect the `data-motion` / `data-contrast` / `data-fx` attributes on
  `<html>` — they are the reduced-motion and high-contrast modes.

---

## Adding a model to the roster

1. Add it to `config.ARENA_MODELS` with a display name.
2. Add a `_reasoning_policy` entry — CI has a `roster-consistency` job that
   fails if any OpenRouter model lacks one.
3. If it is Groq-hosted, prefix the id with `groq:` and make sure it is in
   `_PROVIDER_HOST`.
4. Free-tier only unless there is a budget conversation first.

---

## Good first issues (§32)

Anything labelled **`good first issue`** is scoped so that a newcomer can
finish it in an afternoon without touching the frozen spec. The areas the
project most wants help with, in rough order of usefulness:

| Area | Example starter task |
|---|---|
| **New weapon** | Add a weapon to `weapons.py` + its `WEAPON_GEO` entry in `stickblade-web/public/player.js`, then run `tools/weapon_balance.py` and publish the mirrored-bot win rate |
| **New arena** | Add an arena modifier to `config.py` and pass `tools/run_match.py spec` — the spec fingerprint must change deliberately, not accidentally |
| **Replay visualisation** | The debug overlay (`drawDebug()` in `public/player.js`) is the place to add per-frame instrumentation |
| **Bot adapter** | Add a scripted baseline to `bots.py` — these are the control group for every claim about LLM skill |
| **Dataset analysis** | `/api/export?fmt=jsonl` is public and CC-BY-SA 4.0; analysis of it is citable work that needs no API key |
| **Accessibility** | Keyboard/screen-reader gaps in `stickblade-web`; respect `data-motion` / `data-contrast` / `data-fx` |
| **Documentation** | Anything in `docs/` that is stale is a bug |
| **Test coverage** | `stickblade/` has thin spots; tests need no credentials |

### Labels

| Label | Means |
|---|---|
| `good first issue` | Scoped for a newcomer |
| `help wanted` | Maintainer actively wants this |
| `research` | Methodology, evaluation design, statistics |
| `frontend` / `backend` / `physics` | Which layer |
| `security` | Security or privacy |
| `data quality` | Dataset, export, or vote-quality problem |
| `benchmark spec` | **Frozen specification change — needs a version bump** (see rule 2 above) |

Anything touching `benchmark spec` needs a conversation before code: a
version bump invalidates comparability with every result recorded so far,
which is a real cost and never a drive-by change.

---

## Reporting a bug

Open an issue with: what you did, what you expected, what happened, and the
match id if there is one (`/api/integrity/{match_id}` output is ideal).
Security issues: see [SECURITY.md](./SECURITY.md) — please don't open a public
issue for those.

---

## Code style

- Python: 4 spaces, 88-ish columns, comments that explain *why*. The codebase
  is heavily commented on purpose — the "why" is the part that rots.
- JS/JSX: function components, hooks at the top, no default-exported
  anonymous components.
- Every new module-level constant that affects a match outcome belongs in the
  spec document (`benchmark.spec()`), not just in `config.py`.

## Licence of your contribution

By opening a PR you agree that your contribution is licensed under the
repository's Apache-2.0 licence, and that any match data it produces is
licensed CC-BY-SA 4.0.
