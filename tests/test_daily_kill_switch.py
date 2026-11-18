"""The kill-switch arithmetic itself (not the full script, which needs a
live Deriv session and pydantic) — exercised against storage/db.py's
get_realized_pnl_today(), which has no pydantic dependency."""
from storage.db import get_connection, get_realized_pnl_today, log_trade_closed, log_trade_opened


def _open_and_close(conn, contract_id: int, profit: float) -> None:
    log_trade_opened(
        conn,
        contract_id=contract_id,
        symbol="frxEURUSD",
        direction="UP",
        stake=10.0,
        multiplier=100,
        take_profit=20.0,
        stop_loss=10.0,
        buy_price=10.0,
    )
    log_trade_closed(
        conn, contract_id=contract_id, sell_price=max(0.0, 10.0 + profit), profit=profit, status="won" if profit > 0 else "lost"
    )


def test_kill_switch_not_breached_before_any_losses(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    balance = 1000.0
    daily_loss_limit_pct = 0.03
    assert get_realized_pnl_today(conn) == 0.0
    assert not (get_realized_pnl_today(conn) < -(daily_loss_limit_pct * balance))


def test_kill_switch_breached_once_losses_exceed_limit(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    balance = 1000.0
    daily_loss_limit_pct = 0.03  # loss_limit = 30.0
    _open_and_close(conn, 1, -20.0)
    assert not (get_realized_pnl_today(conn) < -(daily_loss_limit_pct * balance))
    _open_and_close(conn, 2, -15.0)  # cumulative -35.0, past -30.0
    assert get_realized_pnl_today(conn) < -(daily_loss_limit_pct * balance)


def test_kill_switch_not_breached_by_wins(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    balance = 1000.0
    daily_loss_limit_pct = 0.03
    _open_and_close(conn, 1, 50.0)
    _open_and_close(conn, 2, -20.0)  # net +30.0, still not a loss at all
    assert not (get_realized_pnl_today(conn) < -(daily_loss_limit_pct * balance))
