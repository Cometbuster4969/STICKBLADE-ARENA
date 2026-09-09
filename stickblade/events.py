"""Recurring events and seasons (action-plan §31).

A benchmark with no calendar is a benchmark people run once. Recurring
events give the community a reason to come back, and — more importantly
for the research side — they convert the leaderboard from a single
ever-moving number into a series of comparable, dated snapshots ("who won
the September sword cup"), which is the form a result is actually citable
in.

Design decisions:

* **The schedule is derived, not stored.** Occurrences are computed from a
  cadence + anchor date, so there is no table to keep in sync and no cron
  that can silently stop running. Ask for the calendar on any date and you
  get the same answer.
* **Standings come from the same estimators as the leaderboard.** An event
  champion is decided by the Bradley-Terry fit over that event's window,
  not by a bespoke points system nobody has audited.
* **An event with no matches reports that, honestly.** An empty event is
  rendered as "no matches yet", never as a winner. This matters because a
  brand-new cadence will be empty on day one and must not look broken.
* **Windows are half-open [start, end)** so adjacent events cannot
  double-count a match at midnight.
"""
from __future__ import annotations

import datetime as _dt
import math

from ratings import fit_with_ci, preference_pairs_from_votes

# --------------------------------------------------------------------- config
# Each event declares: id, name, cadence, the eval-cell filter that defines
# it, and how it is scored. `cadence` is ("weekly", weekday) or
# ("monthly", day-of-month); `length_days` is how long the window runs.
# `anchor` is the first occurrence's start date — everything after is
# derived from it, so the calendar is reproducible forever.
EVENTS = [
    {
        "id": "weekly-cup",
        "name": "Weekly Model Cup",
        "blurb": "Open division. Any model, any weapon — the week's most "
                 "preferred fighter takes it.",
        "cadence": ("weekly", 0),        # Monday
        "length_days": 7,
        "anchor": "2026-09-07",
        "filter": {},
        "min_matches": 5,
    },
    {
        "id": "monthly-season",
        "name": "Monthly Benchmark Season",
        "blurb": "The headline series. A month of matches in one cell is "
                 "enough data for the intervals to mean something.",
        "cadence": ("monthly", 1),       # 1st of the month
        "length_days": None,             # runs to the end of the month
        "anchor": "2026-09-01",
        "filter": {},
        "min_matches": 10,
    },
    {
        "id": "weapon-cup-sword",
        "name": "Sword Cup",
        "blurb": "Sword only. Rotates weapon each month so every weapon "
                 "gets a turn in the spotlight.",
        "cadence": ("monthly", 8),
        "length_days": 7,
        "anchor": "2026-09-08",
        "filter": {"weapon": "sword"},
        "min_matches": 5,
    },
    {
        "id": "weapon-cup-flail",
        "name": "Flail Cup",
        "blurb": "Flail only. Note: flail is measured asymmetric "
                 "(side-A win rate 0.19, CI [0.08, 0.38]) — treat results "
                 "as configuration-dependent.",
        "cadence": ("monthly", 15),
        "length_days": 7,
        "anchor": "2026-09-15",
        "filter": {"weapon": "flail"},
        "min_matches": 5,
        "caveat": "Flail matches are asymmetric by configuration; see "
                  "research/balance_report.md before reading anything into "
                  "these standings.",
    },
    {
        "id": "blindfolded-challenge",
        "name": "Blindfolded Challenge",
        "blurb": "No pre-parsed spatial hints — the model derives facing, "
                 "height and distance from raw coordinates. A genuinely "
                 "different question from normal mode.",
        "cadence": ("monthly", 22),
        "length_days": 7,
        "anchor": "2026-09-22",
        "filter": {"blindfolded": True},
        "min_matches": 5,
    },
    {
        "id": "speed-tournament",
        "name": "Speed Tournament",
        "blurb": "Sprint-length matches (4 turns). Rewards fast, decisive "
                 "play and exposes models that need time to warm up.",
        "cadence": ("weekly", 3),        # Thursday
        "length_days": 2,
        "anchor": "2026-09-10",
        "filter": {"match_length": "sprint"},
        "min_matches": 5,
    },
    {
        "id": "joint-mode-open",
        "name": "JOINT Mode Open",
        "blurb": "Raw joint control, no tactical layer. Measures motor "
                 "coherence rather than tactics.",
        "cadence": ("monthly", 25),
        "length_days": 5,
        "anchor": "2026-09-25",
        "filter": {"mode": "joint"},
        "min_matches": 5,
    },
]


def _d(s):
    return _dt.date.fromisoformat(s)


def _month_end(y, m):
    """Last day of month (avoids a calendar dependency)."""
    if m == 12:
        return _dt.date(y, 12, 31)
    return _dt.date(y, m + 1, 1) - _dt.timedelta(days=1)


def occurrences(ev, start_date, end_date):
    """Every [start, end) window of `ev` overlapping [start_date, end_date]."""
    kind, n = ev["cadence"]
    anchor = _d(ev["anchor"])
    out = []
    if kind == "weekly":
        # Walk weekly from the anchor; step to the requested weekday first.
        cur = anchor
        while cur.weekday() != n:
            cur += _dt.timedelta(days=1)
        while cur < start_date:
            cur += _dt.timedelta(days=7)
        while cur <= end_date:
            length = ev.get("length_days") or 7
            out.append((cur, cur + _dt.timedelta(days=length)))
            cur += _dt.timedelta(days=7)
    elif kind == "monthly":
        # Walk monthly from the anchor's month.
        y, m = anchor.year, anchor.month
        cur = _dt.date(y, m, min(n, _month_end(y, m).day))
        while cur < start_date:
            m += 1
            if m > 12:
                y, m = y + 1, 1
            cur = _dt.date(y, m, min(n, _month_end(y, m).day))
        while cur <= end_date:
            if ev.get("length_days"):
                end = cur + _dt.timedelta(days=ev["length_days"])
            else:
                end = _month_end(cur.year, cur.month) + _dt.timedelta(days=1)
            out.append((cur, end))
            m += 1
            if m > 12:
                y, m = y + 1, 1
            cur = _dt.date(y, m, min(n, _month_end(y, m).day))
    return out


def _ts(d):
    """Midnight UTC epoch for a date (matches the `created` column)."""
    return _dt.datetime(d.year, d.month, d.day,
                        tzinfo=_dt.timezone.utc).timestamp()


def _event_store_rows(store, filt, start, end):
    """Raw voted-match rows inside the window, honouring the event filter."""
    try:
        rows = store.preference_pairs(
            sharp=filt.get("sharp"),
            weapon=filt.get("weapon"),
            mode=filt.get("mode"),
            arena=filt.get("arena"),
            blindfolded=filt.get("blindfolded"),
        )
    except TypeError:
        return []
    out = []
    for r in rows:
        created = r.get("created")
        if created is None:
            continue
        try:
            c = float(created)
        except (TypeError, ValueError):
            continue
        if c < start or c >= end:
            continue
        if filt.get("match_length") and r.get("match_length") != filt["match_length"]:
            continue
        out.append(r)
    return out


def standings(store, ev, start, end, bootstraps=100):
    """Rank the field inside one event window.

    Returns {"champion", "rows", "matches", "comparisons", "decided"}.
    `decided` is False when the event has too little data to name a
    winner — an undecided event is reported as undecided, not filled in.
    """
    rows = _event_store_rows(store, ev.get("filter") or {}, _ts(start), _ts(end))
    pairs = preference_pairs_from_votes(rows)
    if not pairs:
        return {"champion": None, "rows": [], "matches": 0,
                "comparisons": 0, "decided": False,
                "reason": "no voted matches in this window yet"}
    fitted = fit_with_ci(pairs, bootstraps=bootstraps)
    if not fitted:
        return {"champion": None, "rows": [], "matches": len(rows),
                "comparisons": len(pairs), "decided": False,
                "reason": "no eligible comparisons"}
    top = fitted[0]
    min_m = int(ev.get("min_matches") or 5)
    enough = top["matches"] >= min_m
    # A champion must also be separable from the runner-up: leading on a
    # point estimate inside overlapping intervals is not a win.
    separable = True
    if len(fitted) > 1:
        second = fitted[1]
        separable = top["ci_low"] > second["ci_high"]
    decided = bool(enough and separable)
    if decided:
        reason = None
    elif not enough:
        reason = (f"leader has {top['matches']} comparisons, "
                  f"needs ≥{min_m}")
    else:
        reason = ("leader's interval overlaps the runner-up's — "
                  "not separable yet")
    return {
        "champion": top["model"] if decided else None,
        "champion_rating": top["rating"],
        "champion_ci": [top["ci_low"], top["ci_high"]],
        "rows": fitted,
        "matches": len(rows),
        "comparisons": len(pairs),
        "decided": decided,
        "reason": reason,
    }


def calendar(store, today=None, past=3, future=4, bootstraps=100,
             with_standings=True):
    """The event calendar around `today`: past windows (archive) + upcoming.

    Only the most recent `past` and next `future` occurrences per event are
    materialised, so the payload stays small even years into the project.
    """
    today = today or _dt.date.today()
    # Look back/forward far enough to capture `past`/`future` occurrences of
    # the slowest cadence (monthly), then trim.
    start = _dt.date(today.year, today.month, 1) - _dt.timedelta(days=31 * past + 5)
    end = today + _dt.timedelta(days=31 * (future + 1))
    out = []
    for ev in EVENTS:
        windows = occurrences(ev, start, end)
        if not windows:
            continue
        # Split around today.
        finished = [w for w in windows if w[1] <= today]
        live = [w for w in windows if w[0] <= today < w[1]]
        upcoming = [w for w in windows if w[0] > today]
        keep = finished[-past:] + live + upcoming[:future]
        for (s, e) in keep:
            status = ("active" if s <= today < e
                      else "past" if e <= today else "upcoming")
            entry = {
                "event_id": ev["id"],
                "name": ev["name"],
                "blurb": ev.get("blurb"),
                "caveat": ev.get("caveat"),
                "filter": ev.get("filter") or {},
                "min_matches": ev.get("min_matches", 5),
                "start": s.isoformat(),
                "end": e.isoformat(),
                "status": status,
            }
            if status != "upcoming" and with_standings:
                entry.update(standings(store, ev, s, e, bootstraps=bootstraps))
            out.append(entry)
    out.sort(key=lambda x: (x["start"], x["name"]))
    return out


def champions(store, bootstraps=50):
    """Archive: every decided past window, newest first."""
    cal = calendar(store, past=12, future=0, bootstraps=bootstraps)
    won = [c for c in cal if c.get("decided") and c.get("champion")]
    won.sort(key=lambda x: x["start"], reverse=True)
    return won
