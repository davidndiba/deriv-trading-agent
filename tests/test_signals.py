"""Signal tests use hand-verified synthetic series (see the search script
used to derive them, not checked in) rather than real market data, so the
expected EMA-crossover / RSI / ATR values are known in advance."""
import math

from agents.signals import generate_signal
from schemas.models import Candle, Direction


def _candles(closes: list[float], half_width: float = 0.3) -> list[Candle]:
    return [
        Candle(epoch=i, open=c, high=c + half_width, low=c - half_width, close=c)
        for i, c in enumerate(closes)
    ]


def test_no_signal_when_not_enough_history():
    candles = _candles([100.0] * 10)
    assert generate_signal("TEST", candles) is None


def test_no_signal_on_flat_series():
    # EMA fast/slow never diverge on a flat series -> no crossover ever.
    candles = _candles([100.0] * 60)
    assert generate_signal("TEST", candles) is None


def test_up_signal_on_verified_crossover():
    closes = [100 + t * 0.15 + 4 * math.sin(t / 4.0) for t in range(50)]
    candles = _candles(closes)
    signal = generate_signal("frxEURUSD", candles)
    assert signal is not None
    assert signal.direction is Direction.UP
    assert signal.entry_price == closes[-1]


def test_down_signal_on_verified_crossover():
    closes = [100 + t * 0.1 + 8 * math.sin(t / 6.0) for t in range(61)]
    candles = _candles(closes)
    signal = generate_signal("frxXAUUSD", candles)
    assert signal is not None
    assert signal.direction is Direction.DOWN
    assert signal.entry_price == closes[-1]


def test_no_signal_in_near_zero_volatility_market():
    # Movements are a fraction of a pip — ATR%% sits far below
    # min_atr_pct, so even if EMAs drift apart this must not fire.
    closes = [100.0] * 30 + [100.0 + i * 0.0001 for i in range(1, 21)]
    candles = _candles(closes, half_width=0.0001)
    assert generate_signal("TEST", candles) is None
