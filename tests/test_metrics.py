"""tools/metrics.py has no third-party dependency, so this runs
directly in any environment."""
import math

from tools.metrics import max_consecutive_losses, profit_factor, sharpe_ratio, sortino_ratio


def test_sharpe_matches_hand_computed_value():
    returns = [2.0, -1.0, 2.0, -1.0]
    mean = sum(returns) / 4
    variance = sum((r - mean) ** 2 for r in returns) / 4
    expected = mean / math.sqrt(variance)
    assert abs(sharpe_ratio(returns) - expected) < 1e-9


def test_sharpe_edge_cases():
    assert sharpe_ratio([1.0]) == 0.0  # too few points
    assert sharpe_ratio([5.0, 5.0, 5.0]) == 0.0  # zero variance


def test_sortino_only_penalizes_downside():
    returns = [10.0, 10.0, -1.0]
    mean = sum(returns) / 3
    downside_var = (0**2 + 0**2 + 1**2) / 3
    expected = mean / math.sqrt(downside_var)
    assert abs(sortino_ratio(returns) - expected) < 1e-9
    assert sortino_ratio([5.0, 5.0]) == 0.0  # no downside at all


def test_profit_factor():
    assert profit_factor([10.0, -5.0, 20.0, -5.0]) == 3.0
    assert profit_factor([10.0, 20.0]) == float("inf")
    assert profit_factor([]) == 0.0
    assert profit_factor([-5.0, -3.0]) == 0.0


def test_max_consecutive_losses():
    assert max_consecutive_losses([1, -1, -1, -1, 1, -1]) == 3
    assert max_consecutive_losses([1, 1, 1]) == 0
    assert max_consecutive_losses([-1, -1]) == 2
    assert max_consecutive_losses([]) == 0


def test_max_consecutive_losses_zero_return_does_not_break_a_streak():
    # the 0 neither extends nor resets the in-progress 2-loss streak,
    # so the next loss continues it to 3
    assert max_consecutive_losses([-1, -1, 0, -1, 1, -1]) == 3
