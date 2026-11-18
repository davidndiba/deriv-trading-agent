from schemas.models import RiskBreakdown


def test_stake_is_balance_times_risk_pct():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=False,
        take_profit_pct=0.02,
        stop_loss_pct=0.01,
    )
    assert rb.stake == 10.0
    assert rb.max_loss == rb.stake


def test_blackout_date_halves_stake():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=True,
        take_profit_pct=0.02,
        stop_loss_pct=0.01,
    )
    assert rb.stake == 5.0
    assert rb.blackout_halved is True


def test_risk_reward_ratio_matches_tp_sl_ratio():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=False,
        take_profit_pct=0.02,
        stop_loss_pct=0.01,
    )
    assert rb.risk_reward_ratio == 2.0


def test_multiplier_derived_from_stop_loss_distance():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=False,
        take_profit_pct=0.02,
        stop_loss_pct=0.01,
    )
    assert rb.multiplier == 100


def test_rejects_non_positive_distances():
    import pytest

    with pytest.raises(ValueError):
        RiskBreakdown.compute(
            balance=1000.0,
            risk_per_trade_pct=0.01,
            is_blackout=False,
            take_profit_pct=0.0,
            stop_loss_pct=0.01,
        )
