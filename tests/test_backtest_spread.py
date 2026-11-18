"""tools/backtest.py's spread_pct — no third-party dependency, runs
directly. Covers (1) spread_pct=0.0 is byte-identical to the pre-Phase-12
behavior every earlier script still relies on, and (2) a nonzero spread
shifts both barriers against the trader in the expected direction."""
from tools.backtest import backtest_symbol


class C:
    def __init__(self, h, l, close):
        self.high, self.low, self.close = h, l, close


class FakeSignal:
    def __init__(self, direction, entry_price, atr):
        self.direction = direction
        self.entry_price = entry_price
        self.atr = atr


def _atr_for_5pct_stop(entry_price: float, stop_multiple: float) -> float:
    return entry_price * 0.05 / stop_multiple


def test_default_spread_pct_is_zero_and_unchanged_from_before():
    atr = _atr_for_5pct_stop(100, 1.5)
    candles = [C(100, 100, 100), C(105, 101, 103), C(111, 108, 110), C(109, 107, 108)]

    def fn(symbol, window):
        return FakeSignal("UP", entry_price=100, atr=atr) if len(window) == 1 else None

    trades_default = backtest_symbol("TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0)
    trades_explicit = backtest_symbol(
        "TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0, spread_pct=0.0
    )
    assert trades_default[0].entry_price == 100.0
    assert abs(trades_default[0].stop_loss_price - 95.0) < 1e-9
    assert abs(trades_default[0].take_profit_price - 110.0) < 1e-9
    assert [t.entry_price for t in trades_default] == [t.entry_price for t in trades_explicit]
    assert [t.outcome for t in trades_default] == [t.outcome for t in trades_explicit]


def test_spread_widens_take_profit_and_narrows_stop_loss_for_a_long():
    atr = _atr_for_5pct_stop(100, 1.5)
    candles = [C(100, 100, 100), C(105, 101, 103)]

    def fn(symbol, window):
        return FakeSignal("UP", entry_price=100, atr=atr) if len(window) == 1 else None

    trades = backtest_symbol("TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0, spread_pct=0.01)
    t = trades[0]
    assert t.entry_price == 101.0  # fill price: 100 * 1.01
    assert abs(t.stop_loss_price - 95.95) < 1e-9     # 101 * 0.95, closer than the frictionless 95.0
    assert abs(t.take_profit_price - 111.1) < 1e-9   # 101 * 1.10, farther than the frictionless 110.0


def test_spread_narrows_take_profit_and_widens_stop_loss_for_a_short():
    atr = _atr_for_5pct_stop(100, 1.5)
    candles = [C(100, 100, 100), C(95, 91, 93)]

    def fn(symbol, window):
        return FakeSignal("DOWN", entry_price=100, atr=atr) if len(window) == 1 else None

    trades = backtest_symbol("TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0, spread_pct=0.01)
    t = trades[0]
    assert t.entry_price == 99.0  # fill price: 100 * 0.99 (short fills worse = lower)
    assert abs(t.stop_loss_price - 103.95) < 1e-9    # 99 * 1.05, closer than the frictionless 105.0
    assert abs(t.take_profit_price - 89.1) < 1e-9    # 99 * 0.90, farther than the frictionless 90.0


def test_spread_can_flip_a_near_miss_win_into_a_loss():
    atr = _atr_for_5pct_stop(100, 1.5)
    # Frictionless: TP=110 is hit at idx2 (high=111) before SL=95 is ever touched -> win.
    # With 1% spread: TP becomes 111.1, which idx2's high=111 no longer reaches, so the
    # trade stays open into later bars where the (now-closer) SL eventually gets hit.
    candles = [
        C(100, 100, 100), C(105, 101, 103), C(111, 108, 110),
    ] + [C(105, 105, 105)] * 7 + [C(101, 94, 96)]

    def fn(symbol, window):
        return FakeSignal("UP", entry_price=100, atr=atr) if len(window) == 1 else None

    frictionless = backtest_symbol("TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0)
    assert frictionless[0].outcome == "win"

    with_spread = backtest_symbol(
        "TEST", candles, fn, stop_multiple=1.5, reward_risk_ratio=2.0, spread_pct=0.01
    )
    assert with_spread[0].outcome == "loss"
