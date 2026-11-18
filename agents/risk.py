"""Turns a raw Signal into a sized RiskBreakdown. The only risk-sizing
math lives in RiskBreakdown.compute() (schemas/models.py) — this module
just derives the ATR-based stop/target distances a signal implies."""
from __future__ import annotations

from config.settings import Settings
from schemas.models import RiskBreakdown, Signal
from tools.strategy_params import ATR_STOP_MULTIPLE, REWARD_RISK_RATIO


def build_risk_breakdown(signal: Signal, balance: float, settings: Settings) -> RiskBreakdown:
    stop_loss_pct = (ATR_STOP_MULTIPLE * signal.atr) / signal.entry_price
    take_profit_pct = stop_loss_pct * REWARD_RISK_RATIO

    return RiskBreakdown.compute(
        balance=balance,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        is_blackout=settings.is_blackout_date(),
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
    )


def apply_live_stake_cap(risk: RiskBreakdown, max_stake: float) -> RiskBreakdown:
    """"Smallest viable stake first" (docs/SPEC.md Phase 4->5): clamps
    stake to max_stake, scaling max_gain by the same factor so the R:R
    ratio is unchanged. multiplier is untouched — it was derived purely
    from the stop-loss distance, not from stake (schemas/models.py), so
    it doesn't need rescaling."""
    if risk.stake <= max_stake:
        return risk
    scale = max_stake / risk.stake
    return risk.model_copy(
        update={
            "stake": max_stake,
            "max_loss": max_stake,
            "max_gain": round(risk.max_gain * scale, 2),
        }
    )
