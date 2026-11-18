"""Phase 17: measured price correlation between the configured symbols,
replacing a guess with an actual number.

Standalone analysis — prints and logs the matrix, same pattern as the
backtest scripts. It is NOT wired into the live Phase 4/5 correlation
guard, which still uses tools/exposure.py's currency-overlap heuristic;
see docs/DECISIONS.md for why that's a separate decision from building
this.

Read-only with respect to the account (only `ticks_history`, same as
every backtest script) — safe to run against demo or live, so unlike
the trading scripts this one does NOT refuse ENV=live.
"""
from __future__ import annotations

import asyncio
import sys

from config.settings import Settings, load_settings
from storage.db import get_connection, log_correlation_matrix
from tools.correlation_matrix import build_correlation_matrix, simple_returns
from tools.deriv_client import DerivClient, parse_candles

CANDLE_COUNT = 500
GRANULARITY_SECONDS = 60
HIGH_CORRELATION_THRESHOLD = 0.7


async def run(settings: Settings) -> None:
    if len(settings.symbols) < 2:
        print("Need at least 2 symbols configured to compute a correlation matrix.")
        return

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    try:
        returns_by_symbol: dict[str, list[float]] = {}
        for symbol in settings.symbols:
            response = await client.get_ticks_history(
                symbol, count=CANDLE_COUNT, granularity=GRANULARITY_SECONDS
            )
            candles = parse_candles(response)
            returns_by_symbol[symbol] = simple_returns([c.close for c in candles])

        # All symbols were pulled with the same count/granularity, but
        # trim to the shortest return series anyway in case any symbol
        # returned fewer candles than requested (thin trading hours,
        # partial history) — build_correlation_matrix requires equal
        # lengths and would otherwise raise.
        min_len = min(len(r) for r in returns_by_symbol.values())
        if min_len < 2:
            print("Not enough historical data to compute a correlation matrix.")
            return
        aligned = {symbol: returns[-min_len:] for symbol, returns in returns_by_symbol.items()}

        matrix = build_correlation_matrix(aligned)
        log_correlation_matrix(conn, min_len, matrix)

        print(f"Correlation matrix over {min_len} aligned returns ({GRANULARITY_SECONDS}s candles):\n")
        for (symbol_a, symbol_b), correlation in sorted(matrix.items(), key=lambda kv: -abs(kv[1])):
            flag = " *** HIGH ***" if abs(correlation) >= HIGH_CORRELATION_THRESHOLD else ""
            print(f"  {symbol_a:<12} {symbol_b:<12} {correlation:+.3f}{flag}")

        high = {k: v for k, v in matrix.items() if abs(v) >= HIGH_CORRELATION_THRESHOLD}
        if high:
            print(
                f"\n{len(high)} pair(s) at or above |{HIGH_CORRELATION_THRESHOLD}| — "
                "these move together (or opposite) closely enough that "
                "holding both is closer to one bet than two."
            )
        else:
            print(f"\nNo pairs at or above |{HIGH_CORRELATION_THRESHOLD}|.")
    finally:
        await client.disconnect()
        conn.close()


def main() -> None:
    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
