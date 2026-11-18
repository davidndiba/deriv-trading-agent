# Progress log

Newest entry first. One entry per phase commit/push.

## Phase 2 — Backtest validation (2026-11-18)
- `tools/strategy_params.py`: pulled `ATR_STOP_MULTIPLE`/`REWARD_RISK_RATIO`
  out of `agents/risk.py` into their own dependency-free module so the
  backtester uses the exact same risk parameters as live sizing, and so it
  stays importable/testable without pydantic.
- `tools/backtest.py`: walk-forward engine. At bar i, the signal function
  only ever sees `candles[:i+1]` — never a later bar (lookahead-safe by
  construction). Each trade's TP/SL outcome is found by scanning forward;
  if a single bar's range touches both levels, stop-loss is assumed to
  win (conservative — see docs/DECISIONS.md). One trade at a time, no
  overlap. `summarize()` reports win rate, avg R-multiple, and max
  drawdown in R, and flags `needs_audit=True` when win rate exceeds 70%
  over >= 10 closed trades, per docs/SPEC.md's lookahead-bug warning.
- `storage/db.py`: added a `backtests` table and `log_backtest_result()`.
- `scripts/run_phase2_backtest.py`: pulls 5000 historical 1-minute candles
  per symbol from the demo account (purely as a historical-data source —
  no trading session state needed), runs the Phase 1 signal through the
  backtest engine, prints + logs the report per symbol, and prints an
  explicit stop-and-audit warning if win rate looks suspicious. Refuses to
  run with `ENV=live`. **No `buy`/`sell`/`proposal` call exists anywhere
  in this phase's code.**
- Verified in this sandbox by direct execution (not pytest, which still
  isn't installable here): hand-constructed win/loss/both-touched/
  ran-out-of-data scenarios for `simulate_trade()`, a two-trade no-overlap
  sequence for `backtest_symbol()`/`summarize()` checked against
  hand-computed win rate/avg-R/drawdown, and a forced 100%-win-rate series
  confirmed to set `needs_audit=True`. All of `tests/test_backtest.py`'s
  functions were also run manually end-to-end and passed.
- **Not run against real historical Deriv data** — same sandbox limitation
  as Phase 1 (no `pip`/`venv` here to install `python_deriv_api`). Run
  `scripts/run_phase2_backtest.py` yourself and read the printed report
  (and the stop-and-audit warning, if it fires) before deciding whether
  this signal is worth taking to Phase 3.
- **Status: pushed for review.**

## Phase 1 — Data + analysis only (2026-11-18)
- `tools/indicators.py`: pure-Python EMA, Wilder's RSI, Wilder's ATR. No
  pandas/numpy/pydantic dependency, verified by hand against known test
  vectors (constant series, strictly monotonic series, a fixed true-range
  example) since this sandbox has no `pip`/`venv` to run pytest.
- `agents/signals.py`: one combined signal — EMA(12)/EMA(26) crossover,
  filtered by RSI (reject if already overbought/oversold in the crossover's
  direction) and an ATR% volatility band (reject dead or extreme-spike
  markets). Exactly as scoped in docs/SPEC.md Phase 1 ("2-3 signals max").
- `agents/risk.py`: derives ATR-based stop/target distances from a signal
  and hands them to `RiskBreakdown.compute()` — the only place stake size
  is computed.
- `schemas/models.py`: `RiskBreakdown.compute()` reworked so `take_profit_pct`
  /`stop_loss_pct` are fractional price moves and the multiplier is derived
  (not chosen independently) from the stop-loss distance. Documented as a
  Phase 1/2 approximation to be reconciled against Deriv's real `proposal`
  payout in Phase 3 — see docs/DECISIONS.md.
- `tools/deriv_client.py`: added `parse_candles()` to turn a
  `ticks_history` (style=candles) response into `Candle` models.
- `scripts/run_phase1.py`: connects to the DEMO account, pulls candles per
  configured symbol, runs the signal, prints + logs the full two-sided
  risk/reward breakdown for every candidate signal. Refuses to run at all
  if `ENV=live`. **No `buy`/`sell`/`proposal` call exists anywhere in this
  phase's code.**
- Tests added for indicators (executed directly — no third-party deps) and
  for the signal logic (`tests/test_signals.py`, using hand-verified
  synthetic series since pydantic can't be installed in this sandbox to
  run pytest — see the note below).
- **Not verified end-to-end against a live Deriv demo account** — this
  sandbox has no outbound way to hold a real API token/session for this
  review, and no `pip`/`venv` to install `python_deriv_api`/`pydantic`/
  `fastapi` to run the test suite. Review `scripts/run_phase1.py` and the
  module list above, then run it yourself against your demo `.env` to
  confirm the live wiring.
- **Status: pushed for review. Stopping here before Phase 2 per
  docs/SPEC.md ("implement Phase 1 end-to-end, and stop there for
  review").**

## Phase 0 — Repo scaffold (2026-11-18)
- Created directory structure: `agents/`, `tools/`, `config/`, `types/`,
  `api/`, `storage/`, `docs/`, `scripts/`, `tests/`.
- Added `docs/SPEC.md` (verbatim build spec, source of truth for scope).
- Added `docs/PHASES.md` (Phase 0-5 roadmap and exit criteria).
- Added config loader (`config/settings.py`) reading `.env`: `APP_ID`,
  `API_TOKEN`, `ENV` (demo/live), `RISK_PER_TRADE_PCT`,
  `DAILY_LOSS_LIMIT_PCT`, `BLACKOUT_DATES`.
- Added domain types (`types/models.py`): `Signal`, `RiskBreakdown`,
  `TradeProposal` — no `buy` fields populated anywhere yet.
- Added Deriv client wrapper stub (`tools/deriv_client.py`): connect,
  authorize, balance, ticks_history only. No proposal/buy/sell/
  contract_update methods exist yet (that's Phase 1 and Phase 3).
- Added SQLite schema (`storage/db.py`) for signal/proposal logging.
- Added FastAPI skeleton (`api/main.py`) with a health check endpoint.
- No live Deriv connection made yet. No contracts bought. No signals
  computed yet.
- **Status: pushed for review.**
