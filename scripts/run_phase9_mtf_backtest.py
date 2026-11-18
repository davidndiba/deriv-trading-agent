"""Phase 9: does a higher-timeframe trend filter actually help?

Runs the existing Phase 1 signal both with and without multi-timeframe
confirmation (tools/multi_timeframe.py, agents/signals.py::
generate_confirmed_signal) through the same backtest engine from Phase
2/7, and prints both reports side by side per symbol.

This is deliberately a comparison, not a swap: nothing here changes
what scripts/run_phase{3,4,5}_*.py actually trade. Whether to adopt the
HTF filter into those scripts is a decision to make after looking at
this comparison, not something this script decides for you — see
docs/DECISIONS.md.

No `buy`/`sell`/`proposal` call exists anywhere in this script. Refuses
ENV=live — same as every other backtest-only script.
"""
from __future__ import annotations

import asyncio
import sys

from agents.signals import generate_confirmed_signal, generate_signal
from config.settings import Settings, load_settings
from storage.db import get_connection, log_backtest_result
from tools.backtest import backtest_symbol, summarize
from tools.deriv_client import DerivClient, parse_candles
from tools.strategy_params import get_strategy_params

LTF_CANDLE_COUNT = 5000
LTF_GRANULARITY_SECONDS = 60  # 1-minute
HTF_CANDLE_COUNT = 2000
HTF_GRANULARITY_SECONDS = 900  # 15-minute — comfortably covers the 1m window's history


def _print_report(report) -> None:
    print(
        f"  {report.label:<22} closed={report.closed_trades:<4} "
        f"win_rate={report.win_rate:.1%}  avg_R={report.avg_r_multiple:.2f}  "
        f"max_drawdown_R={report.max_drawdown_r:.2f}"
    )
    if report.needs_audit:
        print(f"    *** {report.label}: win rate above 70% — stop and audit ***")


async def run(settings: Settings) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 9 is backtesting only — refusing to run with ENV=live."
        )

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    try:
        for symbol in settings.symbols:
            ltf_response = await client.get_ticks_history(
                symbol, count=LTF_CANDLE_COUNT, granularity=LTF_GRANULARITY_SECONDS
            )
            htf_response = await client.get_ticks_history(
                symbol, count=HTF_CANDLE_COUNT, granularity=HTF_GRANULARITY_SECONDS
            )
            ltf_candles = parse_candles(ltf_response)
            htf_candles = parse_candles(htf_response)

            stop_multiple, reward_risk_ratio = get_strategy_params(symbol)

            baseline_trades = backtest_symbol(
                symbol, ltf_candles, generate_signal,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
            )
            baseline_report = summarize(symbol, baseline_trades, label="baseline (no HTF)")

            def confirmed_signal_fn(sym: str, window: list):
                return generate_confirmed_signal(sym, window, htf_candles)

            confirmed_trades = backtest_symbol(
                symbol, ltf_candles, confirmed_signal_fn,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
            )
            confirmed_report = summarize(symbol, confirmed_trades, label="HTF-confirmed")

            log_backtest_result(conn, len(ltf_candles), baseline_report)
            log_backtest_result(conn, len(ltf_candles), confirmed_report)

            print(f"[{symbol}] {len(ltf_candles)} 1m candles, {len(htf_candles)} 15m candles")
            _print_report(baseline_report)
            _print_report(confirmed_report)
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
