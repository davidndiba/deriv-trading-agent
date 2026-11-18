"""tools/reconciliation.py's diff logic (no dependency) plus the healing
flow it feeds into, using the real storage/db.py functions."""
from storage.db import get_connection, get_open_contract_ids, log_trade_closed, log_trade_opened
from tools.reconciliation import diff_portfolio


def test_no_drift():
    assert diff_portfolio({1, 2, 3}, {1, 2, 3}) == (set(), set())


def test_ghost_when_local_open_but_deriv_closed():
    ghosts, orphans = diff_portfolio({1, 2, 3, 4}, {1, 2, 3})
    assert ghosts == {4}
    assert orphans == set()


def test_orphan_when_deriv_open_but_no_local_record():
    ghosts, orphans = diff_portfolio({1, 2, 3}, {1, 2, 3, 5})
    assert ghosts == set()
    assert orphans == {5}


def test_both_ghost_and_orphan_at_once():
    ghosts, orphans = diff_portfolio({1, 2, 4}, {1, 2, 5})
    assert ghosts == {4}
    assert orphans == {5}


def test_both_sides_empty():
    assert diff_portfolio(set(), set()) == (set(), set())


def test_healing_a_ghost_removes_it_from_local_open_ids(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    log_trade_opened(
        conn, contract_id=99, symbol="frxEURUSD", direction="UP", stake=1,
        multiplier=10, take_profit=2, stop_loss=1, buy_price=1, env="demo",
    )
    assert get_open_contract_ids(conn, env="demo") == {99}

    # simulate what run_phase8_reconcile.py does once it detects a ghost
    # and fetches a snapshot from Deriv showing it actually won
    ghosts, _ = diff_portfolio(get_open_contract_ids(conn, env="demo"), set())
    assert ghosts == {99}
    log_trade_closed(conn, contract_id=99, sell_price=2, profit=1, status="won")

    assert get_open_contract_ids(conn, env="demo") == set()
