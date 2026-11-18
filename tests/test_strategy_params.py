"""tools/strategy_params.py has no third-party dependency, so this runs
directly in any environment."""
from tools.strategy_params import ATR_STOP_MULTIPLE, REWARD_RISK_RATIO, get_strategy_params


def test_overridden_symbols_get_their_own_params():
    assert get_strategy_params("frxXAUUSD") == (2.0, 2.5)
    assert get_strategy_params("1HZ100V") == (1.0, 2.0)


def test_unlisted_symbol_falls_back_to_global_defaults():
    assert get_strategy_params("frxEURUSD") == (ATR_STOP_MULTIPLE, REWARD_RISK_RATIO)
    assert get_strategy_params("some_future_symbol") == (ATR_STOP_MULTIPLE, REWARD_RISK_RATIO)


def test_overrides_are_distinct_from_each_other_and_the_default():
    gold = get_strategy_params("frxXAUUSD")
    synthetic = get_strategy_params("1HZ100V")
    default = (ATR_STOP_MULTIPLE, REWARD_RISK_RATIO)
    assert gold != synthetic
    assert gold != default
    assert synthetic != default
