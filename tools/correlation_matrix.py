"""Real price-correlation matrix between symbols, computed from
historical returns — the measured number docs/DECISIONS.md flagged as a
reasonable future improvement over tools/exposure.py's currency-overlap
heuristic. Pure Python, no dependency.

This is a standalone analysis tool for now
(scripts/run_phase17_correlation_matrix.py computes, prints, and logs
it). It is NOT wired into the live Phase 4/5 correlation guard, which
still uses the currency-overlap heuristic — see docs/DECISIONS.md for
why adopting it there is a separate decision from building it.
"""
from __future__ import annotations

from typing import Protocol


class _HasClose(Protocol):
    close: float


def simple_returns(closes: list[float]) -> list[float]:
    """Period-over-period simple returns: (close[i] - close[i-1]) /
    close[i-1]. A zero-price bar is skipped (division by zero) rather
    than raising — shouldn't happen with real price data, but this
    keeps a single bad tick from killing the whole computation."""
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]


def pearson_correlation(a: list[float], b: list[float]) -> float:
    """Standard Pearson correlation coefficient, in [-1, 1]. Requires
    len(a) == len(b) >= 2. Returns 0.0 if either series has zero
    variance (a constant series has no meaningful correlation with
    anything, and dividing by a zero stddev would otherwise raise)."""
    n = len(a)
    if n != len(b) or n < 2:
        raise ValueError("a and b must be the same length and have >= 2 points")
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / (var_a**0.5 * var_b**0.5)


def build_correlation_matrix(
    returns_by_symbol: dict[str, list[float]]
) -> dict[tuple[str, str], float]:
    """Pairwise Pearson correlation for every symbol pair. Assumes each
    symbol's return series is already aligned — same length, same
    underlying time steps — which is the caller's job (e.g. pulling the
    same candle count/granularity for every symbol at the same time).
    Keys are (symbol_a, symbol_b) with symbol_a < symbol_b
    alphabetically, so each pair appears exactly once; use
    get_correlation() to look a pair up regardless of order."""
    symbols = sorted(returns_by_symbol.keys())
    matrix: dict[tuple[str, str], float] = {}
    for i, sym_a in enumerate(symbols):
        for sym_b in symbols[i + 1 :]:
            matrix[(sym_a, sym_b)] = pearson_correlation(
                returns_by_symbol[sym_a], returns_by_symbol[sym_b]
            )
    return matrix


def get_correlation(
    matrix: dict[tuple[str, str], float], symbol_a: str, symbol_b: str
) -> float | None:
    """Looks a pair up regardless of which order build_correlation_matrix
    stored it in. None if the pair isn't in the matrix at all — this is
    deliberately NOT `matrix.get(a, b) or matrix.get(b, a)`, since a
    real (and valid) correlation of exactly 0.0 is falsy and would make
    that pattern wrongly fall through to the second lookup."""
    if symbol_a == symbol_b:
        return 1.0
    if (symbol_a, symbol_b) in matrix:
        return matrix[(symbol_a, symbol_b)]
    if (symbol_b, symbol_a) in matrix:
        return matrix[(symbol_b, symbol_a)]
    return None


def correlated_by_matrix(
    candidate_symbol: str,
    candidate_direction: str,
    open_trades: list[tuple[str, str]],
    matrix: dict[tuple[str, str], float],
    *,
    threshold: float = 0.7,
) -> list[str]:
    """Open trades whose measured |correlation| with candidate_symbol is
    >= threshold AND whose direction implies stacked exposure: same
    direction for a positive correlation (e.g. two pairs that tend to
    move together), opposite direction for a negative one (e.g. a short
    on a pair that tends to move opposite the candidate is effectively
    the same bet as a long on the candidate). This is the nuance the
    currency-overlap heuristic in tools/exposure.py can't capture — it
    only ever treats same-direction + shared currency as correlated."""
    matches = []
    for symbol, direction in open_trades:
        if symbol == candidate_symbol:
            continue
        corr = get_correlation(matrix, candidate_symbol, symbol)
        if corr is None or abs(corr) < threshold:
            continue
        same_side = direction == candidate_direction
        if (corr > 0 and same_side) or (corr < 0 and not same_side):
            matches.append(symbol)
    return matches
