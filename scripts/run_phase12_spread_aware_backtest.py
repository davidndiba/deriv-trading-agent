"""Phase 12: how much does realistic spread cost change the backtest?

tools/backtest.py's spread_pct models a real fill price slightly worse
than the signal's quoted entry_price (see its docstring for exactly how
the stop-loss/take-profit barriers shift). Every backtest script before
this one (Phase 2, 7, 9, 10) calls it with spread_pct=0.0 (the default),
i.e. frictionless — this script is the first to turn it on, and only to
compare, not to replace those earlier numbers.

ASSUMED_SPREAD_PCT below is a placeholder starting point, not a number
sourced from Deriv's own published spread data for any symbol — nobody
verified this against a real account in this sandbox (same limitation
as every live-API-touching phase). Replace it with whatever you actually
observe on your symbols before trusting this comparison's magnitude; the
mechanism (which barrier it moves and which direction) is what's been
verified, not this specific number.

No `buy`/`sell`/`proposal` call exists anywhere in this script. Refuses
ENV=live, same as every other backtest-only script.
"""
from __future__ import annotations

import asyncio
import sys

from agents.signals import generate_signal
from config.settings import Settings, load_settings
from storage.db import get_connection, log_backtest_result
from tools.backtest import backtest_symbol, summarize
from tools.deriv_client import DerivClient, parse_candles
from tools.strategy_params import get_strategy_params

CANDLE_COUNT = 5000
GRANULARITY_SECONDS = 60

# Placeholder assumption — see the module docstring. 0.0002 = 0.02%.
ASSUMED_SPREAD_PCT = 0.0002


def _print_report(report) -> None:
    print(
        f"  {report.label:<28} closed={report.closed_trades:<4} "
        f"win_rate={report.win_rate:.1%}  avg_R={report.avg_r_multiple:.2f}  "
        f"max_drawdown_R={report.max_drawdown_r:.2f}"
    )
    if report.needs_audit:
        print(f"    *** {report.label}: win rate above 70% — stop and audit ***")


async def run(settings: Settings) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 12 is backtesting only — refusing to run with ENV=live."
        )

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    try:
        for symbol in settings.symbols:
            response = await client.get_ticks_history(
                symbol, count=CANDLE_COUNT, granularity=GRANULARITY_SECONDS
            )
            candles = parse_candles(response)
            stop_multiple, reward_risk_ratio = get_strategy_params(symbol)

            frictionless_trades = backtest_symbol(
                symbol, candles, generate_signal,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
                spread_pct=0.0,
            )
            frictionless_report = summarize(symbol, frictionless_trades, label="frictionless (as Phase 2)")

            spread_trades = backtest_symbol(
                symbol, candles, generate_signal,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
                spread_pct=ASSUMED_SPREAD_PCT,
            )
            spread_report = summarize(
                symbol, spread_trades, label=f"spread-adjusted ({ASSUMED_SPREAD_PCT:.3%})"
            )

            log_backtest_result(conn, len(candles), frictionless_report)
            log_backtest_result(conn, len(candles), spread_report)

            print(f"[{symbol}] {len(candles)} candles")
            _print_report(frictionless_report)
            _print_report(spread_report)
            print()
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
