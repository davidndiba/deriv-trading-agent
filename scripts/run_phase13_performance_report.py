"""Phase 13: daily/weekly performance report from the local trade log.

Deliberately doesn't connect to Deriv at all — everything it needs is
already in the local SQLite log that the trading/reconciliation scripts
write to, so this is safe and fast to run anytime, offline even. No
`buy`/`sell`/`proposal`/`portfolio` call exists anywhere in this script.

Usage:
    python scripts/run_phase13_performance_report.py [--period daily|weekly]
        [--env demo|live] [--notify] [--no-save]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import load_settings
from storage.db import get_connection, get_trades_closed_since
from tools.reporting import build_performance_report
from tools.telegram_notifier import TelegramNotifier

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
PERIOD_DAYS = {"daily": 1, "weekly": 7}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", choices=sorted(PERIOD_DAYS), default="daily")
    parser.add_argument("--env", choices=["demo", "live"], default="demo")
    parser.add_argument(
        "--notify", action="store_true",
        help="Also send the report via Telegram (no-op if not configured)",
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Don't write the report to reports/"
    )
    args = parser.parse_args()

    # load_settings() is used only for Telegram config here — this
    # script never connects to Deriv — but it's still the one place
    # config validation happens, so a missing/malformed .env is caught
    # the same way it would be for every other script.
    settings = load_settings()

    days = PERIOD_DAYS[args.period]
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conn = get_connection()
    try:
        trades = get_trades_closed_since(conn, since_iso, env=args.env)
    finally:
        conn.close()

    period_label = f"{args.period} report ({args.env}) — last {days} day(s)"
    report_text = build_performance_report(trades, period_label)
    print(report_text)

    if not args.no_save:
        REPORTS_DIR.mkdir(exist_ok=True)
        filename = f"{args.env}_{args.period}_{datetime.now(timezone.utc).date().isoformat()}.md"
        path = REPORTS_DIR / filename
        path.write_text(report_text)
        print(f"\nSaved to {path}")

    if args.notify:
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
        if notifier.enabled:
            asyncio.run(notifier.send(report_text))
            print("Sent via Telegram.")
        else:
            print("Telegram not configured — skipped --notify.")


if __name__ == "__main__":
    main()
