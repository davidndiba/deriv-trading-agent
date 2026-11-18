"""tools/backtest.py has no pydantic dependency, so these run directly in
any environment. See docs/PROGRESS.md for how the scenarios here were
hand-derived and executed before being written down as pytest cases."""
from tools.backtest import backtest_symbol, simulate_trade, summarize


class C:
    def __init__(self, h, l, close):
        self.high, self.low, self.close = h, l, close


class FakeSignal:
    def __init__(self, direction, entry_price, atr):
        self.direction = direction  # plain string, exercising the non-enum path
        self.entry_price = entry_price
        self.atr = atr


def test_simulate_trade_win_when_tp_hit_first():
    candles = [C(100, 100, 100), C(103, 101, 102), C(106, 104, 105), C(109, 107, 108)]
    r = simulate_trade(
        candles, "X", 0, "UP",
        entry_price=100, stop_loss_price=95, take_profit_price=106,
        reward_risk_ratio=2.0,
    )
    assert r.outcome == "win"
    assert r.exit_index == 2
    assert r.r_multiple == 2.0


def test_simulate_trade_loss_when_sl_hit_first():
    candles = [C(100, 100, 100), C(101, 94, 96), C(108, 107, 107)]
    r = simulate_trade(
        candles, "X", 0, "UP",
        entry_price=100, stop_loss_price=95, take_profit_price=108,
        reward_risk_ratio=2.0,
    )
    assert r.outcome == "loss"
    assert r.exit_index == 1
    assert r.r_multiple == -1.0


def test_simulate_trade_same_bar_touch_assumes_stop_loss_first():
    candles = [C(100, 100, 100), C(110, 90, 100)]
    r = simulate_trade(
        candles, "X", 0, "UP",
        entry_price=100, stop_loss_price=95, take_profit_price=106,
        reward_risk_ratio=2.0,
    )
    assert r.outcome == "loss"


def test_simulate_trade_down_direction_win():
    candles = [C(100, 100, 100), C(99, 94, 95), C(93, 89, 90)]
    r = simulate_trade(
        candles, "X", 0, "DOWN",
        entry_price=100, stop_loss_price=105, take_profit_price=92,
        reward_risk_ratio=2.0,
    )
    assert r.outcome == "win"
    assert r.exit_index == 2


def test_simulate_trade_open_at_end_when_data_runs_out():
    candles = [C(100, 100, 100), C(101, 99, 100)]
    r = simulate_trade(
        candles, "X", 0, "UP",
        entry_price=100, stop_loss_price=90, take_profit_price=120,
        reward_risk_ratio=2.0,
    )
    assert r.outcome == "open_at_end"
    assert r.r_multiple is None
    assert r.exit_price == 100


def _five_pct_stop_atr(entry_price: float, stop_multiple: float) -> float:
    """atr value that makes stop_multiple*atr/entry_price == 0.05."""
    return entry_price * 0.05 / stop_multiple


def test_backtest_symbol_no_overlap_and_summarize_stats():
    atr = _five_pct_stop_atr(100, stop_multiple=1.5)
    candles = [
        C(100, 100, 100),  # 0: entry bar, trade 1 (UP)
        C(105, 101, 103),  # 1: no hit (TP=110, SL=95)
        C(111, 108, 110),  # 2: TP hit -> win
    ]
    candles += [C(105, 105, 105)] * 7  # 3-9: no signal fires here
    candles += [
        C(100, 100, 100),  # 10: entry bar, trade 2 (UP)
        C(101, 94, 96),    # 11: SL hit -> loss
    ]
    candles += [C(96, 96, 96)] * 8  # 12-19: filler

    def fake_signal_fn(symbol, window):
        i = len(window) - 1
        if i in (0, 10):
            return FakeSignal("UP", entry_price=100, atr=atr)
        return None

    trades = backtest_symbol("TEST", candles, fake_signal_fn, stop_multiple=1.5, reward_risk_ratio=2.0)
    assert [(t.entry_index, t.exit_index, t.outcome) for t in trades] == [
        (0, 2, "win"),
        (10, 11, "loss"),
    ]

    report = summarize("TEST", trades)
    assert report.closed_trades == 2
    assert report.wins == 1 and report.losses == 1
    assert report.win_rate == 0.5
    assert report.avg_r_multiple == 0.5
    assert abs(report.max_drawdown_r - 1.0) < 1e-9
    assert report.needs_audit is False


def test_summarize_flags_suspiciously_high_win_rate():
    atr = _five_pct_stop_atr(100, stop_multiple=1.5)
    candles = [C(100, 100, 100)]
    for _ in range(15):
        candles.append(C(111, 108, 110))  # always immediately hits TP
        candles.append(C(100, 100, 100))  # re-entry bar

    def always_win_fn(symbol, window):
        i = len(window) - 1
        if i % 2 == 0 and i < len(candles) - 1:
            return FakeSignal("UP", entry_price=100, atr=atr)
        return None

    trades = backtest_symbol("TEST", candles, always_win_fn, stop_multiple=1.5, reward_risk_ratio=2.0)
    report = summarize("TEST", trades)
    assert report.win_rate > 0.70
    assert report.closed_trades >= 10
    assert report.needs_audit is True
