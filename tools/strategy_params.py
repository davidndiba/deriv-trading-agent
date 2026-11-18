"""Strategy constants shared by agents/risk.py and tools/backtest.py.

Pulled out into their own dependency-free module so the backtester can
import them without dragging in pydantic (see docs/DECISIONS.md), and so
there's exactly one place these numbers live — a backtest that silently
used different stop/target multiples than the live risk sizing would be
a lookahead-adjacent bug in its own right.
"""

ATR_STOP_MULTIPLE = 1.5  # default/fallback
REWARD_RISK_RATIO = 2.0  # default/fallback

# Per-symbol overrides — gold, forex majors, and synthetic indices don't
# all move the same way, so one global stop/target multiple is a
# simplification. A symbol not listed here falls back to the defaults
# above. (symbol -> (atr_stop_multiple, reward_risk_ratio))
SYMBOL_STRATEGY_PARAMS: dict[str, tuple[float, float]] = {
    "frxXAUUSD": (2.0, 2.5),  # gold: wider stops for bigger ATR swings
    "1HZ100V": (1.0, 2.0),  # synthetic index: steadier volatility profile, tighter stop
}


def get_strategy_params(symbol: str) -> tuple[float, float]:
    """(atr_stop_multiple, reward_risk_ratio) for a symbol — the
    override from SYMBOL_STRATEGY_PARAMS if one exists, else the global
    defaults. This is the single place both live risk sizing
    (agents/risk.py) and every backtest script look up these numbers, so
    a backtest can never silently use different parameters than what
    Phase 3+ would actually trade with for that symbol."""
    return SYMBOL_STRATEGY_PARAMS.get(symbol, (ATR_STOP_MULTIPLE, REWARD_RISK_RATIO))
