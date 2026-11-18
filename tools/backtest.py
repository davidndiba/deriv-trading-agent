"""Walk-forward backtest engine. Pure Python, no pandas/numpy/pydantic
dependency — same reasoning as tools/indicators.py: keeps it directly
testable in any environment, including this one.

Lookahead safety: at bar i, the signal function is only ever given
candles[:i+1] (everything up to and including bar i's close) — never a
later bar. Only the *outcome* of a trade opened at bar i looks forward,
which is simulation, not lookahead.

Per docs/SPEC.md Phase 2: "a backtested win rate above ~70% on a simple
signal is almost always a lookahead/data bug — stop and audit, don't
proceed." See WIN_RATE_AUDIT_THRESHOLD below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from tools.strategy_params import ATR_STOP_MULTIPLE, REWARD_RISK_RATIO

WIN_RATE_AUDIT_THRESHOLD = 0.70
MIN_CLOSED_TRADES_FOR_AUDIT = 10


class _OHLC(Protocol):
    high: float
    low: float
    close: float


class _SignalLike(Protocol):
    entry_price: float
    atr: float
    # direction is either a plain "UP"/"DOWN" string or anything with a
    # `.value` attribute equal to one of those (e.g. schemas.models.Direction)
    direction: object


def _direction_str(direction: object) -> str:
    value = getattr(direction, "value", direction)
    if value not in ("UP", "DOWN"):
        raise ValueError(f"direction must resolve to 'UP' or 'DOWN', got {value!r}")
    return value


@dataclass
class TradeResult:
    symbol: str
    entry_index: int
    exit_index: int
    direction: str
    entry_price: float
    exit_price: float
    stop_loss_price: float
    take_profit_price: float
    outcome: str  # "win" | "loss" | "open_at_end"
    r_multiple: Optional[float]  # None when outcome == "open_at_end"


def simulate_trade(
    candles: list[_OHLC],
    symbol: str,
    entry_index: int,
    direction: str,
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    reward_risk_ratio: float,
) -> TradeResult:
    """Walk forward from entry_index+1 until stop-loss or take-profit is
    touched. If a single bar's high/low range touches both levels, this
    conservatively assumes the stop-loss was hit first (we can't know the
    intrabar order from OHLC alone, and assuming the best case would bias
    results exactly the way the Phase 2 audit rule warns about)."""
    for i in range(entry_index + 1, len(candles)):
        c = candles[i]
        if direction == "UP":
            hit_tp = c.high >= take_profit_price
            hit_sl = c.low <= stop_loss_price
        else:
            hit_tp = c.low <= take_profit_price
            hit_sl = c.high >= stop_loss_price

        if hit_sl:
            return TradeResult(
                symbol=symbol,
                entry_index=entry_index,
                exit_index=i,
                direction=direction,
                entry_price=entry_price,
                exit_price=stop_loss_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                outcome="loss",
                r_multiple=-1.0,
            )
        if hit_tp:
            return TradeResult(
                symbol=symbol,
                entry_index=entry_index,
                exit_index=i,
                direction=direction,
                entry_price=entry_price,
                exit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                outcome="win",
                r_multiple=reward_risk_ratio,
            )

    last = candles[-1]
    return TradeResult(
        symbol=symbol,
        entry_index=entry_index,
        exit_index=len(candles) - 1,
        direction=direction,
        entry_price=entry_price,
        exit_price=last.close,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        outcome="open_at_end",
        r_multiple=None,
    )


def backtest_symbol(
    symbol: str,
    candles: list[_OHLC],
    signal_fn: Callable[[str, list], Optional[_SignalLike]],
    *,
    stop_multiple: float = ATR_STOP_MULTIPLE,
    reward_risk_ratio: float = REWARD_RISK_RATIO,
) -> list[TradeResult]:
    """One trade at a time: once a trade is opened, no new signal is
    considered until it closes (matches "no correlation/concurrency"
    simplicity of Phase 1/2; concurrency limits are a Phase 4 concern)."""
    trades: list[TradeResult] = []
    i = 0
    while i < len(candles):
        window = candles[: i + 1]
        signal = signal_fn(symbol, window)
        if signal is None:
            i += 1
            continue

        direction = _direction_str(signal.direction)
        entry_price = signal.entry_price
        stop_loss_pct = (stop_multiple * signal.atr) / entry_price
        take_profit_pct = stop_loss_pct * reward_risk_ratio

        if direction == "UP":
            stop_loss_price = entry_price * (1 - stop_loss_pct)
            take_profit_price = entry_price * (1 + take_profit_pct)
        else:
            stop_loss_price = entry_price * (1 + stop_loss_pct)
            take_profit_price = entry_price * (1 - take_profit_pct)

        result = simulate_trade(
            candles,
            symbol,
            i,
            direction,
            entry_price,
            stop_loss_price,
            take_profit_price,
            reward_risk_ratio,
        )
        trades.append(result)
        i = result.exit_index + 1

    return trades


@dataclass
class BacktestReport:
    symbol: str
    total_signals: int
    closed_trades: int
    open_at_end: int
    wins: int
    losses: int
    win_rate: float
    avg_r_multiple: float
    max_drawdown_r: float
    needs_audit: bool  # win_rate > WIN_RATE_AUDIT_THRESHOLD on enough trades


def summarize(symbol: str, trades: list[TradeResult]) -> BacktestReport:
    closed = [t for t in trades if t.outcome != "open_at_end"]
    wins = [t for t in closed if t.outcome == "win"]
    losses = [t for t in closed if t.outcome == "loss"]

    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_r = sum(t.r_multiple for t in closed) / len(closed) if closed else 0.0

    cum = 0.0
    peak = float("-inf")
    max_dd = 0.0
    for t in closed:
        cum += t.r_multiple
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    needs_audit = (
        len(closed) >= MIN_CLOSED_TRADES_FOR_AUDIT
        and win_rate > WIN_RATE_AUDIT_THRESHOLD
    )

    return BacktestReport(
        symbol=symbol,
        total_signals=len(trades),
        closed_trades=len(closed),
        open_at_end=len(trades) - len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        avg_r_multiple=avg_r,
        max_drawdown_r=max_dd,
        needs_audit=needs_audit,
    )
