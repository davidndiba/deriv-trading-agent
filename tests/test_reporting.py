"""tools/reporting.py has no third-party dependency (operates on plain
dicts, not pydantic models), so this runs directly, plus a check of
storage/db.py's get_trades_closed_since feeding it real data."""
from datetime import datetime, timedelta, timezone

from storage.db import get_connection, get_trades_closed_since, log_trade_closed, log_trade_opened
from tools.reporting import build_performance_report, sparkline


def test_sparkline_flat_series():
    assert sparkline([5.0, 5.0, 5.0]) == "▁▁▁"


def test_sparkline_empty():
    assert sparkline([]) == ""


def test_sparkline_increasing_series_spans_low_to_high():
    s = sparkline([0.0, 1, 2, 3, 4, 5, 6, 7])
    assert s[0] == "▁"
    assert s[-1] == "█"


def test_report_on_no_trades():
    report = build_performance_report([], "daily (demo)")
    assert "No closed trades" in report


def test_report_computes_totals_and_per_symbol_breakdown():
    trades = [
        {"symbol": "frxEURUSD", "profit": 10.0, "status": "won", "closed_at": "t1"},
        {"symbol": "frxEURUSD", "profit": -5.0, "status": "lost", "closed_at": "t2"},
        {"symbol": "frxXAUUSD", "profit": 20.0, "status": "won", "closed_at": "t3"},
    ]
    report = build_performance_report(trades, "daily (demo) - last 1 day(s)")
    assert "Closed trades: 3" in report
    assert "wins 2, losses 1" in report
    assert "Win rate: 66.7%" in report
    assert "Total P&L: $25.00" in report
    assert "frxEURUSD: 2 trades, 1/2 won, $5.00" in report
    assert "frxXAUUSD: 1 trades, 1/1 won, $20.00" in report
    assert "Profit factor: 6.00" in report  # gross profit 30 / gross loss 5
    assert "Max consecutive losses: 1" in report
    assert "Sharpe:" in report and "Sortino:" in report


def test_report_fed_by_real_db_data(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    log_trade_opened(
        conn, contract_id=1, symbol="frxEURUSD", direction="UP", stake=10,
        multiplier=100, take_profit=20, stop_loss=10, buy_price=10, env="demo",
    )
    log_trade_closed(conn, contract_id=1, sell_price=20, profit=10, status="won")

    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    trades = get_trades_closed_since(conn, since, env="demo")
    report = build_performance_report(trades, "daily (demo)")
    assert "Closed trades: 1" in report
    assert "Total P&L: $10.00" in report
