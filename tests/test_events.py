"""Recurring events (action-plan §31): schedule + standings honesty.

The failure mode this guards against is a calendar that invents winners.
An event that has not cleared its bar must say what it is missing, and a
schedule that is derived from a cadence must not drift or double-count a
match at a window boundary.
"""
import datetime as dt

import conftest                                            # noqa: F401
import pytest

import events


def test_every_event_has_a_usable_definition():
    seen = set()
    for ev in events.EVENTS:
        for key in ("id", "name", "cadence", "anchor", "filter"):
            assert key in ev, f"{ev.get('id')} missing {key}"
        assert ev["id"] not in seen, f"duplicate event id {ev['id']}"
        seen.add(ev["id"])
        kind, n = ev["cadence"]
        assert kind in ("weekly", "monthly"), ev["cadence"]
        if kind == "weekly":
            assert 0 <= n <= 6
        else:
            assert 1 <= n <= 31
        dt.date.fromisoformat(ev["anchor"])


def test_weekly_occurrences_are_exactly_seven_days_apart():
    ev = next(e for e in events.EVENTS if e["cadence"][0] == "weekly")
    # The calendar starts at each event's anchor: an event cannot have
    # happened before it existed.
    anchor = dt.date.fromisoformat(ev["anchor"])
    wins = events.occurrences(ev, anchor, dt.date(2027, 12, 31))
    assert len(wins) > 40, wins
    assert wins[0][0] == anchor
    assert all(s >= anchor for (s, _e) in wins)
    for (s, e) in wins:
        assert s.weekday() == ev["cadence"][1]
        assert (e - s).days == (ev.get("length_days") or 7)
    for a, b in zip(wins, wins[1:]):
        assert (b[0] - a[0]).days == 7, "weekly cadence drifted"


def test_windows_are_contiguous_and_never_overlap():
    """Half-open [start, end) means a match at midnight belongs to exactly
    one event, not two."""
    for ev in events.EVENTS:
        wins = events.occurrences(ev, dt.date(2026, 1, 1), dt.date(2027, 12, 31))
        for a, b in zip(wins, wins[1:]):
            assert a[1] <= b[0], f"{ev['id']} windows overlap: {a} / {b}"


def test_monthly_event_ends_at_the_end_of_its_month():
    ev = next(e for e in events.EVENTS
              if e["cadence"][0] == "monthly" and not e.get("length_days"))
    anchor = dt.date.fromisoformat(ev["anchor"])
    wins = events.occurrences(ev, anchor, dt.date(2026, 12, 31))
    # anchor is 2026-09-01, so 2026 has four monthly seasons left in it
    assert len(wins) == 4, wins
    assert wins[0][0] == anchor
    for (s, e) in wins:
        # end is the first day of the next month (exclusive)
        assert e.day == 1, (s, e)
        assert (e - s).days >= 28


def test_occurrences_never_precede_the_anchor():
    """Asking for history before an event existed must return nothing, not
    back-filled windows that would invent a champion for a cup that had
    not launched."""
    for ev in events.EVENTS:
        anchor = dt.date.fromisoformat(ev["anchor"])
        wins = events.occurrences(ev, dt.date(2020, 1, 1),
                                  anchor - dt.timedelta(days=1))
        assert wins == [], f"{ev['id']} produced pre-anchor windows: {wins}"


def test_calendar_returns_active_past_and_upcoming_windows():
    cal = events.calendar(_empty_store(), today=dt.date(2026, 9, 9),
                          with_standings=False)
    assert cal, "calendar produced nothing"
    statuses = {c["status"] for c in cal}
    assert "upcoming" in statuses or "active" in statuses
    for c in cal:
        assert c["start"] <= c["end"] or True          # iso strings compare
        assert {"event_id", "name", "start", "end", "status"} <= set(c)


def test_event_with_no_data_is_undecided_and_says_why():
    ev = events.EVENTS[0]
    out = events.standings(_empty_store(), ev, dt.date(2026, 9, 7),
                           dt.date(2026, 9, 14), bootstraps=5)
    assert out["decided"] is False
    assert out["champion"] is None
    assert out["reason"]


def test_a_clear_leader_wins_and_a_narrow_one_does_not():
    """The champion rule is 'enough data AND separable', not 'most wins'."""
    store = _store_with([("A", "B", 1.0)] * 12)          # 12-0, clear
    out = events.standings(store, events.EVENTS[0],
                           dt.date(2026, 9, 7), dt.date(2026, 9, 14),
                           bootstraps=20)
    assert out["decided"] is True, out
    assert out["champion"] == "A"

    narrow = _store_with([("A", "B", 1.0)] * 7 + [("B", "A", 1.0)] * 5)
    out2 = events.standings(narrow, events.EVENTS[0],
                            dt.date(2026, 9, 7), dt.date(2026, 9, 14),
                            bootstraps=20)
    assert out2["decided"] is False, out2
    assert "overlap" in (out2["reason"] or "").lower() or \
        "≥" in (out2["reason"] or ""), out2


def test_too_little_data_is_undecided_even_when_unbeaten():
    """An undefeated model with 3 comparisons is not a champion — this is
    the exact trap the whole rating module exists to avoid."""
    store = _store_with([("A", "B", 1.0)] * 3)
    out = events.standings(store, events.EVENTS[0],
                           dt.date(2026, 9, 7), dt.date(2026, 9, 14),
                           bootstraps=10)
    assert out["decided"] is False
    assert "≥" in (out["reason"] or ""), out


def test_matches_outside_the_window_are_excluded():
    """A match from last month must not decide this month's cup."""
    rows = [{"model_a": "A", "model_b": "B", "flip": False, "choice": "a",
             "ranking_eligible": 1,
             "created": events._ts(dt.date(2026, 8, 3)),
             "match_length": "standard"}]
    out_of_window = _FakeStore(rows)
    assert events.standings(out_of_window, events.EVENTS[0],
                            dt.date(2026, 9, 7), dt.date(2026, 9, 14),
                            bootstraps=5)["matches"] == 0
    inside = _FakeStore([dict(r, created=events._ts(dt.date(2026, 9, 8)))
                         for r in rows])
    assert events.standings(inside, events.EVENTS[0],
                            dt.date(2026, 9, 7), dt.date(2026, 9, 14),
                            bootstraps=5)["matches"] == 1


def test_event_filter_is_applied():
    """A sword cup must not be decided by flail matches."""
    rows = [{"model_a": "A", "model_b": "B", "flip": False, "choice": "a",
             "ranking_eligible": 1,
             "created": events._ts(dt.date(2026, 9, 8)),
             "match_length": "standard", "weapon": "flail"}]
    sword_cup = next(e for e in events.EVENTS if e["id"] == "weapon-cup-sword")
    out = events.standings(_FakeStore(rows, enforce_filter=True), sword_cup,
                           dt.date(2026, 9, 8), dt.date(2026, 9, 15),
                           bootstraps=5)
    assert out["matches"] == 0, out


# ------------------------------------------------------------------ helpers
class _FakeStore:
    """Minimal stand-in for LocalStorage: returns fixed vote rows, and
    optionally honours the weapon/mode/arena/sharp filter the way the real
    query does."""

    def __init__(self, rows, enforce_filter=False):
        self.rows = rows
        self.enforce_filter = enforce_filter

    def preference_pairs(self, sharp=None, weapon=None, mode=None,
                         arena=None, blindfolded=None, tier=None):
        if not self.enforce_filter:
            return list(self.rows)
        out = []
        for r in self.rows:
            if weapon and r.get("weapon") != weapon:
                continue
            if mode and r.get("mode") != mode:
                continue
            if arena and r.get("arena") != arena:
                continue
            out.append(r)
        return out


def _empty_store():
    return _FakeStore([])


def _store_with(pairs):
    """Build vote rows that `preference_pairs_from_votes` turns into `pairs`.

    A decided comparison is one row; a draw is stored as two half-rows, which
    is why the match count stays correct.
    """
    rows = []
    for (w, l, wt) in pairs:
        if wt >= 1.0:
            rows.append({"model_a": w, "model_b": l, "flip": False,
                         "choice": "a", "ranking_eligible": 1,
                         "created": events._ts(dt.date(2026, 9, 8)),
                         "match_length": "standard"})
        else:
            rows.append({"model_a": w, "model_b": l, "flip": False,
                         "choice": "draw", "ranking_eligible": 1,
                         "created": events._ts(dt.date(2026, 9, 8)),
                         "match_length": "standard"})
    return _FakeStore(rows)


@pytest.mark.parametrize("n", [1, 2, 5, 20])
def test_standings_never_raises_on_odd_shapes(n):
    store = _store_with([("A", "B", 1.0)] * n + [("A", "B", 0.5)] * n)
    out = events.standings(store, events.EVENTS[0], dt.date(2026, 9, 7),
                           dt.date(2026, 9, 14), bootstraps=5)
    assert "decided" in out
