"""Strategy constants shared by agents/risk.py and tools/backtest.py.

Pulled out into their own dependency-free module so the backtester can
import them without dragging in pydantic (see docs/DECISIONS.md), and so
there's exactly one place these numbers live — a backtest that silently
used different stop/target multiples than the live risk sizing would be
a lookahead-adjacent bug in its own right.
"""

ATR_STOP_MULTIPLE = 1.5
REWARD_RISK_RATIO = 2.0
