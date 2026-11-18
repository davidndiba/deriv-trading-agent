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
    status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'sold' | 'won' | 'lost'
    env TEXT NOT NULL DEFAULT 'demo'  -- 'demo' | 'live'
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS won't add a column to a table that
    already exists on disk from an earlier phase's schema, so a local
    trading_agent.db created before the `env` column was added needs an
    explicit ALTER TABLE. Safe to run every time — it's a no-op once the
    column exists."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    if "env" not in columns:
        conn.execute("ALTER TABLE trades ADD COLUMN env TEXT NOT NULL DEFAULT 'demo'")
        conn.commit()


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
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
    env: str = "demo",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO trades (
            contract_id, symbol, direction, stake, multiplier,
            take_profit, stop_loss, buy_price, opened_at, status, env
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
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
            env,
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


def get_open_trades(conn: sqlite3.Connection, env: str = "demo") -> list[tuple[str, str]]:
    """(symbol, direction) for every trade still open in the given env.
    Demo and live are separate Deriv accounts/balances entirely, so a
    live run must never count demo positions against its concurrency or
    correlation limits (or vice versa)."""
    rows = conn.execute(
        "SELECT symbol, direction FROM trades WHERE status = 'open' AND env = ?",
        (env,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_open_trade_count(conn: sqlite3.Connection, env: str = "demo") -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'open' AND env = ?", (env,)
    ).fetchone()
    return int(row[0])


def get_realized_pnl_today(conn: sqlite3.Connection, env: str = "demo") -> float:
    """Sum of `profit` for trades closed today (UTC) in the given env.
    0.0 if none closed. Scoped by env for the same reason as
    get_open_trades — demo and live P&L must never be mixed into one
    kill-switch check."""
    today = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(profit), 0.0) FROM trades "
        "WHERE closed_at IS NOT NULL AND substr(closed_at, 1, 10) = ? AND env = ?",
        (today, env),
    ).fetchone()
    return float(row[0])


def get_demo_track_record(conn: sqlite3.Connection) -> tuple[int, str | None]:
    """(closed demo trade count, earliest demo trade's opened_at or None).
    Always scoped to env='demo' regardless of what the caller is running
    as — this is specifically the pre-live soak-period check."""
    row = conn.execute(
        "SELECT COUNT(*), MIN(opened_at) FROM trades "
        "WHERE env = 'demo' AND status IN ('won', 'lost')"
    ).fetchone()
    return int(row[0]), row[1]


def _rows_as_dicts(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Read-only helper for the FastAPI layer. Sets row_factory on this
    connection so results come back as plain dicts; safe to call on a
    connection that's about to be closed anyway (every api/main.py
    endpoint opens a fresh connection per request)."""
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def list_proposals(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return _rows_as_dicts(
        conn,
        "SELECT id, created_at, symbol, direction, reason, balance, stake, "
        "multiplier, take_profit, stop_loss, max_loss, max_gain, "
        "risk_reward_ratio, blackout_halved, approved FROM proposals "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def list_trades(
    conn: sqlite3.Connection, env: str = "demo", status: str | None = None, limit: int = 50
) -> list[dict]:
    if status is not None:
        return _rows_as_dicts(
            conn,
            "SELECT * FROM trades WHERE env = ? AND status = ? ORDER BY id DESC LIMIT ?",
            (env, status, limit),
        )
    return _rows_as_dicts(
        conn, "SELECT * FROM trades WHERE env = ? ORDER BY id DESC LIMIT ?", (env, limit)
    )


def list_backtests(
    conn: sqlite3.Connection, symbol: str | None = None, limit: int = 50
) -> list[dict]:
    if symbol is not None:
        return _rows_as_dicts(
            conn,
            "SELECT * FROM backtests WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        )
    return _rows_as_dicts(conn, "SELECT * FROM backtests ORDER BY id DESC LIMIT ?", (limit,))


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
