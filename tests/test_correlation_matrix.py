"""tools/correlation_matrix.py has no third-party dependency, so this
runs directly in any environment."""
from tools.correlation_matrix import (
    build_correlation_matrix,
    correlated_by_matrix,
    get_correlation,
    pearson_correlation,
    simple_returns,
)


def test_simple_returns():
    r = simple_returns([100, 110, 99])
    assert abs(r[0] - 0.10) < 1e-9
    assert abs(r[1] - (-0.1)) < 1e-9


def test_pearson_perfect_positive_correlation():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [2.0, 4.0, 6.0, 8.0, 10.0]
    assert abs(pearson_correlation(a, b) - 1.0) < 1e-9


def test_pearson_perfect_negative_correlation():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    c = [5.0, 4.0, 3.0, 2.0, 1.0]
    assert abs(pearson_correlation(a, c) - (-1.0)) < 1e-9


def test_pearson_zero_variance_series_returns_zero():
    varying = [1.0, -1.0, 1.0, -1.0, 1.0]
    constant = [1.0, 1.0, 1.0, 1.0, 1.0]
    assert pearson_correlation(varying, constant) == 0.0


def test_get_correlation_looks_up_either_order_and_self():
    matrix = {("A", "B"): 1.0}
    assert get_correlation(matrix, "A", "B") == 1.0
    assert get_correlation(matrix, "B", "A") == 1.0
    assert get_correlation(matrix, "A", "A") == 1.0
    assert get_correlation(matrix, "A", "Z") is None


def test_get_correlation_does_not_treat_a_genuine_zero_as_missing():
    matrix = {("X", "Y"): 0.0}
    assert get_correlation(matrix, "X", "Y") == 0.0
    assert get_correlation(matrix, "Y", "X") == 0.0


def test_correlated_by_matrix_same_direction_positive_correlation_stacks():
    matrix = {("A", "B"): 1.0}
    assert correlated_by_matrix("A", "UP", [("B", "UP")], matrix, threshold=0.7) == ["B"]
    assert correlated_by_matrix("A", "DOWN", [("B", "UP")], matrix, threshold=0.7) == []


def test_correlated_by_matrix_opposite_direction_negative_correlation_stacks():
    matrix = {("A", "C"): -1.0}
    assert correlated_by_matrix("A", "UP", [("C", "DOWN")], matrix, threshold=0.7) == ["C"]
    assert correlated_by_matrix("A", "DOWN", [("C", "DOWN")], matrix, threshold=0.7) == []


def test_correlated_by_matrix_respects_threshold():
    matrix = {("A", "B"): 0.3}
    assert correlated_by_matrix("A", "UP", [("B", "UP")], matrix, threshold=0.7) == []


def test_build_correlation_matrix_keys_every_pair_once():
    returns = {"A": [1.0, 2.0, 3.0], "B": [2.0, 4.0, 6.0], "C": [3.0, 2.0, 1.0]}
    matrix = build_correlation_matrix(returns)
    assert set(matrix.keys()) == {("A", "B"), ("A", "C"), ("B", "C")}
