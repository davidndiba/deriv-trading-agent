"""Builds a text/markdown performance report from closed trades. Pure
Python, no dependency — operates on plain dicts (as storage/db.py's
_rows_as_dicts returns), not pydantic models, so this stays directly
testable and doesn't care whether its caller used the API layer or a
raw SQL row.
"""
from __future__ import annotations

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """A one-line ASCII/unicode sparkline of an equity curve. Empty
    string for no data; a single repeated character for a flat line
    (every value identical) rather than dividing by zero."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return _SPARK_CHARS[0] * len(values)
    span = hi - lo
    last = len(_SPARK_CHARS) - 1
    return "".join(
        _SPARK_CHARS[min(last, int((v - lo) / span * last))] for v in values
    )


def build_performance_report(trades: list[dict], period_label: str) -> str:
    """trades: dicts with at least 'symbol', 'profit', 'status',
    'closed_at' — exactly storage.db's trade row shape. Assumed already
    sorted chronologically by closed_at (storage.db.get_trades_closed_since
    does this); this function does not re-sort, so a caller passing
    unsorted trades gets an equity curve in whatever order it gave them.
    """
    lines = [f"# {period_label}", ""]

    if not trades:
        lines.append("No closed trades in this period.")
        return "\n".join(lines)

    wins = [t for t in trades if t["status"] == "won"]
    losses = [t for t in trades if t["status"] == "lost"]
    total_profit = sum(t.get("profit") or 0.0 for t in trades)
    win_rate = len(wins) / len(trades) if trades else 0.0

    equity_curve = []
    running = 0.0
    for t in trades:
        running += t.get("profit") or 0.0
        equity_curve.append(running)

    lines.append(f"- Closed trades: {len(trades)}  (wins {len(wins)}, losses {len(losses)})")
    lines.append(f"- Win rate: {win_rate:.1%}")
    lines.append(f"- Total P&L: ${total_profit:.2f}")
    lines.append(f"- Equity curve: `{sparkline(equity_curve)}`")
    lines.append("")

    by_symbol: dict[str, list[dict]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    lines.append("## By symbol")
    for symbol, symbol_trades in sorted(by_symbol.items()):
        symbol_profit = sum(t.get("profit") or 0.0 for t in symbol_trades)
        symbol_wins = sum(1 for t in symbol_trades if t["status"] == "won")
        lines.append(
            f"- {symbol}: {len(symbol_trades)} trades, "
            f"{symbol_wins}/{len(symbol_trades)} won, ${symbol_profit:.2f}"
        )

    return "\n".join(lines)
