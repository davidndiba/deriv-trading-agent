"""tools/news_calendar.py has no third-party dependency, so this runs
directly. Fixture rows below are copied from the real feed's actual
shape, fetched and confirmed while building this (see docs/PROGRESS.md),
not guessed."""
import json
import urllib.request
from datetime import datetime, timedelta

from tools.news_calendar import _parse_events, fetch_this_weeks_events, is_within_news_blackout

RAW_FIXTURE = [
    {"title": "CPI m/m", "country": "CAD", "date": "2026-11-16T08:30:00-05:00",
     "impact": "High", "forecast": "0.3%", "previous": "0.1%"},
    {"title": "Core CPI m/m", "country": "CAD", "date": "2026-11-16T08:30:00-05:00",
     "impact": "Low", "forecast": "0.2%", "previous": "0.0%"},
    {"title": "Retail Sales m/m", "country": "USD", "date": "2026-11-17T08:30:00-05:00",
     "impact": "High", "forecast": "0.1%", "previous": "0.8%"},
    {"title": "missing date", "country": "XXX"},
]


def test_parse_events_skips_malformed_rows_without_crashing():
    events = _parse_events(RAW_FIXTURE)
    assert len(events) == 3
    assert events[0].title == "CPI m/m"
    assert events[0].currency == "CAD"
    assert events[0].impact == "High"
    assert events[0].at.tzinfo is not None


def test_blackout_window_boundaries_are_inclusive():
    events = _parse_events(RAW_FIXTURE)
    event_time = datetime.fromisoformat("2026-11-16T08:30:00-05:00")

    hit, trig = is_within_news_blackout(
        {"CAD"}, events, event_time - timedelta(minutes=30), minutes_before=30, minutes_after=30
    )
    assert hit and trig.title == "CPI m/m"

    miss, _ = is_within_news_blackout(
        {"CAD"}, events, event_time - timedelta(minutes=31), minutes_before=30, minutes_after=30
    )
    assert not miss

    hit_after, _ = is_within_news_blackout(
        {"CAD"}, events, event_time + timedelta(minutes=30), minutes_before=30, minutes_after=30
    )
    assert hit_after

    miss_after, _ = is_within_news_blackout(
        {"CAD"}, events, event_time + timedelta(minutes=31), minutes_before=30, minutes_after=30
    )
    assert not miss_after


def test_blackout_ignores_other_currencies():
    events = _parse_events(RAW_FIXTURE)
    event_time = datetime.fromisoformat("2026-11-16T08:30:00-05:00")
    hit, _ = is_within_news_blackout({"EUR"}, events, event_time, minutes_before=30, minutes_after=30)
    assert not hit


def test_blackout_respects_min_impact():
    low_only = [e for e in _parse_events(RAW_FIXTURE) if e.impact == "Low"]
    event_time = datetime.fromisoformat("2026-11-16T08:30:00-05:00")

    blocked_at_high = is_within_news_blackout({"CAD"}, low_only, event_time, min_impact="High")[0]
    assert not blocked_at_high  # the only CAD event here is Low impact

    blocked_at_low = is_within_news_blackout({"CAD"}, low_only, event_time, min_impact="Low")[0]
    assert blocked_at_low


def test_fetch_returns_parsed_events(monkeypatch):
    class FakeResp:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    payload = json.dumps(RAW_FIXTURE[:3]).encode("utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: FakeResp(payload))
    events = fetch_this_weeks_events()
    assert len(events) == 3


def test_fetch_failure_propagates_rather_than_returning_empty(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        fetch_this_weeks_events()
        raised = False
    except OSError:
        raised = True
    assert raised
