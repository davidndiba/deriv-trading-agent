"""Phase 2 entry point: backtest the Phase 1 signal against historical
`ticks_history` data per symbol, before touching a live tick.

No `buy`/`sell`/`proposal` call exists anywhere in this script or the
modules it imports. Refuses to run with ENV=live, same as Phase 1 — this
phase never needs a live session at all, demo is used purely as a
historical-data source.
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
GRANULARITY_SECONDS = 60  # 1-minute candles


async def run(settings: Settings) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 2 is backtesting only — refusing to run with ENV=live."
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
            trades = backtest_symbol(
                symbol, candles, generate_signal,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
            )
            report = summarize(symbol, trades)
            log_backtest_result(conn, len(candles), report)

            print(f"[{symbol}] candles={len(candles)}  signals={report.total_signals}")
            print(
                f"  closed={report.closed_trades}  wins={report.wins}  "
                f"losses={report.losses}  open_at_end={report.open_at_end}"
            )
            print(
                f"  win_rate={report.win_rate:.1%}  "
                f"avg_R={report.avg_r_multiple:.2f}  "
                f"max_drawdown_R={report.max_drawdown_r:.2f}"
            )
            if report.needs_audit:
                print(
                    "  *** STOP AND AUDIT: win rate above ~70% on a simple "
                    "signal is almost always a lookahead/data bug. Do not "
                    "proceed to Phase 3 on this result without checking "
                    "for lookahead bias first. ***"
                )
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
