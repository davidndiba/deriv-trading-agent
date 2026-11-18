"""tools/csv_export.py has no third-party dependency (uses stdlib csv),
so this runs directly."""
import csv
import io

from tools.csv_export import TRADE_COLUMNS, trades_to_csv


def _sample_trades():
    return [
        {"id": 1, "contract_id": 101, "symbol": "frxEURUSD", "direction": "UP",
         "stake": 10.0, "multiplier": 100, "take_profit": 20.0, "stop_loss": 10.0,
         "buy_price": 10.0, "opened_at": "2026-11-18T06:00:00+00:00",
         "closed_at": "2026-11-18T06:30:00+00:00", "sell_price": 20.0,
         "profit": 10.0, "status": "won", "env": "demo"},
        {"id": 2, "contract_id": 102, "symbol": "frxGBPUSD", "direction": "DOWN",
         "stake": 5.0, "multiplier": 50, "take_profit": 10.0, "stop_loss": 5.0,
         "buy_price": 5.0, "opened_at": "2026-11-18T07:00:00+00:00",
         "closed_at": None, "sell_price": None, "profit": None,
         "status": "open", "env": "demo"},
    ]


def test_round_trips_through_csv_reader():
    text = trades_to_csv(_sample_trades())
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2
    assert rows[0]["symbol"] == "frxEURUSD"
    assert rows[0]["profit"] == "10.0"
    assert list(rows[0].keys()) == TRADE_COLUMNS


def test_none_values_become_empty_cells_not_the_string_none():
    text = trades_to_csv(_sample_trades())
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[1]["profit"] == ""
    assert rows[1]["closed_at"] == ""


def test_tolerant_of_missing_and_extra_keys():
    sparse = [{"symbol": "frxXAUUSD", "bogus_extra_field": "ignored"}]
    text = trades_to_csv(sparse)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["symbol"] == "frxXAUUSD"
    assert rows[0]["profit"] == ""
    assert "bogus_extra_field" not in rows[0]


def test_empty_list_produces_header_only():
    text = trades_to_csv([])
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows == []
    assert text.strip() == ",".join(TRADE_COLUMNS)
