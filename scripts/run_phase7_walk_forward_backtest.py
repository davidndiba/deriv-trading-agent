"""Phase 7: walk-forward (per-fold) backtest validation.

docs/SPEC.md's Phase 2 backtests on one historical window. This splits
that same history into chronological folds and reports each fold
separately, so a signal that only "worked" during one stretch of history
is visible as exactly that, instead of being averaged away into one
aggregate number. There is no parameter-fitting step anywhere in this
codebase, so this isn't train/test in the ML sense — see
tools/backtest.py::walk_forward_report for what it actually checks.

No `buy`/`sell`/`proposal` call exists anywhere in this script. Refuses
ENV=live, same as every other non-trading script — the demo account is
only ever used here as a historical-data source.
"""
from __future__ import annotations

import asyncio
import sys

import _bootstrap  # noqa: F401
from agents.signals import generate_signal
from config.settings import Settings, load_settings
from storage.db import get_connection, log_backtest_result
from tools.backtest import walk_forward_report
from tools.deriv_client import DerivClient, parse_candles
from tools.strategy_params import get_strategy_params

CANDLE_COUNT = 5000
GRANULARITY_SECONDS = 60
N_FOLDS = 4


async def run(settings: Settings) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 7 is backtesting only — refusing to run with ENV=live."
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
            reports = walk_forward_report(
                symbol, candles, generate_signal, n_folds=N_FOLDS,
                stop_multiple=stop_multiple, reward_risk_ratio=reward_risk_ratio,
            )
            fold_size = len(candles) // N_FOLDS

            print(f"[{symbol}] {len(candles)} candles, {N_FOLDS} folds of ~{fold_size} each")
            win_rates = []
            for report in reports:
                log_backtest_result(conn, fold_size, report)
                win_rates.append(report.win_rate)
                print(
                    f"  {report.label}: closed={report.closed_trades}  "
                    f"win_rate={report.win_rate:.1%}  "
                    f"avg_R={report.avg_r_multiple:.2f}  "
                    f"max_drawdown_R={report.max_drawdown_r:.2f}"
                )
                if report.needs_audit:
                    print(
                        f"    *** {report.label}: win rate above 70% — "
                        "stop and audit this fold for lookahead/data bugs ***"
                    )

            if len(win_rates) >= 2:
                spread = max(win_rates) - min(win_rates)
                print(
                    f"  win-rate spread across folds: {spread:.1%} "
                    "(a signal with a real edge should look roughly similar "
                    "fold to fold — eyeball this, there's no auto-threshold here)"
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
