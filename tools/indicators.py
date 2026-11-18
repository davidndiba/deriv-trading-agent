"""Pure-Python indicators. No pandas/numpy/pydantic dependency — keeps this
module importable and testable on its own, without the rest of the stack."""
from __future__ import annotations

from typing import Protocol


class _OHLC(Protocol):
    high: float
    low: float
    close: float


def ema(values: list[float], period: int) -> list[float]:
    """Standard exponential moving average, seeded with the first value."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI. First `period` entries are None (not enough history)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(values)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, n):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)

    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def true_range(prev_close: float, high: float, low: float) -> float:
    return max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close),
    )


def atr(candles: list[_OHLC], period: int = 14) -> list[float | None]:
    """Wilder's ATR. First `period` entries are None (not enough history)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(candles)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    trs = [
        true_range(candles[i - 1].close, candles[i].high, candles[i].low)
        for i in range(1, n)
    ]
    # trs[i] corresponds to candles[i+1]
    first_atr = sum(trs[:period]) / period
    out[period] = first_atr
    prev_atr = first_atr
    for i in range(period, len(trs)):
        prev_atr = (prev_atr * (period - 1) + trs[i]) / period
        out[i + 1] = prev_atr

    return out
