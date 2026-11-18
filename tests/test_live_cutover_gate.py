"""Soak-period gate logic for Phase 5 (scripts/run_phase5_live_trading.py
can't be imported here — it pulls in pydantic transitively — so this
exercises the same storage/db.py function the script's check is built on,
with the identical threshold logic inlined, matching how it was
hand-verified before being written down as a test)."""
from datetime import datetime, timedelta, timezone

from storage.db import get_connection, get_demo_track_record, log_trade_closed, log_trade_opened


def _check(conn, min_trades: int, min_days: int) -> tuple[bool, str]:
    closed_count, earliest_opened_at = get_demo_track_record(conn)
    if closed_count < min_trades:
        return False, f"only {closed_count} closed demo trades (need {min_trades})"
    if earliest_opened_at is None:
        return False, "no demo trade history"
    earliest = datetime.fromisoformat(earliest_opened_at)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    soak_days = (datetime.now(timezone.utc) - earliest).days
    if soak_days < min_days:
        return False, f"only {soak_days} days (need {min_days})"
    return True, f"{closed_count} trades over {soak_days} days"


def _add_closed_demo_trade(conn, contract_id: int) -> None:
    log_trade_opened(
        conn, contract_id=contract_id, symbol="frxEURUSD", direction="UP",
        stake=1.0, multiplier=10, take_profit=2.0, stop_loss=1.0, buy_price=1.0, env="demo",
    )
    log_trade_closed(conn, contract_id=contract_id, sell_price=1.0, profit=0.1, status="won")


def test_blocks_with_no_demo_history(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    ok, _ = _check(conn, min_trades=20, min_days=14)
    assert ok is False


def test_blocks_when_trade_count_met_but_soak_too_short(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    for i in range(25):
        _add_closed_demo_trade(conn, 1000 + i)  # all opened "now"
    ok, reason = _check(conn, min_trades=20, min_days=14)
    assert ok is False
    assert "days" in reason


def test_passes_once_both_count_and_soak_window_are_met(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    for i in range(25):
        _add_closed_demo_trade(conn, 1000 + i)
    old_date = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    conn.execute("UPDATE trades SET opened_at = ? WHERE contract_id = 1000", (old_date,))
    conn.commit()
    ok, reason = _check(conn, min_trades=20, min_days=14)
    assert ok is True
    assert "25 trades" in reason


def test_live_trades_never_count_toward_the_demo_track_record(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for i in range(25):
        log_trade_opened(
            conn, contract_id=2000 + i, symbol="frxEURUSD", direction="UP",
            stake=1.0, multiplier=10, take_profit=2.0, stop_loss=1.0,
            buy_price=1.0, env="live",
        )
        log_trade_closed(conn, contract_id=2000 + i, sell_price=1.0, profit=0.1, status="won")
    conn.execute("UPDATE trades SET opened_at = ? WHERE env = 'live'", (old_date,))
    conn.commit()
    ok, _ = _check(conn, min_trades=20, min_days=14)
    assert ok is False  # 25 trades exist, but none of them count — they're 'live', not 'demo'
