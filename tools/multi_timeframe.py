"""Higher-timeframe trend lookup, for confirming a lower-timeframe signal
against the prevailing trend on a slower chart. Pure Python, no
dependency (not even schemas.models — trend direction comes back as the
plain string 'UP'/'DOWN', not the Direction enum, so this stays
importable without pydantic; agents/signals.py converts at the edge).

Lookahead safety: lookup_htf_trend only ever considers HTF candles whose
epoch is <= the as-of epoch — never a later HTF candle, even one that
closed before the lower-timeframe bar in question but after the instant
being evaluated would make sense chronologically. This mirrors the
lookahead rule in tools/backtest.py.
"""
from __future__ import annotations

import bisect
from typing import Protocol

from tools.indicators import ema  # also dependency-free, so this import is safe


class _OHLCWithEpoch(Protocol):
    epoch: int
    close: float


def build_htf_trend_lookup(
    htf_candles: list[_OHLCWithEpoch], ema_period: int = 50
) -> tuple[list[int], list[str | None]]:
    """Precomputes a trend label ('UP'/'DOWN'/None) per HTF candle —
    'UP' if that candle's close is above its own EMA(ema_period), 'DOWN'
    if below, None if exactly equal or not enough history yet for that
    candle's EMA value to mean anything. Returns (epochs, trends),
    parallel lists sorted by epoch (ticks_history already returns
    candles in chronological order), for lookup_htf_trend's bisect."""
    closes = [c.close for c in htf_candles]
    ema_vals = ema(closes, ema_period) if closes else []
    epochs = [c.epoch for c in htf_candles]

    trends: list[str | None] = []
    for i, close in enumerate(closes):
        if i < ema_period:
            trends.append(None)
        elif close > ema_vals[i]:
            trends.append("UP")
        elif close < ema_vals[i]:
            trends.append("DOWN")
        else:
            trends.append(None)
    return epochs, trends


def lookup_htf_trend(epochs: list[int], trends: list[str | None], as_of_epoch: int) -> str | None:
    """The trend label of the most recent HTF candle with epoch <=
    as_of_epoch. None if as_of_epoch is before every HTF candle on
    record (no history yet to judge a trend from)."""
    idx = bisect.bisect_right(epochs, as_of_epoch) - 1
    if idx < 0:
        return None
    return trends[idx]
