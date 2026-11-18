"""generate_confirmed_signal() needs pydantic (schemas.models), so — like
tests/test_signals.py and test_risk_breakdown.py — this couldn't be
executed in this sandbox; the base-signal series are the exact
hand-verified ones from test_signals.py, and the HTF series were checked
against tools/multi_timeframe.py's own verified logic (see
docs/PROGRESS.md) before being written down here."""
import math

from agents.signals import generate_confirmed_signal
from schemas.models import Candle, Direction


def _candles(closes: list[float], half_width: float = 0.3) -> list[Candle]:
    return [
        Candle(epoch=i, open=c, high=c + half_width, low=c - half_width, close=c)
        for i, c in enumerate(closes)
    ]


def _htf_candles(start_close: float, step: float, count: int, spacing: int = 5) -> list[Candle]:
    return [
        Candle(epoch=i * spacing, open=start_close + i * step,
               high=start_close + i * step + 0.3, low=start_close + i * step - 0.3,
               close=start_close + i * step)
        for i in range(count)
    ]


def test_up_signal_confirmed_by_agreeing_htf_uptrend():
    closes = [100 + t * 0.15 + 4 * math.sin(t / 4.0) for t in range(50)]
    candles = _candles(closes)  # base signal is UP, verified in test_signals.py
    htf_up = _htf_candles(start_close=100.0, step=1.0, count=10)  # epochs 0..45, rising

    signal = generate_confirmed_signal("frxEURUSD", candles, htf_up, htf_ema_period=3)
    assert signal is not None
    assert signal.direction is Direction.UP
    assert "HTF trend confirms" in signal.reason


def test_up_signal_rejected_when_htf_disagrees():
    closes = [100 + t * 0.15 + 4 * math.sin(t / 4.0) for t in range(50)]
    candles = _candles(closes)  # base signal is UP
    htf_down = _htf_candles(start_close=200.0, step=-1.0, count=10)  # epochs 0..45, falling

    signal = generate_confirmed_signal("frxEURUSD", candles, htf_down, htf_ema_period=3)
    assert signal is None


def test_down_signal_confirmed_by_agreeing_htf_downtrend():
    closes = [100 + t * 0.1 + 8 * math.sin(t / 6.0) for t in range(61)]
    candles = _candles(closes)  # base signal is DOWN, verified in test_signals.py
    htf_down = _htf_candles(start_close=200.0, step=-1.0, count=11)  # epochs 0..50, falling

    signal = generate_confirmed_signal("frxXAUUSD", candles, htf_down, htf_ema_period=3)
    assert signal is not None
    assert signal.direction is Direction.DOWN


def test_signal_rejected_when_htf_has_no_trend_yet():
    closes = [100 + t * 0.15 + 4 * math.sin(t / 4.0) for t in range(50)]
    candles = _candles(closes)
    htf_too_short = _htf_candles(start_close=100.0, step=1.0, count=2)  # fewer than ema_period+1

    signal = generate_confirmed_signal("frxEURUSD", candles, htf_too_short, htf_ema_period=3)
    assert signal is None


def test_no_base_signal_means_no_confirmed_signal_regardless_of_htf():
    flat_candles = _candles([100.0] * 60)  # no crossover ever, per test_signals.py
    htf_up = _htf_candles(start_close=100.0, step=1.0, count=10)

    assert generate_confirmed_signal("TEST", flat_candles, htf_up, htf_ema_period=3) is None
