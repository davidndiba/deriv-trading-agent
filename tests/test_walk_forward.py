"""tools/backtest.py's fold-splitting and per-fold reporting, no
third-party dependency — same pattern as test_backtest.py. Scenarios here
were hand-verified by direct execution before being written down."""
from tools.backtest import split_into_folds, summarize, walk_forward_report


class C:
    def __init__(self, h, l, close):
        self.high, self.low, self.close = h, l, close


class FakeSignal:
    def __init__(self, direction, entry_price, atr):
        self.direction = direction
        self.entry_price = entry_price
        self.atr = atr


def test_split_into_folds_exact_division():
    candles = [C(1, 1, 1)] * 12
    folds = split_into_folds(candles, 4)
    assert [len(f) for f in folds] == [3, 3, 3, 3]


def test_split_into_folds_uneven_division_gives_remainder_to_earlier_folds():
    candles = [C(1, 1, 1)] * 10
    folds = split_into_folds(candles, 4)
    assert [len(f) for f in folds] == [3, 3, 2, 2]
    assert sum(len(f) for f in folds) == 10


def test_split_into_folds_preserves_chronological_order():
    candles = [C(i, i, i) for i in range(23)]
    folds = split_into_folds(candles, 5)
    reconstructed = [c for fold in folds for c in fold]
    assert reconstructed == candles


def test_summarize_label_defaults_to_empty_string():
    report = summarize("TEST", [])
    assert report.label == ""


def _five_pct_stop_atr(entry_price: float, stop_multiple: float) -> float:
    return entry_price * 0.05 / stop_multiple


def test_walk_forward_report_isolates_each_folds_outcome():
    atr = _five_pct_stop_atr(100, stop_multiple=1.5)
    fold_a = [C(100, 100, 100), C(105, 101, 103), C(111, 108, 110)] + [C(105, 105, 105)] * 7
    fold_b = [C(100, 100, 100), C(101, 94, 96)] + [C(96, 96, 96)] * 8
    all_candles = fold_a + fold_b

    def fake_signal_fn(symbol, window):
        i = len(window) - 1
        if i in (0, len(fold_a)):
            return FakeSignal("UP", entry_price=100, atr=atr)
        return None

    reports = walk_forward_report(
        "TEST", all_candles, fake_signal_fn, n_folds=2, stop_multiple=1.5, reward_risk_ratio=2.0
    )
    assert reports[0].label == "fold 1/2"
    assert reports[0].wins == 1 and reports[0].losses == 0
    assert reports[1].label == "fold 2/2"
    assert reports[1].wins == 0 and reports[1].losses == 1
