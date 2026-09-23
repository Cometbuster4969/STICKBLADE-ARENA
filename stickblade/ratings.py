"""Rating models with uncertainty (action-plan §5).

Elo is fine as a live scoreboard and terrible as a scientific claim. It has
no notion of confidence, it is order-dependent (the same matches in a
different order give different ratings once ratings move), and it cannot tell
you "this model is 1200 but we genuinely don't know" — the single most
important thing to be able to say when n is small.

So this module adds a **Bradley–Terry** model fitted by maximum likelihood:

    P(i beats j) = logistic(theta_i - theta_j)

with:

  * **Ties** handled by the Davidson extension (a draw counts as half a win to
    each side plus a shared tie parameter), because roughly 10–20 % of our
    matches end in a draw and dropping them biases every rating.
  * **Ridge regularisation** toward zero (theta = 0 ⇒ rating 1000) so an
    undefeated model with three matches does not get an infinite rating — the
    sparse-data failure mode Elo handles by silently over-ranking.
  * **Bootstrap confidence intervals** (resample the match set), which is the
    honest answer to "how sure are we" and needs no normality assumption.

Ratings are reported on an Elo-like scale (400/ln(10) ≈ 173.7 points per
logit) purely so they are readable next to the Elo column. They are a
different quantity: Elo is a running estimate, this is an MLE over a fixed
match set.

Design decisions worth knowing:
  * **Votes, not physics, decide the pairs.** The benchmark measures human
    tactical preference, so a "win" is a vote. Physics wins are available
    separately (`/api/leaderboard/objective`).
  * **Self-play and mirror matches are dropped**, consistent with the Elo
    path.
  * **Cells are separate models.** weapon/arena/sharp/mode/blindfolded
    filters are applied before fitting, because pooling them would compare
    different questions.
  * **Disconnected models are reported, not hidden.** A model whose matches
    never connect it to the rest of the graph is only comparable within its
    own component, so we say so.

Usage:
    from ratings import bradley_terry, fit_with_ci
    rows = fit_with_ci(pairs, bootstraps=200)
"""
from __future__ import annotations

import math
import random as _random

# Elo-ish scale: 400 points per e-fold... standard conversion is
# 400 / ln(10) per natural-log unit.
SCALE = 400.0 / math.log(10.0)
CENTER = 1000.0

# Ridge penalty on theta. 1.0 is mild — it keeps an undefeated 3-match model
# within ~±200 points of the field instead of running off to infinity.
DEFAULT_RIDGE = 1.0
DEFAULT_TIE_PARAM = 0.5


def _logistic(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def bradley_terry(pairs, ridge: float = DEFAULT_RIDGE,
                  tie_param: float = DEFAULT_TIE_PARAM,
                  iterations: int = 500, tol: float = 1e-9):
    """Fit Bradley–Terry with Davidson ties by minorisation-maximisation.

    `pairs` is an iterable of `(winner, loser, weight)` where `weight` is 1.0
    for a win and 0.5 each way for a draw (a draw contributes two 0.5
    entries, one per direction).

    Davidson model (1970) for one comparison of i vs j:

        P(i wins)  = p_i / D          D = p_i + p_j + nu * sqrt(p_i * p_j)
        P(tie)     = nu * sqrt(p_i p_j) / D
        p = exp(theta)

    with `nu > 0` the tie parameter. Dropping draws (the usual shortcut)
    would bias every rating here, since ~10–20 % of our matches end level.

    Update (Davidson's iterative scaling, an MM step):

        theta_i <- log( (W_i + ridge/2) / (sum_j N_ij * (p_i + nu/2 * sqrt(p_i p_j)) / D_ij + ridge) )

    where `W_i` = observed wins + half the ties, and `N_ij` = comparisons
    between i and j. MM is used rather than Newton because it converges
    monotonically and never needs a Hessian inverse — which matters when the
    data is sparse enough that the Hessian is near-singular.

    Returns `{model: theta}` with the scale centred on zero.
    """
    players = {}
    for w, l, _wt in pairs:
        players.setdefault(w, 0.0)
        players.setdefault(l, 0.0)
    if not players:
        return {}

    names = sorted(players)
    idx = {n: i for i, n in enumerate(names)}
    n = len(names)

    # Per UNORDERED pair: wins each way and ties. Counting per pairing (not
    # per direction) is what makes the tie parameter estimable.
    pair_wins = {}          # (i, j) i<j -> [wins_i, wins_j, ties]
    for w, l, wt in pairs:
        i, j = idx[w], idx[l]
        key = (i, j) if i < j else (j, i)
        slot = pair_wins.setdefault(key, [0.0, 0.0, 0.0])
        wt = float(wt)
        if wt >= 1.0:
            slot[0 if i < j else 1] += 1.0
        else:
            slot[2] += 0.5              # ties arrive twice, one per direction
    keys = sorted(pair_wins)
    total_ties = sum(pair_wins[k][2] for k in keys)

    nu = float(tie_param) if tie_param else 0.0
    theta = [0.0] * n

    # Observed points per player: a win is 1, a tie is 0.5.
    points = [0.0] * n
    for (a, b) in keys:
        w_ab, w_ba, t_ab = pair_wins[(a, b)]
        points[a] += w_ab + 0.5 * t_ab
        points[b] += w_ba + 0.5 * t_ab

    for _ in range(iterations):
        p = [math.exp(t) for t in theta]
        root = [math.sqrt(v) for v in p]

        # --- Davidson tie parameter, estimated from the data -------------
        # nu = T / sum_{i<j} N_ij * sqrt(p_i p_j) / D_ij   (score equation).
        # A FIXED nu biases every rating: with nu > 0 and no draws in the
        # sample the model still "expects" ties and flattens the fit, which
        # is exactly the bug this replaced. No ties at all => nu -> 0, i.e.
        # ordinary Bradley-Terry.
        if total_ties > 0:
            den_nu = 0.0
            for (i, j) in keys:
                w_ij, w_ji, t_ij = pair_wins[(i, j)]
                nij = w_ij + w_ji + t_ij
                if nij <= 0:
                    continue
                d = p[i] + p[j] + nu * root[i] * root[j]
                if d > 0:
                    den_nu += nij * root[i] * root[j] / d
            nu = min(20.0, total_ties / den_nu) if den_nu > 0 else 0.0
        else:
            nu = 0.0

        # --- fixed-point (MM) update -------------------------------------
        # Score equation:  W_i = sum_j N_ij (p_i + nu/2 * sqrt(p_i p_j)) / D_ij
        # Rearranged so the fixed point IS the score equation:
        #   p_i <- W_i / sum_j N_ij (1 + nu/2 * sqrt(p_j / p_i)) / D_ij
        new = [0.0] * n
        for i in range(n):
            s_i = 0.0
            for j in range(n):
                if i == j:
                    continue
                key = (i, j) if i < j else (j, i)
                if key not in pair_wins:
                    continue
                w_a, w_b, t_ij = pair_wins[key]
                nij = w_a + w_b + t_ij
                if nij <= 0:
                    continue
                d = p[i] + p[j] + nu * root[i] * root[j]
                if d <= 0:
                    continue
                s_i += nij * (1.0 + 0.5 * nu * root[j] / root[i]) / d
            # ridge: shrinks toward theta = 0 (rating 1000) when data is thin,
            # so a 3-0 newcomer cannot run off to infinity.
            new[i] = math.log((points[i] + ridge * 0.5) / (s_i + ridge))
        delta = max(abs(new[i] - theta[i]) for i in range(n))
        mean = sum(new) / n
        theta = [t - mean for t in new]
        if delta < tol:
            break
    out = {names[i]: theta[i] for i in range(n)}
    out["_nu"] = nu                      # exposed for diagnostics/tests
    return out


def _components(pairs):
    """Connected components of the match graph (union-find).

    A rating is only meaningful inside its component: if model X has only
    ever played model Y, and neither has played anyone else, X vs Z is not
    estimable no matter what the numbers say.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w, l, _wt in pairs:
        union(w, l)
    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)
    return list(groups.values()), find


def _match_units(pairs):
    """Group pair rows into matches, so the bootstrap resamples MATCHES.

    A draw is stored as two directed rows ((i, j, 0.5) and (j, i, 0.5)) but
    is one match. Resampling rows would give every draw double the sampling
    weight of a decided match and report an interval that is too tight
    exactly when draws are common.
    """
    units = []
    used = [False] * len(pairs)
    for i, (w, l, wt) in enumerate(pairs):
        if used[i]:
            continue
        used[i] = True
        if wt >= 1.0:
            units.append([i])
            continue
        mirror = None
        for j in range(i + 1, len(pairs)):
            if (not used[j] and pairs[j][0] == l and pairs[j][1] == w
                    and pairs[j][2] == wt):
                mirror = j
                break
        if mirror is None:          # unpaired draw row — resample alone
            units.append([i])
        else:
            used[mirror] = True
            units.append([i, mirror])
    return units


def fit_with_ci(pairs, bootstraps: int = 200, ridge: float = DEFAULT_RIDGE,
                seed: int = 12345, min_matches: int = 1):
    """Fit Bradley–Terry with bootstrap confidence intervals.

    Returns rows sorted by rating desc:
        {model, rating, ci_low, ci_high, matches, wins, losses, draws,
         preference_rate, component}
    """
    pairs = [(w, l, float(wt)) for w, l, wt in pairs if w and l and w != l]
    if not pairs:
        return []

    # A draw is recorded as TWO pair entries (one per direction) so the
    # fitter can treat it as half a win each way — but it is still ONE
    # match for counting purposes. Counting each entry as a match would
    # inflate n and publish a confidence interval that is far too tight.
    counts = {}
    for w, l, wt in pairs:
        a = counts.setdefault(w, {"matches": 0.0, "wins": 0, "losses": 0,
                                  "draws": 0.0, "score": 0.0})
        b = counts.setdefault(l, {"matches": 0.0, "wins": 0, "losses": 0,
                                  "draws": 0.0, "score": 0.0})
        if wt >= 1.0:
            a["wins"] += 1; b["losses"] += 1
            a["score"] += 1.0
            a["matches"] += 1.0; b["matches"] += 1.0
        else:
            a["draws"] += 0.5; b["draws"] += 0.5
            a["score"] += 0.25; b["score"] += 0.25
            a["matches"] += 0.5; b["matches"] += 0.5

    groups, find = _components(pairs)
    comp_id = {}
    for i, g in enumerate(sorted(groups, key=lambda g: -len(g))):
        for node in g:
            comp_id[node] = i

    base = bradley_terry(pairs, ridge=ridge)
    if not base:
        return []

    # Bootstrap: resample MATCHES, not pair rows. A draw is two rows for one
    # match, so resampling rows would over-weight draws.
    rng = _random.Random(seed)
    draw_curves = {m: [] for m in base}
    units = _match_units(pairs)
    n_units = len(units)
    for _ in range(max(0, int(bootstraps))):
        sample = [pairs[i]
                  for u in (units[rng.randrange(n_units)] for _ in range(n_units))
                  for i in u]
        fit = bradley_terry(sample, ridge=ridge)
        for m, t in fit.items():
            draw_curves.setdefault(m, []).append(t)
        for m in draw_curves:
            if m not in fit:
                draw_curves[m].append(base.get(m, 0.0))

    rows = []
    for model, theta in base.items():
        c = counts.get(model, {"matches": 0, "wins": 0, "losses": 0,
                               "draws": 0, "score": 0.0})
        if int(round(c["matches"])) < min_matches:
            continue
        samples = sorted(draw_curves.get(model) or [theta])
        k = len(samples)
        lo = samples[int(0.025 * k)] if k > 1 else theta
        hi = samples[min(k - 1, int(0.975 * k))] if k > 1 else theta
        n = int(round(c["matches"])) or 1
        rows.append({
            "model": model,
            "rating": round(CENTER + SCALE * theta, 1),
            "ci_low": round(CENTER + SCALE * lo, 1),
            "ci_high": round(CENTER + SCALE * hi, 1),
            "theta": round(theta, 4),
            "matches": n,
            "wins": c["wins"], "losses": c["losses"],
            "draws": int(round(c["draws"])),
            "preference_rate": round(c["score"] / n, 3),
            "component": comp_id.get(model, 0),
            "component_size": sum(1 for m in comp_id
                                 if comp_id[m] == comp_id.get(model, 0)),
            # A rating is provisional until it has enough matches AND is
            # connected to the field — both are stated, not inferred.
            "provisional": bool(n < 10 or comp_id.get(model, 0) != 0),
        })
    rows.sort(key=lambda r: -r["rating"])
    return rows


def preference_pairs_from_votes(rows):
    """Turn joined match+vote rows into Bradley–Terry pairs.

    `rows` are dicts with: model_a, model_b, flip, choice (the tactical
    vote: 'a' | 'b' | 'draw'), and ranking_eligible.

    The vote is cast on CANVAS sides (a/b) but credited to MODELS, which is
    what `flip` encodes. Getting this backwards would silently rank the wrong
    model — the same mapping Elo uses.
    """
    pairs = []
    for r in rows:
        # `in (False, 0)`, not `is False`: SQLite rows carry 0/1 ints while
        # Supabase rows carry real booleans — both must exclude ineligible.
        # Missing/None reads as eligible (back-compat for minimal rows).
        if r.get("ranking_eligible") in (False, 0):
            continue
        flip = bool(r.get("flip"))
        a_model = r.get("model_b") if flip else r.get("model_a")
        b_model = r.get("model_a") if flip else r.get("model_b")
        if not a_model or not b_model or a_model == b_model:
            continue                      # mirror/self-play: not estimable
        choice = (r.get("choice") or "").lower()
        if choice == "a":
            pairs.append((a_model, b_model, 1.0))
        elif choice == "b":
            pairs.append((b_model, a_model, 1.0))
        elif choice == "draw":
            pairs.append((a_model, b_model, 0.5))
            pairs.append((b_model, a_model, 0.5))
    return pairs
