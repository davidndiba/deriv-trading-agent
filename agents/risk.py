"""Turns a raw Signal into a sized RiskBreakdown. The only risk-sizing
math lives in RiskBreakdown.compute() (schemas/models.py) — this module
just derives the ATR-based stop/target distances a signal implies."""
from __future__ import annotations

from config.settings import Settings
from schemas.models import RiskBreakdown, Signal

ATR_STOP_MULTIPLE = 1.5
REWARD_RISK_RATIO = 2.0


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
