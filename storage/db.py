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
    needs_audit INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT ''  -- e.g. 'fold 2/4'; '' for a whole-window run
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

CREATE TABLE IF NOT EXISTS correlation_matrix (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at TEXT NOT NULL,
    symbol_a TEXT NOT NULL,
    symbol_b TEXT NOT NULL,
    correlation REAL NOT NULL,
    candle_count INTEGER NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS won't add a column to a table that
    already exists on disk from an earlier phase's schema, so a local
    trading_agent.db created before the `env` column was added needs an
    explicit ALTER TABLE. Safe to run every time — it's a no-op once the
    column exists."""
    trade_columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    if "env" not in trade_columns:
        conn.execute("ALTER TABLE trades ADD COLUMN env TEXT NOT NULL DEFAULT 'demo'")
        conn.commit()

    backtest_columns = {row[1] for row in conn.execute("PRAGMA table_info(backtests)")}
    if "label" not in backtest_columns:
        conn.execute("ALTER TABLE backtests ADD COLUMN label TEXT NOT NULL DEFAULT ''")
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


def get_open_contract_ids(conn: sqlite3.Connection, env: str = "demo") -> set[int]:
    """Every contract_id the local log still calls 'open' for this env —
    the local side of the reconciliation check in tools/reconciliation.py."""
    rows = conn.execute(
        "SELECT contract_id FROM trades WHERE status = 'open' AND env = ?", (env,)
    ).fetchall()
    return {r[0] for r in rows}


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


def get_trades_closed_since(conn: sqlite3.Connection, since_iso: str, env: str = "demo") -> list[dict]:
    """Every closed (won/lost) trade for this env since a given ISO
    timestamp, oldest first — the input to tools/reporting.py's
    performance report, which builds its equity curve in this order."""
    return _rows_as_dicts(
        conn,
        "SELECT * FROM trades WHERE env = ? AND status IN ('won', 'lost') "
        "AND closed_at >= ? ORDER BY closed_at ASC",
        (env, since_iso),
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
            max_drawdown_r, needs_audit, label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            getattr(report, "label", ""),
        ),
    )
    conn.commit()
    return cur.lastrowid


def log_correlation_matrix(
    conn: sqlite3.Connection, candle_count: int, matrix: dict[tuple[str, str], float]
) -> None:
    """One row per pair, all sharing the same computed_at so
    get_latest_correlation_matrix() can pull back exactly one run."""
    computed_at = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO correlation_matrix (computed_at, symbol_a, symbol_b, "
        "correlation, candle_count) VALUES (?, ?, ?, ?, ?)",
        [
            (computed_at, symbol_a, symbol_b, correlation, candle_count)
            for (symbol_a, symbol_b), correlation in matrix.items()
        ],
    )
    conn.commit()


def get_latest_correlation_matrix(conn: sqlite3.Connection) -> dict[tuple[str, str], float]:
    """The most recently logged correlation_matrix run, as a dict keyed
    like tools.correlation_matrix.build_correlation_matrix()'s own
    output — {} if nothing has been logged yet."""
    row = conn.execute("SELECT MAX(computed_at) FROM correlation_matrix").fetchone()
    latest = row[0]
    if latest is None:
        return {}
    rows = conn.execute(
        "SELECT symbol_a, symbol_b, correlation FROM correlation_matrix WHERE computed_at = ?",
        (latest,),
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def get_latest_correlation_matrix_with_timestamp(
    conn: sqlite3.Connection,
) -> tuple[dict[tuple[str, str], float], str | None]:
    """Same as get_latest_correlation_matrix(), plus the run's own
    computed_at (None if nothing has been logged) — for a caller that
    needs to decide whether that run is too stale to trust, e.g. a live
    trading script deciding whether to apply the real-correlation guard
    this run or fall back to the heuristic alone."""
    row = conn.execute("SELECT MAX(computed_at) FROM correlation_matrix").fetchone()
    latest = row[0]
    if latest is None:
        return {}, None
    rows = conn.execute(
        "SELECT symbol_a, symbol_b, correlation FROM correlation_matrix WHERE computed_at = ?",
        (latest,),
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}, latest
