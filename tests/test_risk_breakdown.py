from schemas.models import RiskBreakdown


def test_stake_is_balance_times_risk_pct():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=False,
        multiplier=100,
        take_profit_pct=20.0,
        stop_loss_pct=10.0,
    )
    assert rb.stake == 10.0
    assert rb.max_loss == rb.stake


def test_blackout_date_halves_stake():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=True,
        multiplier=100,
        take_profit_pct=20.0,
        stop_loss_pct=10.0,
    )
    assert rb.stake == 5.0
    assert rb.blackout_halved is True


def test_risk_reward_ratio_matches_tp_sl_ratio():
    rb = RiskBreakdown.compute(
        balance=1000.0,
        risk_per_trade_pct=0.01,
        is_blackout=False,
        multiplier=100,
        take_profit_pct=20.0,
        stop_loss_pct=10.0,
    )
    assert rb.risk_reward_ratio == 2.0
