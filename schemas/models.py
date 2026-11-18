"""Domain models shared by agents/, tools/, api/.

RiskBreakdown.stake is the ONLY place stake size is computed. No other
module should set a stake value directly — see docs/DECISIONS.md.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Direction(str, Enum):
    UP = "UP"      # maps to MULTUP
    DOWN = "DOWN"  # maps to MULTDOWN


class Candle(BaseModel):
    epoch: int
    open: float
    high: float
    low: float
    close: float


class Signal(BaseModel):
    """Raw output of a strategy before risk sizing is applied."""

    symbol: str
    direction: Direction
    reason: str  # e.g. "EMA(12) crossed above EMA(26), RSI 45, ATR ok"
    entry_price: float
    atr: float
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class RiskBreakdown(BaseModel):
    """The two-sided risk/reward breakdown shown before any approval ask.

    stake is always `balance * risk_per_trade_pct`, halved on blackout
    dates. Never a flat dollar amount, never martingale/grid sizing.
    """

    balance: float
    risk_per_trade_pct: float
    blackout_halved: bool
    stake: float
    multiplier: int
    take_profit: float
    stop_loss: float
    max_loss: float   # == stake, by Multipliers design (auto stop-out)
    max_gain: float   # value at take_profit
    risk_reward_ratio: float

    @classmethod
    def compute(
        cls,
        *,
        balance: float,
        risk_per_trade_pct: float,
        is_blackout: bool,
        take_profit_pct: float,
        stop_loss_pct: float,
        max_multiplier: int = 1000,
    ) -> "RiskBreakdown":
        """stop_loss_pct/take_profit_pct are fractional underlying price
        moves (e.g. 0.01 = 1%), not dollar amounts.

        The multiplier is derived, not chosen independently: it is set so
        the stop-loss distance in price terms consumes exactly `stake`
        dollars (multiplier = 1 / stop_loss_pct), which matches how
        Multipliers' own auto stop-out caps max loss at the stake
        regardless of multiplier. This is a Phase 1/2 approximation for
        candidate-signal logging; Phase 3 reconciles it against the real
        multiplier tiers and exact payout Deriv's own `proposal` call
        returns for the symbol (see docs/DECISIONS.md).
        """
        if stop_loss_pct <= 0 or take_profit_pct <= 0:
            raise ValueError("stop_loss_pct and take_profit_pct must be > 0")

        effective_risk_pct = risk_per_trade_pct * (0.5 if is_blackout else 1.0)
        stake = round(balance * effective_risk_pct, 2)
        multiplier = min(max(1, round(1 / stop_loss_pct)), max_multiplier)
        max_loss = stake  # Multipliers auto stop-out caps loss at stake.
        max_gain = round(stake * (take_profit_pct / stop_loss_pct), 2)
        rr = round(max_gain / max_loss, 2) if max_loss else 0.0
        return cls(
            balance=balance,
            risk_per_trade_pct=risk_per_trade_pct,
            blackout_halved=is_blackout,
            stake=stake,
            multiplier=multiplier,
            take_profit=take_profit_pct,
            stop_loss=stop_loss_pct,
            max_loss=max_loss,
            max_gain=max_gain,
            risk_reward_ratio=rr,
        )


class TradeProposal(BaseModel):
    """A candidate trade with its full risk breakdown, ready to display.

    Phase 1 only ever logs these. No `buy` call exists until Phase 3, and
    even then only after an explicit human approval per proposal.
    """

    signal: Signal
    risk: RiskBreakdown
    approved: bool | None = None  # None = not yet decided (Phase 1 logging)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def render(self) -> str:
        s, r = self.signal, self.risk
        effective_pct = r.risk_per_trade_pct * (0.5 if r.blackout_halved else 1)
        return (
            f"[{s.symbol}] {s.direction.value}  ({s.reason})\n"
            f"  stake=${r.stake} (balance=${r.balance} x {effective_pct:.3%}"
            f"{' [blackout-halved]' if r.blackout_halved else ''})\n"
            f"  multiplier={r.multiplier}  TP={r.take_profit:.3%}  "
            f"SL={r.stop_loss:.3%}\n"
            f"  max_loss=${r.max_loss}  max_gain=${r.max_gain}  "
            f"R:R=1:{r.risk_reward_ratio}"
        )
