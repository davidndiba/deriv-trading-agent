"""Correlation/concurrency risk guards. Pure Python, no deps — same
reasoning as tools/indicators.py and tools/backtest.py.

Per docs/SPEC.md Phase 4: "correlation checks (don't go long 3 USD pairs
at once and call it diversification)."
"""
from __future__ import annotations

_FOREX_SYMBOL_PREFIX = "frx"


def currency_exposure(symbol: str) -> frozenset[str]:
    """Best-effort currency codes implied by a Deriv forex symbol, e.g.
    'frxEURUSD' -> {'EUR', 'USD'}. Non-forex symbols (gold, synthetic
    indices, ...) return a singleton of the symbol itself, so they only
    ever "correlate" with another position in that exact same symbol.
    """
    if symbol.startswith(_FOREX_SYMBOL_PREFIX) and len(symbol) == len(_FOREX_SYMBOL_PREFIX) + 6:
        rest = symbol[len(_FOREX_SYMBOL_PREFIX):]
        base, quote = rest[:3], rest[3:]
        return frozenset({base, quote})
    return frozenset({symbol})


def is_correlated(symbol_a: str, symbol_b: str) -> bool:
    return bool(currency_exposure(symbol_a) & currency_exposure(symbol_b))


def correlated_open_symbols(
    candidate_symbol: str,
    candidate_direction: str,
    open_trades: list[tuple[str, str]],  # (symbol, direction) pairs
) -> list[str]:
    """Open trades that share a currency with candidate_symbol AND are
    in the same direction — e.g. already long EUR/USD and about to go
    long GBP/USD too (both effectively "long USD-adjacent")."""
    candidate_currencies = currency_exposure(candidate_symbol)
    matches = []
    for symbol, direction in open_trades:
        if direction != candidate_direction:
            continue
        if currency_exposure(symbol) & candidate_currencies:
            matches.append(symbol)
    return matches
