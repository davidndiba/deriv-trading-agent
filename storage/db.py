"""SQLite logging for signals/proposals. No trade-execution tables yet —
those arrive in Phase 3 (buy/sell confirmations)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "trading_agent.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    reason TEXT NOT NULL,
    balance REAL NOT NULL,
    stake REAL NOT NULL,
    multiplier INTEGER NOT NULL,
    take_profit REAL NOT NULL,
    stop_loss REAL NOT NULL,
    max_loss REAL NOT NULL,
    max_gain REAL NOT NULL,
    risk_reward_ratio REAL NOT NULL,
    blackout_halved INTEGER NOT NULL,
    approved INTEGER,  -- NULL = not decided, 0 = rejected, 1 = approved
    raw_json TEXT NOT NULL
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def log_proposal(conn: sqlite3.Connection, proposal) -> int:  # TradeProposal
    s, r = proposal.signal, proposal.risk
    cur = conn.execute(
        """
        INSERT INTO proposals (
            created_at, symbol, direction, reason, balance, stake,
            multiplier, take_profit, stop_loss, max_loss, max_gain,
            risk_reward_ratio, blackout_halved, approved, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal.created_at.isoformat(),
            s.symbol,
            s.direction.value,
            s.reason,
            r.balance,
            r.stake,
            r.multiplier,
            r.take_profit,
            r.stop_loss,
            r.max_loss,
            r.max_gain,
            r.risk_reward_ratio,
            int(r.blackout_halved),
            None if proposal.approved is None else int(proposal.approved),
            proposal.model_dump_json(),
        ),
    )
    conn.commit()
    return cur.lastrowid
