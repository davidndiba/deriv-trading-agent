"""SQLite logging for signals/proposals/backtests/trades."""
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

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    stake REAL NOT NULL,
    multiplier INTEGER NOT NULL,
    take_profit REAL NOT NULL,
    stop_loss REAL NOT NULL,
    buy_price REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    sell_price REAL,
    profit REAL,
    status TEXT NOT NULL DEFAULT 'open'  -- 'open' | 'sold' | 'won' | 'lost'
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


def log_trade_opened(
    conn: sqlite3.Connection,
    *,
    contract_id: int,
    symbol: str,
    direction: str,
    stake: float,
    multiplier: int,
    take_profit: float,
    stop_loss: float,
    buy_price: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO trades (
            contract_id, symbol, direction, stake, multiplier,
            take_profit, stop_loss, buy_price, opened_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            contract_id,
            symbol,
            direction,
            stake,
            multiplier,
            take_profit,
            stop_loss,
            buy_price,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def log_trade_closed(
    conn: sqlite3.Connection,
    *,
    contract_id: int,
    sell_price: float,
    profit: float,
    status: str,
) -> None:
    conn.execute(
        """
        UPDATE trades
        SET closed_at = ?, sell_price = ?, profit = ?, status = ?
        WHERE contract_id = ?
        """,
        (datetime.now(timezone.utc).isoformat(), sell_price, profit, status, contract_id),
    )
    conn.commit()


def get_open_trades(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(symbol, direction) for every trade still open."""
    rows = conn.execute("SELECT symbol, direction FROM trades WHERE status = 'open'").fetchall()
    return [(r[0], r[1]) for r in rows]


def get_open_trade_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'").fetchone()
    return int(row[0])


def get_realized_pnl_today(conn: sqlite3.Connection) -> float:
    """Sum of `profit` for trades closed today (UTC). 0.0 if none closed."""
    today = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(profit), 0.0) FROM trades "
        "WHERE closed_at IS NOT NULL AND substr(closed_at, 1, 10) = ?",
        (today,),
    ).fetchone()
    return float(row[0])


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
