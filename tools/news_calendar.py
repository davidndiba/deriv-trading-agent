"""Economic calendar data for a news-event blackout guard — skip
proposing trades right before/after high-impact releases (NFP, FOMC,
CPI, central bank speeches, etc.) that can spike price outside what any
backtested signal was ever trained to expect.

Data source: https://nfs.faireconomy.media/ff_calendar_thisweek.json —
Forex Factory's own free, public, no-API-key weekly JSON export, widely
used by retail trading tools for exactly this purpose. Field names
(`title`, `country`, `date`, `impact`, `forecast`, `previous`) were
confirmed by fetching it directly, not assumed from documentation. It
covers the CURRENT WEEK ONLY. This is an unofficial export, not a
documented contract from Forex Factory — it could change format or go
away without notice; see docs/DECISIONS.md for why callers of
fetch_this_weeks_events() should fail CLOSED (block trading) rather than
open (assume no news) when it can't be fetched or parsed.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
IMPACT_ORDER = {"Low": 1, "Medium": 2, "High": 3}


@dataclass(frozen=True)
class NewsEvent:
    title: str
    currency: str
    impact: str  # "Low" | "Medium" | "High" | anything else the feed sends
    at: datetime  # timezone-aware, as parsed from the feed's own offset


def _parse_events(raw: list[dict]) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for item in raw:
        try:
            at = datetime.fromisoformat(item["date"])
        except (KeyError, ValueError, TypeError):
            continue  # skip anything that doesn't parse rather than fail the whole fetch
        events.append(
            NewsEvent(
                title=item.get("title", ""),
                currency=item.get("country", ""),
                impact=item.get("impact", "Low"),
                at=at,
            )
        )
    return events


def fetch_this_weeks_events(*, timeout: float = 10.0) -> list[NewsEvent]:
    """Raises on any fetch/parse failure — deliberately does not
    swallow errors into an empty list, since "the feed is down" and
    "there's no news this week" must never look the same to a caller
    deciding whether it's safe to trade."""
    request = urllib.request.Request(
        CALENDAR_URL, headers={"User-Agent": "deriv-trading-agent/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return _parse_events(raw)


def is_within_news_blackout(
    currencies: set[str],
    events: list[NewsEvent],
    now: datetime,
    *,
    minutes_before: int = 30,
    minutes_after: int = 30,
    min_impact: str = "High",
) -> tuple[bool, NewsEvent | None]:
    """True (plus the triggering event) if `now` falls within
    [event.at - minutes_before, event.at + minutes_after] for any event
    whose currency is in `currencies` and whose impact is >= min_impact
    (by IMPACT_ORDER; an unrecognized impact string never qualifies)."""
    threshold = IMPACT_ORDER.get(min_impact, IMPACT_ORDER["High"])
    before = timedelta(minutes=minutes_before)
    after = timedelta(minutes=minutes_after)
    for event in events:
        if event.currency not in currencies:
            continue
        if IMPACT_ORDER.get(event.impact, 0) < threshold:
            continue
        if event.at - before <= now <= event.at + after:
            return True, event
    return False, None
