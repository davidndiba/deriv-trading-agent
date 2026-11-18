"""2-signal strategy: EMA(fast)/EMA(slow) crossover, filtered by RSI
(don't chase an already-overbought/oversold move) and an ATR volatility
band (skip dead markets and skip extreme-spike markets).

Deliberately just one combined signal, per docs/SPEC.md Phase 1: "2-3
signals max... don't add ten indicators before one works."
"""
from __future__ import annotations

from dataclasses import dataclass

from schemas.models import Candle, Direction, Signal
from tools.indicators import atr, ema, rsi
from tools.multi_timeframe import build_htf_trend_lookup, lookup_htf_trend


@dataclass(frozen=True)
class SignalConfig:
    ema_fast: int = 12
    ema_slow: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    min_atr_pct: float = 0.0005
    max_atr_pct: float = 0.05


def generate_signal(
    symbol: str,
    candles: list[Candle],
    config: SignalConfig | None = None,
) -> Signal | None:
    config = config or SignalConfig()
    min_len = max(config.ema_slow, config.rsi_period, config.atr_period) + 2
    if len(candles) < min_len:
        return None

    closes = [c.close for c in candles]
    ema_fast = ema(closes, config.ema_fast)
    ema_slow = ema(closes, config.ema_slow)
    rsi_vals = rsi(closes, config.rsi_period)
    atr_vals = atr(candles, config.atr_period)

    last_rsi = rsi_vals[-1]
    last_atr = atr_vals[-1]
    if last_rsi is None or last_atr is None:
        return None

    last_close = closes[-1]
    atr_pct = last_atr / last_close
    if not (config.min_atr_pct <= atr_pct <= config.max_atr_pct):
        return None

    prev_diff = ema_fast[-2] - ema_slow[-2]
    curr_diff = ema_fast[-1] - ema_slow[-1]
    crossed_up = prev_diff <= 0 and curr_diff > 0
    crossed_down = prev_diff >= 0 and curr_diff < 0

    if crossed_up and last_rsi < config.rsi_overbought:
        return Signal(
            symbol=symbol,
            direction=Direction.UP,
            entry_price=last_close,
            atr=last_atr,
            reason=(
                f"EMA{config.ema_fast}/{config.ema_slow} crossed up, "
                f"RSI={last_rsi:.1f}, ATR%={atr_pct:.3%}"
            ),
        )

    if crossed_down and last_rsi > config.rsi_oversold:
        return Signal(
            symbol=symbol,
            direction=Direction.DOWN,
            entry_price=last_close,
            atr=last_atr,
            reason=(
                f"EMA{config.ema_fast}/{config.ema_slow} crossed down, "
                f"RSI={last_rsi:.1f}, ATR%={atr_pct:.3%}"
            ),
        )

    return None


def generate_confirmed_signal(
    symbol: str,
    candles: list[Candle],
    htf_candles: list[Candle],
    config: SignalConfig | None = None,
    htf_ema_period: int = 50,
) -> Signal | None:
    """generate_signal(), additionally requiring a higher-timeframe trend
    (tools/multi_timeframe.py) to agree with the signal's own direction.

    This is a separate function rather than a change to generate_signal()
    itself — every Phase 1-8 script/backtest calls generate_signal() with
    exactly (symbol, window), and changing its signature or behavior
    would silently change what every one of those already-verified
    phases does. This is purely additive; nothing adopts it automatically
    — see docs/DECISIONS.md and scripts/run_phase9_mtf_backtest.py.
    """
    base_signal = generate_signal(symbol, candles, config)
    if base_signal is None:
        return None

    epochs, trends = build_htf_trend_lookup(htf_candles, ema_period=htf_ema_period)
    htf_trend = lookup_htf_trend(epochs, trends, candles[-1].epoch)
    if htf_trend is None or htf_trend != base_signal.direction.value:
        return None

    return base_signal.model_copy(
        update={"reason": base_signal.reason + f"; HTF trend confirms {htf_trend}"}
    )
