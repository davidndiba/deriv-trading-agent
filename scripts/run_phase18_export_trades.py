"""Phase 18: export trade history to CSV.

Local-only, like Phase 13's performance report — doesn't connect to
Deriv at all, everything it needs is already in the local SQLite log.

Usage:
    python scripts/run_phase18_export_trades.py [--env demo|live]
        [--status open|sold|won|lost] [--limit 1000] [--output path.csv]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from storage.db import get_connection, list_trades
from tools.csv_export import trades_to_csv

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "exports"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["demo", "live"], default="demo")
    parser.add_argument("--status", choices=["open", "sold", "won", "lost"], default=None)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    conn = get_connection()
    try:
        trades = list_trades(conn, env=args.env, status=args.status, limit=args.limit)
    finally:
        conn.close()

    csv_text = trades_to_csv(trades)

    output = args.output
    if output is None:
        EXPORTS_DIR.mkdir(exist_ok=True)
        filename = f"{args.env}_trades_{datetime.now(timezone.utc).date().isoformat()}.csv"
        output = EXPORTS_DIR / filename

    output.write_text(csv_text)
    print(f"Exported {len(trades)} trade(s) to {output}")


if __name__ == "__main__":
    main()
