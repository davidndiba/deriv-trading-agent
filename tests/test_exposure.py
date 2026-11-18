"""tools/exposure.py has no third-party dependency, so this runs directly
in any environment — verified by hand in this sandbox before being
written down here."""
from tools.exposure import correlated_open_symbols, currency_exposure, is_correlated


def test_forex_symbol_splits_into_base_and_quote():
    assert currency_exposure("frxEURUSD") == frozenset({"EUR", "USD"})
    assert currency_exposure("frxGBPUSD") == frozenset({"GBP", "USD"})


def test_non_forex_symbol_only_matches_itself():
    assert currency_exposure("1HZ100V") == frozenset({"1HZ100V"})
    assert currency_exposure("frxXAUUSD") == frozenset({"XAU", "USD"})


def test_is_correlated_shares_a_currency():
    assert is_correlated("frxEURUSD", "frxGBPUSD") is True  # share USD
    assert is_correlated("frxEURUSD", "frxEURJPY") is True  # share EUR
    assert is_correlated("frxEURUSD", "1HZ100V") is False


def test_correlated_open_symbols_matches_same_direction_only():
    open_trades = [("frxEURUSD", "UP"), ("frxGBPUSD", "UP"), ("frxUSDJPY", "DOWN")]

    up_matches = correlated_open_symbols("frxAUDUSD", "UP", open_trades)
    assert set(up_matches) == {"frxEURUSD", "frxGBPUSD"}

    down_matches = correlated_open_symbols("frxAUDUSD", "DOWN", open_trades)
    assert down_matches == ["frxUSDJPY"]


def test_correlated_open_symbols_ignores_uncorrelated_symbols():
    open_trades = [("frxEURUSD", "UP"), ("frxGBPUSD", "UP")]
    assert correlated_open_symbols("1HZ100V", "UP", open_trades) == []
