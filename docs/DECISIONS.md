# Decisions log

Record any choice that isn't obvious from SPEC.md, with the reason.

## 2026-11-18 — Contract type is hard-restricted in code, not just by convention
`tools/deriv_client.py` only exposes the calls needed for Multipliers
(`proposal` with `contract_type=MULTUP/MULTDOWN`, `buy`, `sell`,
`proposal_open_contract`, `contract_update`). There is no generic
"send raw request" passthrough exposed to the agent layer, so a future
signal implementation cannot accidentally construct a CALL/PUT/DIGITMATCH
request even by copy-pasting a Deriv doc example.

## 2026-11-18 — `types/` renamed to `schemas/`
The spec's suggested layout names a `types/` directory. A top-level Python
package literally named `types` shadows the standard-library `types` module
for any process that has the repo root on `sys.path` (every entry point
here: `uvicorn api.main:app`, `python scripts/*.py`, pytest). `typing` and
several third-party libraries (FastAPI, pydantic) `import types` internally,
so this would break imports intermittently depending on run order. Using
`schemas/` instead keeps the same role (domain models) without the clash.

## 2026-11-18 — Stake sizing lives in one place
`schemas/models.py::RiskBreakdown.stake` is always computed as
`balance * risk_per_trade_pct` (optionally halved on a blackout date). No
other module is allowed to set a stake value directly — this keeps the
"never a flat dollar stake, never martingale" rule enforceable by code
review (one function to check) rather than by convention across call sites.

## 2026-11-18 — Backtest engine duplicates no strategy math, only entry logic
`tools/backtest.py` imports `ATR_STOP_MULTIPLE`/`REWARD_RISK_RATIO` from
the new `tools/strategy_params.py` (also used by `agents/risk.py`) instead
of hardcoding its own stop/target multiples. A backtest that quietly used
different risk parameters than the live sizing logic would produce a
report that doesn't describe what Phase 3 will actually do — worse than
no backtest at all.

## 2026-11-18 — Backtest intrabar ambiguity resolved conservatively
When a single OHLC bar's range touches both the stop-loss and the
take-profit level, `simulate_trade()` assumes the stop-loss was hit first.
OHLC data alone can't tell you the actual intrabar order, and assuming the
best case here is exactly the kind of optimistic bias that inflates a
backtested win rate — see the >70% audit rule in docs/SPEC.md Phase 2.

## 2026-11-18 — Backtest runs one trade at a time, no overlap
`backtest_symbol()` does not consider a new signal until the previous
trade has closed (hit TP, hit SL, or run out of data). Concurrency/
correlation limits across multiple open positions are explicitly a Phase 4
concern (docs/PHASES.md); modeling them in the Phase 2 backtest would add
complexity without changing what Phase 2 needs to answer: is this single
signal's edge real.

## 2026-11-18 — FastAPI wraps the agent instead of the agent importing FastAPI
`api/main.py` imports from `agents/`/`tools/`, not the other way round, so
the signal/analysis/trading logic has no web-framework dependency and can be
exercised directly from the CLI runner in `scripts/` or from tests.
