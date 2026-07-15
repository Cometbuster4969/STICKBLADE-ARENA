# AGENTS.md — Working on STICKBLADE ARENA

> Instructions for any AI agent (Claude, Codex, Cursor, Copilot, etc.) opening
> a session on this repo. Read this before touching code.

**Project:** STICKBLADE ARENA — a physics-based LLM benchmark where two
language models sword-fight in a 2D arena, and users vote blind on who
fought smarter. Built by [@Cometbuster4969](https://github.com/Cometbuster4969)
(Ayush Kumar) as a solo project.

**Live surfaces:**
- Frontend: https://stickblade-arena.vercel.app
- Backend:  https://pioneer37-stickman-arena.hf.space
- Repo:     https://github.com/Cometbuster4969/STICKBLADE-ARENA
- Space:    https://huggingface.co/spaces/Pioneer37/Stickman-Arena

---

## 0. Read this first — the #1 rule

**Before making any claim about the state of the code, run `git log --oneline -10`
and confirm the tip commit hash.** Multiple past audits have flagged bugs as
"still open" that had shipped hours earlier. If you're not looking at the same
tree as `origin/main`, everything downstream is fiction.

When claiming "line X is unchanged" or "file Y still has bug Z" — quote the
actual current line content. If you can't, don't make the claim.

---

## 0.5. Anti-sycophancy protocol — NON-NEGOTIABLE

Two separate audit sessions (Jul 13 2026) failed the same way: two LLMs
ping-ponged grades without either re-grepping the code. Each one caved
to the other's pushback instead of holding a defensible flag. The user
called it "gaslighting" and was right. This section exists so it never
happens again.

**Rules for any code audit, security review, or grade you produce on this repo:**

1. **No claim without a `file:line` citation.** If you can't cite
   `stickblade/security.py:66` or `next.config.mjs:46`, don't make the
   claim. "I think there's no rate limit" is not allowed. Grep first.

2. **Run this checklist before any grade:**
   ```bash
   git log --oneline -10                              # tip commit
   grep -rn "RL_\|MAX_\|rate_limit\|check_match_allowed" stickblade/
   grep -rn "TODO\|FIXME\|console\.log" stickblade/ stickblade-web/app stickblade-web/lib
   grep -n "Content-Security-Policy\|frame-ancestors\|HSTS" stickblade-web/next.config.mjs
   grep -n "apply_elo_vote\|ON CONFLICT\|FOR UPDATE" stickblade/storage_supabase.py
   bandit -r stickblade/ --skip B101,B404,B608 --severity-level medium --confidence-level medium
   ```
   Every "missing" claim must survive this checklist. If it doesn't,
   delete the claim, don't hedge it.

3. **Never move a grade based on another LLM's pushback alone.**
   If another agent (or the user relaying one) says "you're too generous"
   or "you're too harsh" — that's an input, not evidence. Re-run the
   checklist. If the facts you cited are still true, hold the grade
   and defend it with citations. If the facts are wrong, name the
   specific fact that was wrong and only move the grade for that fact.
   "Vibes moves" of ±0.3 across the board are the sycophancy tell.

4. **Publish the audit's inputs, not just its outputs.**
   Every grade must be accompanied by:
     - the commit SHA it's grading (from `git log`)
     - the file:line evidence for each dimension
     - a "what would move this grade" list (concrete, e.g. "add
       pip-audit to CI → security +0.3")
   No SHA + no citations = the grade is invalid, refuse to give one.

5. **Grade inflation forensics.** If your first draft came out
   "impressive prototype, top 5% of solo work" — stop, re-read for
   emotional adjectives, delete them, re-grade against a public
   product bar (would this pass a code review at a company that
   ships LLM eval tools? — not "is this good for a 19yo indie?").
   The user explicitly does not want the indie-encouragement grade.
   They want the honest-peer-reviewer grade.

6. **Grade deflation forensics.** If your draft came out harsh
   because the previous LLM was too generous — stop, that's reactive
   grading. Re-anchor to the checklist in rule 2. Harshness that
   isn't backed by a specific failed grep is just contrarianism.

7. **When in disagreement with another audit, produce a diff table:**
   | Claim | Other audit said | You say | Grep result | Winner |
   Fill it in with actual grep output. Whoever's facts hold up wins
   that row. Grade = sum of rows, not vibes.

**Anchor grades (established Jul 13 2026, commit `0abd354`, verified via
the checklist above):**
  - Codebase: **8.4 / 10** — modular, 0 TODO/console.log, `config.py`
    centralizes magic numbers, real error handling. Held back by:
    `brains.py` 1296L (coherent but fat), no pytest suite, no type
    hints, no ruff/mypy gate.
  - Security: **8.7 / 10** — `RL_MATCHES_PER_HOUR=50/IP`,
    `MAX_MATCHES_PER_DAY=300` global, `MAX_QUEUE=10`, `TRUST_XFF` opt-in
    with docstring, CSP+HSTS+COOP+Permissions-Policy lockdown, atomic
    `apply_elo_vote` RPC on Supabase path, `_validate_id` regex guard,
    full-history secret scan in CI, BYOK zero-log with `_KEY_LEAK_RE`
    scrubber. Held back by: no dependabot / pip-audit, no CAPTCHA
    (IP rotation possible), no per-API-key rate limit.
  - Research-readiness: **5.5 / 10** — blind eval, Elo, replays, 29
    models real. Missing: dataset dump w/ DOI, N-per-model surfaced,
    confidence intervals, inter-rater agreement, calibration set,
    prompt versioning, correlation vs MMLU/GPQA. ~3 focused weekends
    to reach 7.5.

If you produce a materially different grade, you must show which
specific line-cited fact from above is now wrong. Otherwise the
anchor holds.

---

## 1. How the user works with agents

### Communication style — mandatory

- **Be honest, not sycophantic.** Skip "Absolutely!", "Great question!",
  "You're right to ask!". Get to the point.
- **Push back when the user is wrong.** They explicitly want this. Silent
  agreement wastes both of your time.
- **The user is open to being wrong too.** This is a two-way street. When
  they push back on your suggestion, they might be right — but they might
  also be missing something you know. Don't cave immediately. If you have
  evidence or reasoning for your position, state it and let them decide.
  A well-argued disagreement is welcome; a reflexive "you're right, sorry"
  is not.
- **Concede when something is actually a problem.** Don't dig in on bad
  positions to avoid embarrassment. If you were wrong, say so plainly
  and move on. Don't over-apologize.
- **Tone:** confident-builder-friend, 19yo solo-indie energy — confident +
  funny + lightly cocky, never desperate or corporate. Match their energy.
- **No hedging soup.** "It might be possible that perhaps you could consider"
  → "Do X." Give recommendations, not menus.

### When asked "what to reply to this DM/comment/reddit post"

Give **3 ranked drafts** with:
- Your recommended pick clearly marked (🥇/🥈/🥉 or explicit)
- Why that one, in one sentence
- Character count if the platform has a limit
- **A "what NOT to do" note** if the situation has obvious wrong moves

### When giving grades / assessments

**Honest grades only, not inflated.** If something is a B, call it a B.
Acknowledge limitations openly. The user values self-aware over polished.

### When there's ambiguity

Use the `ask_user` tool (if available) with 2-4 concrete options plus a free-text
escape hatch. Don't waffle for a paragraph then pick one anyway.

---

## 2. Repo layout

```
STICKBLADE-ARENA/
├── stickblade/                    # Python backend (FastAPI + pymunk)
│   ├── server.py                  # REST endpoints, worker loops, LIVE_STATE
│   ├── main.py                    # Match class: 24-turn fight orchestration
│   ├── brains.py                  # Brain hierarchy: Mock, OpenRouter, Groq
│   ├── joint_mode.py              # Raw per-joint control mode
│   ├── weapons.py                 # sword/dagger/spear/flail/bow builders
│   ├── ragdoll.py                 # pymunk Fighter (16 limbs, 10 joints)
│   ├── combat.py                  # zone classifier, damage model
│   ├── moves.py                   # macro action keyframe library
│   ├── recorder.py                # replay JSON capture
│   ├── storage.py                 # LocalStorage (SQLite)
│   ├── storage_supabase.py        # SupabaseStorage (Postgres+bucket)
│   ├── security.py                # rate limits + spend caps + client_ip
│   ├── config.py                  # ARENA_MODELS roster, env vars, constants
│   └── supabase_schema.sql        # DDL + apply_elo_vote RPC
│
├── stickblade-web/                # Next.js 15 frontend
│   ├── app/
│   │   ├── page.js                # main fight page (setup + replay + vote)
│   │   ├── layout.js              # <head> metadata, footer
│   │   ├── replay/page.js         # standalone /replay?id=… viewer
│   │   ├── leaderboard/page.js    # per-weapon/zone Elo boards
│   │   ├── history/page.js        # recent duels list
│   │   ├── tournament/page.js     # bracket creator + live viewer
│   │   └── globals.css            # theme vars (--gold, --green, --red-2, etc.)
│   ├── components/
│   │   ├── WaitPanel.js           # live combat ticker + H2H + queue pos
│   │   ├── ByokPanel.js           # BYOK key paste UI
│   │   ├── OnboardingCard.js      # first-visit welcome, / route only
│   │   ├── ShareButton.js         # copy-to-clipboard w/ ✓ feedback
│   │   ├── LeaderboardTable.js    # medals + trend arrow + compact prop
│   │   ├── ModelPicker.js         # neutral Slot 1/2 model dropdowns
│   │   └── ReplayPlayer.js        # React wrapper around vanilla player.js
│   ├── lib/
│   │   ├── api.js                 # fetch client + startKeepalive()
│   │   ├── byok.js                # localStorage helpers for BYOK
│   │   └── models.js              # displayName() fallback map
│   └── public/
│       └── player.js              # canvas replay engine (SINGLE SOURCE)
│
├── .github/FUNDING.yml            # GitHub Sponsors config
├── AGENTS.md                      # this file
├── README.md                      # public-facing docs + HF frontmatter
├── Dockerfile                     # HF Space container
└── LICENSE                        # MIT
```

**Notable:** `stickblade-web/public/player.js` is the ONE canonical copy of
the canvas player. `stickblade/server.py`'s `/static/player.js` route and
`recorder.py`'s HTML-export bake both resolve to it. The old
`stickblade/player.js` was deleted in `b5e4a2c` to kill drift.

---

## 3. Deploy pipeline (critical)

**Two remotes, two deploy targets:**

| Remote        | Auto-deploys to | Purpose                          |
|---------------|-----------------|----------------------------------|
| `origin`      | Vercel          | Frontend (Next.js)               |
| `huggingface` | HF Spaces       | Backend (FastAPI + pymunk)       |

**Push flow (user does this from their laptop, NEVER from workspace):**

```bash
cd "C:\Users\ayush\projects\helloworld\top secret\Stickman-Arena"
git pull origin main
git push origin main         # → Vercel picks up frontend changes
git push huggingface main    # → HF rebuilds backend Docker container
```

**Which remote needs which push:**
- Frontend-only change → `origin` only (Vercel deploys ~2 min)
- Backend-only change → `huggingface` only (HF rebuild ~2-3 min)
- Both changed → both remotes

**⚠ NEVER `git push` from this workspace.** No credentials are configured
here and the user does deployments from their laptop for security reasons.
Only `git commit` in the workspace; instruct the user on what to push.

---

## 4. Coding conventions

### Commit messages — long form, no exceptions

The user's stated preference: **"commits with detailed messages explaining
what + why."** Structure:

```
<type>(<scope>): <one-line summary in imperative mood>

<paragraph explaining WHY this change exists — the bug, the requirement,
the observation that triggered it. Cite specific evidence: line numbers,
log signatures, curl outputs, %% fallback rates.>

<paragraph explaining WHAT the change does, in plain terms. If it's a
non-obvious fix, walk through the mechanism.>

<Optional: "Verified" section listing what was tested and how, especially
for anything touching physics/LLM/security. Include actual numbers where
possible ("22/24 turns had real LLM output, was 0/24 before").>
```

Escape literal `%` inside commit messages as `%%` (git-notes quirk).

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.
**Scopes commonly used:** `brains`, `server`, `ui`, `groq`, `leaderboard`,
`replay`, `security`, `storage`.

### Python (backend)

- Python 3.13, type hints where they aid clarity (not enforced everywhere)
- FastAPI for HTTP, `httpx` for outbound calls (no `requests`)
- All path params validated by `_validate_id()` (regex `^[a-f0-9]{12}$`)
- All error messages sent to users pass through `_safe_err()` — scrubs
  URLs, bearer tokens, `sk-*` keys, filesystem paths
- Env vars default to empty string, never a real value:
  `OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")`
- Never `print()` API keys, match IDs are OK
- Any brain error surfaced to `/api/debug/brain_errors` goes through
  `_log_brain_err()` which also scrubs `sk-*` patterns
- Long docstrings explain WHY, not what (the code is the what)

### JavaScript (frontend, Next.js 15 App Router)

- `"use client"` on any file using hooks/state
- All new components go in `stickblade-web/components/`
- Prefer inline styles + CSS variables from `globals.css` (`var(--gold)`,
  `var(--green)`, `var(--red-2)`, `var(--dim)`, `var(--text)`, `var(--line)`,
  `var(--bg-2)`) over new class definitions
- No new npm packages without explicit user approval
- All URLs auto-linkify in copy — don't use Markdown `[text](url)` in
  strings meant for LinkedIn/Reddit output (they render literally)
- BYOK keys stay in `localStorage` only, only ever passed via
  `POST /api/match` body — never GET params, never headers set by frontend
- Model IDs display via `names[id]` from server responses; use
  `lib/models.js#displayName(id)` as a last-line fallback for unrecognized ids

### UI craft — the standard

The frontend is not an afterthought. It's a first-class part of what
this project is. Apply the same standard to it that the physics code
gets:

- **If a prop is passed, it should do something.** `<LeaderboardTable
  rows={lb} compact />` shouldn't silently ignore `compact`. Either
  implement the prop or delete it from the call site — never leave
  half-wired.
- **Interactive elements should have interactive feedback.**
  `<ShareButton>` shows "✓ Copied!" for 2s on click. Vote buttons
  disable during submission. The pulsing gold border on the
  currently-running bracket match is not decorative — it answers
  "which match right now?" at a glance. Feedback is functional, not
  optional.
- **Blindness contracts are sacred.** Anywhere a Fighter A/B identity
  might be revealed early (replay JSON, LIVE_STATE, ticker log, quips
  payload) — audit before shipping. The whole benchmark rests on the
  blind-vote guarantee. `canvas_a_model` vs `model_a` bug wasted
  ~50% of shared replay links for weeks; don't reintroduce it.
- **Preserve motion / animation intent.** The killcam letterbox bars,
  the arena-badge glow, the ticker's per-turn scroll — these were
  designed for feel. Don't strip them for "performance" without
  actually measuring first.
- **Consistency across surfaces.** OpenGraph title = Twitter title =
  `<title>` tag. Card border-radius matches across ByokPanel,
  OnboardingCard, commentator quote card (all gold-bordered, all
  ~8px radius). Every "sponsor / share / play" CTA uses the same
  visual weight. Break these deliberately, not accidentally.
- **Hydration matters.** Any component that reads `localStorage` must
  start with the SSR-safe state (usually `false` / `null`) and
  reveal in `useEffect`. `OnboardingCard` and `ByokPanel` both follow
  this pattern — do the same in new components. A flash of the wrong
  state on first paint is a real regression.
- **Copy is UX.** "Use your own OpenRouter key" not "Use my own
  OpenRouter key" — first-person leaks from AI-drafted copy are the
  cheapest tell that a component wasn't reviewed. Read every string
  aloud before shipping.
- **When adding a new visible element**, ask: does this earn its
  place, or is it filler? The main page has ~10 states (setup, busy,
  wait-panel, replay, predict, vote, reveal, commentary, share).
  Every one of them is intentional. Don't add an 11th unless it
  materially changes what the user is doing.

### Prompt/copy conventions

- **Second person, not first.** "Use your own OpenRouter key", not "Use my
  own OpenRouter key." The site is addressing the user.
- **"benchmark" is the primary positioning word.** Not "game", not "toy",
  not "sandbox". This word came from pymunk's showcase + Google's AI Overview
  and is now the alignment story across all surfaces.

---

## 5. Testing / verification workflow

The project has thin unit tests. The real testing strategy is:

### 1. Compile / syntax check (always)

```bash
python3 -c "import py_compile
for f in ['stickblade/server.py','stickblade/brains.py',...]:
    py_compile.compile(f, doraise=True); print('OK', f)"
```

For JSX files:
```bash
python3 -c "
src = open('stickblade-web/app/page.js').read()
assert src.count('{') == src.count('}'), 'brace mismatch'
assert src.count('(') == src.count(')'), 'paren mismatch'"
```

### 2. Local smoke (for physics / match changes)

```bash
cd stickblade && SDL_VIDEODRIVER=dummy python3 -c "
import pygame; pygame.init(); pygame.display.set_mode((10,10))
from main import Match
from render import FX
m = Match('mock:berserker','mock:duelist',['tip'],FX(),weapon='sword')
frames = 0
while m.phase != Match.PH_OVER and frames < 60*60:
    m.update(1/60, False); frames+=1
print(f'winner={m.winner} turns={m.turn}')
"
# Clean up test artifacts:
rm -f stickblade/battle_log_*.json
```

Run for all 5 weapons + 3 arenas on physics-touching changes.

### 3. LIVE testing via debug endpoints (mandatory for LLM/brain changes)

The `/api/debug/*` endpoints exist for exactly this. Never claim a fix
"works" until you've verified via:

```bash
BASE=https://pioneer37-stickman-arena.hf.space

# Sanity check the deploy sync:
curl -s "https://huggingface.co/api/spaces/Pioneer37/Stickman-Arena" | \
  python3 -c "import json,sys; d=json.load(sys.stdin);
    print('sha:', d.get('sha','?')[:10],
          'stage:', d.get('runtime',{}).get('stage','?'))"

# Health + feature flags:
curl -s "$BASE/api/health"

# Trigger a match:
R=$(curl -s -X POST $BASE/api/match -H "Content-Type: application/json" \
  -d '{"model_a":"...","model_b":"...","sharp":["tip"],"weapon":"sword",
       "mode":"macro","arena":"normal","blind":true}')
MID=$(echo "$R" | python3 -c "import json,sys; print(json.load(sys.stdin)['match_id'])")

# Poll until done, then check what actually happened:
curl -s "$BASE/api/replay/$MID" | python3 -c "..."
curl -s "$BASE/api/debug/brain_errors"  # WHY things failed
curl -s "$BASE/api/debug/cooldowns"     # WHO is throttled
```

**Fallback rate is the primary success metric.** If a match returns
`fallback_turns == total_turns`, the LLM layer failed 100% and the code
change didn't actually work — regardless of what unit tests pass.

### 4. Never forget to clean up

Test runs create `battle_log_*.json` files in `stickblade/`. Always:
```bash
rm -f stickblade/battle_log_*.json 2>/dev/null
```
before committing. These are `.gitignore`'d but visible in `git status`.

---

## 6. Environment variables

### Required for prod

| Var                  | Where set  | Purpose                              |
|----------------------|------------|--------------------------------------|
| `OPENROUTER_API_KEY` | HF Space   | Primary LLM provider                 |
| `GROQ_API_KEY`       | HF Space   | Secondary LLM provider (failover)    |
| `SUPABASE_URL`       | HF Space   | Postgres+bucket endpoint             |
| `SUPABASE_KEY`       | HF Space   | Service-role key (bypasses RLS)      |

### Optional

| Var                     | Default | Purpose                                     |
|-------------------------|---------|---------------------------------------------|
| `OPENAI_API_KEY`        | ""      | Enables `GPTBrain` (unused in prod)         |
| `GEMINI_API_KEY`        | ""      | Enables `GeminiBrain` (unused in prod)      |
| `ADMIN_TOKEN`           | ""      | Bypass rate limits w/ `x-admin-token` header|
| `CORS_ORIGINS`          | vercel  | Comma-separated allowlist                   |
| `TRUST_XFF`             | ""      | Set `1` to trust `X-Forwarded-For` (dev only)|
| `RL_MATCHES_PER_HOUR`   | 50      | Per-IP match creation limit                 |
| `RL_VOTES_PER_HOUR`     | 100     | Per-IP vote limit                           |
| `RL_REQS_PER_MIN`       | 120     | Per-IP general request limit                |
| `MAX_MATCHES_PER_DAY`   | 300     | Global daily cap (LLM spend ceiling)        |
| `ALLOW_PAID_CUSTOM`     | 0       | 1 = allow custom paid model ids             |

### Secret handling

- **Never** paste real keys into chat, commit, or the workspace
- User pastes keys directly into HF Space settings only
- Workspace has no configured git credentials — cannot push
- If a user pastes a key by accident, tell them immediately and instruct
  them to rotate it at the provider

---

## 7. Common pitfalls (learned the hard way, don't relearn them)

### LLM providers

- **OpenRouter and Groq have DIFFERENT reasoning-param contracts.**
  OR uses `reasoning: {enabled, exclude}`. Groq uses `include_reasoning`,
  `reasoning_format`, or `reasoning_effort` per model family. Sending OR's
  shape to Groq returns 400 "property 'reasoning' is unsupported" on
  every call. See `GroqBrain._groq_reasoning_params()` for the mapping.
- **`openai/gpt-oss-120b:free` on OR is mandatory-reasoning** — sending
  `enabled: false` gives a 400. Use `effort: "low"` instead.
- **OpenRouter free tier is 50 req/day per model** without $10 credit
  on the account. This is the #1 cause of "fallback fires immediately."
- **Groq free tier is 30 rpm per model, 14,400 rpd per model** — much more
  headroom. Retry ladder should prefer Groq buddies when OR throttles.
- **The retry ladder must re-check cooldowns before firing each attempt.**
  Was a bug (fixed in `3313e16`) where queued buddies fired even when a
  previous attempt's 429 had marked them cool.

### Physics / arena

- **Ice arena wasn't just friction.** Real fix needed shin friction
  override (1.6→0.2) AND space.damping bump (0.99→0.996) OR ice and
  stone feel identical. See `main.py` in the ice branch.
- **`build_state()` must be arena-aware** for bow-drop hints, not use
  raw `C.GRAVITY[1]`. Was a bug that told low-grav archers to
  compensate for 2.86× too much drop.
- **`MockBrain.decide()` must call `_sanitize(mv, self.actions)`**, not
  `_sanitize(mv)`. Without `self.actions`, weapon-specific moves
  (spin_up, wide_swing, thrust_over) silently get downgraded to "ready"
  and the fighter stands still.

### Frontend

- **Replay page reveal must use `canvas_a_model`/`canvas_b_model`**, not
  `model_a`/`model_b`. The engine coin-flips green/blue at match start;
  `model_a` is the user's Slot 1 pick, not the fighter that rendered as
  green. Getting this wrong = ~50% of shared /replay links show the
  wrong winner.
- **BYOK key must never appear** in: replay JSON, storage row,
  `/api/debug/brain_errors`, `_safe_err()` output, LIVE_STATE snapshot,
  any log line. Regex scrub is `_KEY_LEAK_RE`.
- **`layout.js` metadata title/description** should NOT differ across
  `<meta>`, OpenGraph, and Twitter. All three must match or link
  previews on different platforms tell different stories.

### Git / deploy

- **README.md at repo root MUST have the HF frontmatter** (title, emoji,
  sdk, etc.). If it gets replaced with the frontend README, HF Spaces
  emits `Warning: empty or missing yaml metadata in repo card` and the
  Space card display breaks.
- **The workspace and user's laptop can drift.** Multiple past sessions
  had "commit not pushed" because the user's local checkout was behind.
  Always verify `git log --oneline -3` matches `origin/main`'s tip before
  claiming state.

---

## 8. What NOT to do

- ❌ **Don't push from the workspace.** Ever. No creds, no permission.
- ❌ **Don't add npm packages** without explicit approval.
- ❌ **Don't touch `physics/brains/storage/security`** during UI work
  (and vice versa). Keep commits scoped.
- ❌ **Don't blindly execute audit-style specs** without first checking
  what's already shipped. Half of past "still broken" audits were about
  code fixed hours earlier.
- ❌ **Don't inflate grades or claim victory.** If fallback dropped from
  100% to 80%, say "still bad, here's what's left" — don't spin it as
  a win.
- ❌ **Don't paraphrase official copy the user wrote.** README frontmatter,
  onboarding card text, quips — preserve exact wording unless asked to
  rewrite.
- ❌ **Don't cold-tag anyone on user's social posts.** The user has a
  standing rule against needy tagging.
- ❌ **Don't recommend paid tools without a fit check.** The user prefers
  free-tier solutions and calls out unnecessary spend.
- ❌ **Don't delete files without clear reason.** Some seemingly-dead
  code (mockups, drafted Reddit posts, backup logos) is intentionally
  kept in the workspace.

---

## 9. Publishing / social content

When drafting social posts, README updates, or launch copy:

- Lead with **third-party validation** where possible (pymunk showcase,
  Google AI Overview, "as seen on X"). Self-praise ranks last.
- **Character limits matter.** Twitter/X: 280. LinkedIn: 3000 (but
  optimal 1200-1800). BMC bio: ~500.
- **Use "benchmark" as the primary noun.** Not "game", "tool", "sandbox".
- **Never use Markdown link syntax `[text](url)` on LinkedIn/Twitter/X.**
  They render as literal characters. Just paste the plain URL and let the
  platform auto-linkify.
- **On LinkedIn, put URLs in the first comment** for max feed reach
  (the "URLs in comments" algorithm trick). Except the replay URL, which
  belongs inline as a proof-point.

---

## 10. Quick-reference: run these before ANY session

```bash
cd /home/user/STICKBLADE-ARENA

# 1. What's the current state?
git log --oneline -5
git status

# 2. Are we in sync with GitHub?
curl -s https://api.github.com/repos/Cometbuster4969/STICKBLADE-ARENA/commits/main \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['sha'][:10])"

# 3. Is prod healthy?
curl -s https://pioneer37-stickman-arena.hf.space/api/health

# 4. Any current brain issues on prod?
curl -s https://pioneer37-stickman-arena.hf.space/api/debug/brain_errors \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d[\"count\"]} errors buffered')"
```

If any of these look unexpected, ask the user before proceeding. Don't
assume you know what state the tree should be in.

---

## 11. When in doubt

- **Ask the user with concrete options**, not open-ended "what would you like?"
- **The user cares about elegance and craft as much as shipping speed.**
  Don't split those into a false binary. When they push on UI polish
  (share buttons that actually copy vs plain links, pulse animations on
  the currently-running bracket match, canvas_a/b for correct reveals,
  killcam letterbox bars, honoring `compact` instead of ignoring it) —
  that's the whole point, not incidental. Match the standard, don't
  cut corners for velocity. "Ships this hour" and "reads well six
  months later" are both goals, weight them equally.
- **Their taste is generally right, but they're open to being wrong.**
  If they push back on a suggestion, they've usually seen a problem
  you haven't — ask why before defending. But equally: if YOU think
  they're wrong, say so directly with evidence. They've explicitly
  said they're open to discussion when they're wrong. Silent agreement
  is worse than a well-argued disagreement. State your case, show your
  work, and let them decide. Don't fold at the first sign of pushback
  unless they've given you new information you didn't have.
- **Their audits are often stale by minutes.** If a report says X is
  broken, verify against current code before agreeing. About half the time
  the fix already shipped.

---

*Last updated: this file is intended to be updated by any agent whenever
they discover a new pitfall, convention, or user preference. Keep it
factual, cite commits where possible, and don't let it grow stale.*
