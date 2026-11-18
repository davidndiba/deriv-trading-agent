"""storage/db.py's correlation_matrix functions against real SQLite —
no third-party dependency."""
import time

from storage.db import get_connection, get_latest_correlation_matrix, log_correlation_matrix


def test_empty_db_returns_empty_dict(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    assert get_latest_correlation_matrix(conn) == {}


def test_round_trips_including_a_genuine_zero_correlation(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    matrix = {
        ("frxEURUSD", "frxGBPUSD"): 0.85,
        ("frxEURUSD", "frxXAUUSD"): -0.3,
        ("frxGBPUSD", "frxXAUUSD"): 0.0,
    }
    log_correlation_matrix(conn, 500, matrix)
    got = get_latest_correlation_matrix(conn)
    assert got == matrix
    assert got[("frxGBPUSD", "frxXAUUSD")] == 0.0


def test_only_the_latest_run_is_returned(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    log_correlation_matrix(conn, 500, {("A", "B"): 0.1})
    time.sleep(0.01)
    log_correlation_matrix(conn, 600, {("A", "B"): 0.9})
    assert get_latest_correlation_matrix(conn) == {("A", "B"): 0.9}
