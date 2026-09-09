# Security Policy

## Supported versions

This is a solo research project. Only the latest commit on `main` is
supported; there is no LTS branch and no backporting.

## Reporting a vulnerability

**Please do not open a public issue for a security bug.** Use GitHub's private
vulnerability reporting:

<https://github.com/Cometbuster4969/STICKBLADE-ARENA/security/advisories/new>

If that is unavailable, open a
[private security advisory](https://docs.github.com/en/code-security/security-advisories)
or contact the maintainer directly through their GitHub profile.

**What to include**

- What the issue is and where it lives (`file:line` if you can).
- A minimal reproduction.
- What an attacker gains (data exposure, spend amplification, rating
  manipulation…).

**What to expect**

- Acknowledgement within a few days. It might take longer — this is one
  person's project, not a staffed security team.
- A fix, or a written explanation of why the behaviour is intended, once
  reproduced.
- Credit in the fix commit and advisory unless you would rather stay anonymous.

## Trust boundaries

There are three, and they are defended differently:

### 1. Your API key (BYOK)

If you paste an OpenRouter key into the arena it is used **only** for that
match's HTTP calls. It is:

- never written to the database, the replay JSON, the battle log, or any
  export (`tests/test_byok.py` asserts each of these),
- removed from the in-process key map when the match finishes,
- never logged — provider errors pass through `server._safe_err()`, which
  strips `sk-*` strings, `Bearer` tokens and URLs before anything is printed
  or returned.

The key does travel through the backend (it has to, to make the call), so
**use a scoped, rate-limited key** and treat it as you would any third-party
integration. Details: [/trust](https://stickblade-arena.vercel.app/trust).

### 2. Model output (untrusted input)

Everything a model returns is attacker-influenced text if the operator of
that model wants it to be. Defences:

- Replies are parsed and **sanitised against the weapon's action vocabulary**;
  unknown actions coerce to `ready` and are counted, not executed.
- A fighter is never shown its opponent's `thought` field, so one model cannot
  inject instructions into another's prompt.
- Custom free-text fields are filtered before transmission.

### 3. The rating system

Votes are anonymous and there is no account system, which removes most
ballot-stuffing surface, but the remaining abuse is worth naming:

- **Exploitative play** (permanent guarding, edge camping, repeated identical
  actions) is detected after the fact by `stickblade/anti_gaming.py` and
  surfaced at `GET /api/integrity/{match_id}`.
- **Spend amplification** is bounded by per-IP rate limits
  (`RL_MATCHES_PER_HOUR`, `RL_REQS_PER_MIN`, `MAX_QUEUE`,
  `MAX_MATCHES_PER_DAY`) and by adaptive per-model timeouts.
- **Rating attacks** are limited because only the tactical vote is ranked and
  each match accepts one vote.

## Known non-issues

Things that look like findings but are intended:

- `/api/debug/*` endpoints exist for operator diagnosis of provider
  throttling. They return cooldown and error counters, never key material.
- Supabase-backed deploys read config from environment variables; local runs
  fall back to SQLite under `arena_data/`.
- The frontend sets a strict Content-Security-Policy that omits
  `fonts.googleapis.com`. Fonts are self-hosted from npm (`@fontsource/*`),
  so no build or page load ever reaches a third-party font host.

## Automated scanning

CI runs `bandit` on the backend plus a dependency audit on every push. A
failing security job blocks the merge.
