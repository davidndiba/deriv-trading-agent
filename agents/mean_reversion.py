"""A second, independently backtested signal: Bollinger Band fade,
filtered by RSI and an ATR volatility band — the opposite style from
agents/signals.py's trend-following EMA crossover.

Direction: when price closes outside a Bollinger Band AND RSI confirms
the extreme, bet on reversion back toward the mean (fade the move, don't
chase it) — the reverse of signals.py's "only take the crossover if RSI
isn't already extreme in that direction."

This does not replace agents/signals.py's signal. It's a separate
strategy with its own backtest (scripts/run_phase10_mean_reversion_backtest.py);
nothing adopts it into Phase 3-5's live/demo trading automatically — see
docs/DECISIONS.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from schemas.models import Candle, Direction, Signal
from tools.indicators import atr, bollinger_bands, rsi


@dataclass(frozen=True)
class MeanReversionConfig:
    bb_period: int = 20
    bb_num_std: float = 2.0
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    min_atr_pct: float = 0.0005
    max_atr_pct: float = 0.05


def generate_mean_reversion_signal(
    symbol: str,
    candles: list[Candle],
    config: MeanReversionConfig | None = None,
) -> Signal | None:
    config = config or MeanReversionConfig()
    min_len = max(config.bb_period, config.rsi_period, config.atr_period) + 1
    if len(candles) < min_len:
        return None

    closes = [c.close for c in candles]
    _, upper, lower = bollinger_bands(closes, config.bb_period, config.bb_num_std)
    rsi_vals = rsi(closes, config.rsi_period)
    atr_vals = atr(candles, config.atr_period)

    last_upper = upper[-1]
    last_lower = lower[-1]
    last_rsi = rsi_vals[-1]
    last_atr = atr_vals[-1]
    if last_upper is None or last_lower is None or last_rsi is None or last_atr is None:
        return None

    last_close = closes[-1]
    atr_pct = last_atr / last_close
    if not (config.min_atr_pct <= atr_pct <= config.max_atr_pct):
        return None

    if last_close > last_upper and last_rsi > config.rsi_overbought:
        return Signal(
            symbol=symbol,
            direction=Direction.DOWN,
            entry_price=last_close,
            atr=last_atr,
            reason=(
                f"close above upper BB({config.bb_period},{config.bb_num_std}), "
                f"RSI={last_rsi:.1f} overbought -> fade down"
            ),
        )

    if last_close < last_lower and last_rsi < config.rsi_oversold:
        return Signal(
            symbol=symbol,
            direction=Direction.UP,
            entry_price=last_close,
            atr=last_atr,
            reason=(
                f"close below lower BB({config.bb_period},{config.bb_num_std}), "
                f"RSI={last_rsi:.1f} oversold -> fade up"
            ),
        )

    return None
