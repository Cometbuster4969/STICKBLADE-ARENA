## What changed

<!-- One paragraph. What does this do, and why now? -->

## Why

<!-- The problem, not the diff. Link the issue if there is one. -->

## How it was verified

<!-- Commands a reviewer can run. "It works" is not verification.
     Delete the lines that don't apply, add the ones that do. -->

- [ ] `python3 -m pytest tests -q` → 117 passed
- [ ] `cd stickblade-web && npm run build` → build OK
- [ ] `./tools/run_match.py verify …` → replay integrity OK
- [ ] Numbers / command output:

```
(paste it)
```

## Checklist

- [ ] Every claim above has a `file:line` citation or a command I actually ran
- [ ] No API key, token, or personal data in the diff, logs, or pasted output
- [ ] Physics / prompt / spec constants unchanged, **or** `BENCHMARK_VERSION` /
      `PHYSICS_VERSION` / `PROMPT_VERSION` bumped and the new fingerprint recorded
- [ ] Schema change (if any) is idempotent in `supabase_schema.sql` **and** in the
      SQLite migration path in `storage.py`
- [ ] Blind election still holds (no model names before the vote)
- [ ] Accessibility attributes preserved (`role`, `aria-*`, focus order)
- [ ] `TIMELINE.md` updated if this ships a feature, kills an idea, or moves the roadmap
