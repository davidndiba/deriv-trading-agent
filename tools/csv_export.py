"""CSV export of trade history. Pure Python (stdlib csv module), no
third-party dependency — operates on plain dicts, the same shape
storage/db.py's trade rows already come back as.
"""
from __future__ import annotations

import csv
import io

TRADE_COLUMNS = [
    "id", "contract_id", "symbol", "direction", "stake", "multiplier",
    "take_profit", "stop_loss", "buy_price", "opened_at", "closed_at",
    "sell_price", "profit", "status", "env",
]


def trades_to_csv(trades: list[dict]) -> str:
    """Renders trades as CSV text, columns in TRADE_COLUMNS order. A
    dict missing a column becomes an empty cell rather than raising
    (extrasaction="ignore" drops any extra keys the same way) — keeps
    this tolerant of a caller's dict not matching the schema exactly."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=TRADE_COLUMNS, extrasaction="ignore", restval=""
    )
    writer.writeheader()
    for trade in trades:
        writer.writerow(trade)
    return buffer.getvalue()
