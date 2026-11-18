"""SQLite logging for signals/proposals/backtests. No trade-execution
tables yet — those arrive in Phase 3 (buy/sell confirmations)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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

CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    candle_count INTEGER NOT NULL,
    total_signals INTEGER NOT NULL,
    closed_trades INTEGER NOT NULL,
    open_at_end INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_r_multiple REAL NOT NULL,
    max_drawdown_r REAL NOT NULL,
    needs_audit INTEGER NOT NULL
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
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


def log_backtest_result(
    conn: sqlite3.Connection, candle_count: int, report
) -> int:  # report: tools.backtest.BacktestReport
    cur = conn.execute(
        """
        INSERT INTO backtests (
            run_at, symbol, candle_count, total_signals, closed_trades,
            open_at_end, wins, losses, win_rate, avg_r_multiple,
            max_drawdown_r, needs_audit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            report.symbol,
            candle_count,
            report.total_signals,
            report.closed_trades,
            report.open_at_end,
            report.wins,
            report.losses,
            report.win_rate,
            report.avg_r_multiple,
            report.max_drawdown_r,
            int(report.needs_audit),
        ),
    )
    conn.commit()
    return cur.lastrowid
