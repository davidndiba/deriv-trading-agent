"""generate_mean_reversion_signal() needs pydantic (schemas.models), so
this couldn't be executed in this sandbox — same limitation as
test_signals.py. The synthetic series were found and checked against
tools/indicators.py's own hand-verified Bollinger Bands/RSI/ATR math
(see docs/PROGRESS.md) before being written down here."""
from agents.mean_reversion import generate_mean_reversion_signal
from schemas.models import Candle, Direction


def _candles(closes: list[float], half_width: float = 0.3) -> list[Candle]:
    return [
        Candle(epoch=i, open=c, high=c + half_width, low=c - half_width, close=c)
        for i, c in enumerate(closes)
    ]


def test_fades_down_when_price_pokes_above_upper_band_and_overbought():
    closes = [100.0] * 25 + [100.5, 101.0, 101.5, 108.0]
    signal = generate_mean_reversion_signal("frxEURUSD", _candles(closes))
    assert signal is not None
    assert signal.direction is Direction.DOWN
    assert signal.entry_price == closes[-1]


def test_fades_up_when_price_pokes_below_lower_band_and_oversold():
    closes = [100.0] * 25 + [99.5, 99.0, 98.5, 92.0]
    signal = generate_mean_reversion_signal("frxXAUUSD", _candles(closes))
    assert signal is not None
    assert signal.direction is Direction.UP
    assert signal.entry_price == closes[-1]


def test_no_signal_on_flat_series():
    signal = generate_mean_reversion_signal("TEST", _candles([100.0] * 40))
    assert signal is None


def test_no_signal_when_not_enough_history():
    signal = generate_mean_reversion_signal("TEST", _candles([100.0] * 10))
    assert signal is None
