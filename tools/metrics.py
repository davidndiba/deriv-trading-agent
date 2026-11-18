"""Risk-adjusted performance metrics computed from a return series —
either dollar profits from closed trades, or R-multiples from a
backtest. Pure Python, no dependency.

These are NOT annualized. A backtest's trades and a day's closed trades
don't happen on any fixed schedule, so annualizing would mean guessing a
trades-per-year figure this module has no business inventing — these
report the raw per-trade ratio, which is what a profit-factor/Sharpe
number computed from an uneven, irregularly-timed trade sequence
actually is.
"""
from __future__ import annotations


def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Mean excess return / population stddev of returns. 0.0 if fewer
    than two returns or if returns have zero variance (can't divide by
    a zero stddev; a flat series has no meaningful ratio either way)."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((x - mean) ** 2 for x in excess) / len(excess)
    stddev = variance**0.5
    if stddev == 0:
        return 0.0
    return mean / stddev


def sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Like sharpe_ratio, but only downside deviation (excess returns
    below zero) counts against it — an upside-heavy series with a few
    big losers scores worse here than Sharpe would show, which is the
    point of using Sortino at all."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    downside = [min(0.0, x) for x in excess]
    downside_variance = sum(d**2 for d in downside) / len(excess)
    downside_dev = downside_variance**0.5
    if downside_dev == 0:
        return 0.0
    return mean / downside_dev


def profit_factor(returns: list[float]) -> float:
    """Gross profit / gross loss. float('inf') if there's profit and no
    losses at all; 0.0 if there's no profit (including an empty or
    all-zero series)."""
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = -sum(r for r in returns if r < 0)
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def max_consecutive_losses(returns: list[float]) -> int:
    """Longest streak of strictly-negative returns in sequence order. A
    zero return is ignored — it neither extends nor breaks a streak in
    progress (it's not a loss, but it's not a recovery either); only a
    strictly positive return resets the counter to zero."""
    worst = 0
    current = 0
    for r in returns:
        if r < 0:
            current += 1
            worst = max(worst, current)
        elif r > 0:
            current = 0
    return worst
