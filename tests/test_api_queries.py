"""The read-only query functions behind api/main.py. FastAPI itself can't
be imported in this sandbox (not installable here), but these functions
are plain storage/db.py code with no pydantic/FastAPI dependency, so they
run directly — same pattern as every other sandbox-verified module in
this repo."""
from storage.db import get_connection, list_backtests, list_proposals, list_trades, log_trade_closed, log_trade_opened


def _insert_raw_proposal(conn, symbol: str, approved) -> None:
    conn.execute(
        """
        INSERT INTO proposals (
            created_at, symbol, direction, reason, balance, stake,
            multiplier, take_profit, stop_loss, max_loss, max_gain,
            risk_reward_ratio, blackout_halved, approved, raw_json
        ) VALUES ('2026-11-18T00:00:00+00:00', ?, 'UP', 'test', 1000.0, 10.0,
                  100, 20.0, 10.0, 10.0, 20.0, 2.0, 0, ?, '{}')
        """,
        (symbol, approved),
    )
    conn.commit()


def test_list_proposals_returns_newest_first(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    _insert_raw_proposal(conn, "frxEURUSD", 1)
    _insert_raw_proposal(conn, "frxGBPUSD", 0)
    rows = list_proposals(conn, limit=10)
    assert [r["symbol"] for r in rows] == ["frxGBPUSD", "frxEURUSD"]
    assert rows[0]["approved"] == 0


def test_list_proposals_respects_limit(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    for i in range(5):
        _insert_raw_proposal(conn, f"SYM{i}", 1)
    assert len(list_proposals(conn, limit=2)) == 2


def test_list_trades_filters_by_env_and_status(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    log_trade_opened(
        conn, contract_id=1, symbol="frxEURUSD", direction="UP", stake=10,
        multiplier=100, take_profit=20, stop_loss=10, buy_price=10, env="demo",
    )
    log_trade_opened(
        conn, contract_id=2, symbol="frxGBPUSD", direction="UP", stake=1,
        multiplier=50, take_profit=2, stop_loss=1, buy_price=1, env="live",
    )
    log_trade_closed(conn, contract_id=1, sell_price=20, profit=10, status="won")

    assert len(list_trades(conn, env="demo")) == 1
    assert len(list_trades(conn, env="live", status="open")) == 1
    assert list_trades(conn, env="demo", status="won")[0]["profit"] == 10
    assert list_trades(conn, env="demo", status="open") == []


def test_list_backtests_filters_by_symbol(tmp_path):
    conn = get_connection(tmp_path / "t.db")

    class R:
        symbol = "frxEURUSD"
        total_signals = 5
        closed_trades = 4
        open_at_end = 1
        wins = 2
        losses = 2
        win_rate = 0.5
        avg_r_multiple = 0.5
        max_drawdown_r = 1.0
        needs_audit = False

    from storage.db import log_backtest_result

    log_backtest_result(conn, 100, R())
    rows = list_backtests(conn, symbol="frxEURUSD")
    assert len(rows) == 1
    assert rows[0]["win_rate"] == 0.5
    assert list_backtests(conn, symbol="frxXAUUSD") == []
