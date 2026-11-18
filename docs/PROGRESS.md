# Progress log

Newest entry first. One entry per phase commit/push.

## Phase 8 — Deriv portfolio reconciliation (2026-11-18)
- `tools/deriv_client.py`: `get_portfolio()` (every contract Deriv shows
  as currently open) and `get_open_contract_snapshot()` (one-off status
  for a single contract, no subscription).
- `tools/reconciliation.py`: `diff_portfolio()` — pure set difference
  between local and Deriv open-contract ids, returning `(ghosts,
  orphans)`. Ghosts (local says open, Deriv disagrees) get healed by
  fetching the real outcome and updating the local record. Orphans
  (Deriv says open, local has no record) are only ever reported — this
  never silently writes a position it didn't create into the local log.
- `storage/db.py`: `get_open_contract_ids()`.
- `scripts/run_phase8_reconcile.py` — **the first non-trading script
  that does not refuse `ENV=live`.** It places no orders at all
  (`portfolio` and a one-off `proposal_open_contract` read, plus local
  `UPDATE`s to heal ghosts), so it's exactly the kind of check worth
  running against a real account after a crash or restart, not something
  that needs gating the way order-placing scripts do.
- Verified by direct execution: every `diff_portfolio()` scenario (no
  drift, ghost only, orphan only, both, both empty) and the healing flow
  against the real `storage/db.py` functions (confirming a healed ghost
  actually drops out of `get_open_contract_ids()`).
- **Not verified**: the real `portfolio`/`proposal_open_contract` calls
  against a live Deriv session — same sandbox limitation as every other
  live-API-touching phase.
- **Status: pushed.**

## Phase 7 — Walk-forward backtest validation (2026-11-18)
- `tools/backtest.py`: `split_into_folds()` (chronological, contiguous,
  never shuffled — shuffling time-series folds would leak future bars
  into an earlier fold) and `walk_forward_report()`, which runs
  `backtest_symbol()` independently per fold and returns one
  `BacktestReport` per fold via `summarize()`'s new optional `label`.
  There's no parameter-fitting step anywhere in this codebase
  (`ATR_STOP_MULTIPLE`/`REWARD_RISK_RATIO` are fixed constants, not
  optimized on history), so this isn't train/test in the ML sense — it's
  a consistency check: a signal that only wins in one historical stretch
  isn't an edge.
- `storage/db.py`: `backtests.label` column + migration, so a fold's
  result records which fold it was (`'fold 2/4'`), threaded through
  `log_backtest_result()`.
- `scripts/run_phase7_walk_forward_backtest.py`: pulls the same 5000
  historical candles as Phase 2, splits into 4 folds, prints + logs each
  fold's report, flags any individual fold whose win rate clears 70%
  (Phase 2's existing rule, just applied per fold now), and prints the
  win-rate spread across folds for a human to eyeball — deliberately no
  invented auto-threshold for "how much spread is too much," unlike the
  70% rule which has real justification behind it. Refuses `ENV=live`.
- Verified by direct execution in this sandbox: fold-splitting on exact
  and uneven candle counts (confirming folds reconstruct the original
  chronological order with no gaps or overlaps), the `backtests.label`
  migration against a hand-built pre-migration database, and
  `walk_forward_report()` correctly isolating a winning fold from a
  losing one in a hand-built two-fold scenario. Full regression pass
  across all six directly-executable test modules confirms nothing
  earlier broke.
- **Not verified**: against real historical Deriv data, same sandbox
  limitation as every backtest-related phase so far.
- **Status: pushed.**

## Phase 6 — CI pipeline (2026-11-18)
- `.github/workflows/ci.yml`: installs `requirements.txt` and runs
  `pytest tests/ -v` on every push/PR to `main`, Python 3.11, with pip
  caching.
- Validated the workflow YAML itself with `pyyaml` in this sandbox
  (available here even though the project's own dependencies aren't) —
  caught and fixed a real bug in the process: an unquoted `on:` key
  parses as the boolean `True` under YAML 1.1, which is exactly the
  well-known GitHub Actions gotcha. GitHub's own parser tolerates it, but
  `"on":` is the correct, unambiguous form, now fixed in the committed
  file.
- **This is the first time anything in this repo gets to run against a
  real `pip install`** — this sandbox never had `pip`/`venv`, so every
  prior phase's "verified by direct execution" notes only ever covered
  the dependency-free parts of each module (indicators, backtest engine,
  exposure math, DB functions, etc.). Once this workflow runs on GitHub,
  check its result — it covers `pydantic`/`fastapi`/`python_deriv_api`
  code paths (schemas/models.py, agents/signals.py, agents/risk.py,
  api/main.py) that could not be exercised here at all before now.
- **Status: pushed. Watch the Actions tab on the first push for the
  actual pass/fail — don't assume it passes just because it's wired up.**

## Cross-cutting — Read-only reporting API (2026-11-18)
Closes out a Phase 0 deliverable that was left as just a health check:
docs/SPEC.md asks for "FastAPI service wrapping the agent's internals...
instead of trading logic getting reimplemented" elsewhere. Not a new
numbered phase — it reports on state the existing phases already produce,
it doesn't add trading behavior.
- `storage/db.py`: `list_proposals`, `list_trades` (filterable by
  `env`/`status`), `list_backtests` (filterable by `symbol`).
- `api/main.py`: `GET /proposals`, `GET /trades`, `GET /trades/pnl/today`,
  `GET /backtests`, alongside the existing `/health`. **Deliberately
  read-only** — there is no endpoint that proposes, approves, or buys
  anything. The CLI y/n gate in every trading script stays the only path
  to a `buy` call; an API that could trigger one would undermine that.
- Verified by direct execution (still no pip/venv in this sandbox to run
  FastAPI itself): all four query functions against hand-built proposal/
  trade/backtest rows, including env/status filtering and limit
  enforcement.
- **Not verified**: the FastAPI routes themselves (request/response
  wiring, query-param validation) — only the storage-layer functions
  they call. Run `uvicorn api.main:app --reload` yourself once
  dependencies are installed and hit `/health` first.

## Phase 5 — Real-money cutover (2026-11-18)
- `config/settings.py`: `LIVE_MAX_STAKE_USD` (default 1.0),
  `LIVE_MIN_DEMO_SOAK_DAYS` (default 14), `LIVE_MIN_DEMO_TRADES`
  (default 20).
- `storage/db.py`: added an `env` ('demo'|'live') column to `trades`,
  with an `ALTER TABLE` migration in `get_connection()` for any
  pre-existing local `trading_agent.db` from an earlier phase.
  `get_open_trades`/`get_open_trade_count`/`get_realized_pnl_today` now
  take an `env` parameter (defaulting to `'demo'`, so every Phase 3/4
  call site is unchanged) so a live run's guards are never polluted by
  demo history, and demo's aren't polluted by live. Added
  `get_demo_track_record()`, always scoped to `env='demo'` regardless of
  caller, for the Phase 5 soak-period gate.
- `agents/risk.py`: `apply_live_stake_cap()` clamps stake to
  `LIVE_MAX_STAKE_USD` and scales `max_gain` by the same factor, keeping
  R:R accurate ("smallest viable stake first").
- `scripts/run_phase5_live_trading.py` — **the only script in this repo
  that will run against a live account**; every other script refuses
  `ENV=live` outright, this one refuses anything else. Gates, in order:
  (1) `ENV=live` required, (2) a demo track-record check with no
  override flag (see docs/DECISIONS.md), (3) a second confirmation
  requiring an exact typed phrase, separate from the `ENV=live` flag
  itself, (4) the same per-trade CLI y/n every other phase requires —
  unchanged, (5) the live stake cap applied on top of the normal
  risk-% sizing. Daily kill-switch, concurrency cap, correlation guard,
  and Telegram alerts are Phase 4's logic, scoped to `env='live'`.
- Verified in this sandbox by direct execution: the schema migration
  against a hand-built pre-migration database, env-scoped isolation
  between demo and live P&L/open-position counts (a demo loss does not
  trip a live kill-switch and vice versa), the stake-cap math preserving
  R:R, and all four soak-period gate scenarios in
  `tests/test_live_cutover_gate.py` — including confirming that live
  trades never count toward the demo track record.
- **Not verified**: everything already flagged as unverified in Phases
  3-4 (the live Deriv `proposal`/`buy`/`subscribe` calls against a real
  session) still applies here, now for real money. The confirmation-
  phrase and approval-prompt functions themselves couldn't be executed
  in this sandbox (the script transitively imports pydantic, which isn't
  installable here) — read them yourself before trusting this script;
  they're short.
- **This does not mean Phase 3/4 have actually run clean on demo for
  2-4 weeks** — they haven't been run against a real account at all yet.
  The soak-period gate exists so the script itself refuses to proceed
  until that's genuinely true, not so that building this code substitutes
  for it.
- **Status: pushed for review.**

## Phase 4 — Hardening, still demo-only (2026-11-18)
- `config/settings.py`: added `MAX_CONCURRENT_CONTRACTS` (default 3),
  `MAX_CORRELATED_SAME_DIRECTION` (default 1), and optional
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`.
- `tools/exposure.py`: currency-overlap correlation guard — splits a
  forex symbol into base/quote currency codes (gold and synthetic
  indices just match themselves) and flags a candidate trade as
  correlated with an existing open position when they share a currency
  and the same direction. This is the literal "don't go long 3 USD pairs
  at once" example from docs/SPEC.md, not a measured correlation
  coefficient — see docs/DECISIONS.md.
- `storage/db.py`: added `get_open_trades()` and `get_open_trade_count()`.
- `tools/telegram_notifier.py`: stdlib-only (urllib, no new dependency)
  alerting. **Notify-only** — it cannot approve or reject a trade; the
  CLI y/n gate from Phase 3 is unchanged and is still the only path to a
  `buy` call. This was an explicit v1 deferral in docs/SPEC.md's own
  non-negotiables, not something this phase changes.
- `scripts/run_phase4_demo_trading.py`: Phase 3's flow plus the
  concurrency cap and correlation guard checked before a signal is even
  shown for approval, and Telegram alerts on trades opened/closed, the
  kill-switch firing, and the correlation guard blocking a trade.
  Refuses `ENV=live`, same as every prior phase.
- Verified by direct execution in this sandbox (still no pip/venv here):
  the new settings fields and their validation (stubbing out the
  `dotenv` import, which isn't installed), all of `tools/exposure.py`'s
  logic against hand-built open-trade scenarios, `get_open_trades`/
  `get_open_trade_count` against the real SQLite functions, and the
  Telegram notifier's request construction (and its disabled no-op path)
  against a mocked `urlopen` — no real bot token involved.
- **Not verified**: a real Telegram bot end-to-end (needs a real
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from your own BotFather setup),
  and everything already flagged as unverified in Phase 3 still applies
  (the live `proposal`/`buy`/`subscribe` calls).
- **Phase 3 has not actually been run against a real demo account yet**
  — this phase's guards don't change that. Per docs/PHASES.md, Phase 4
  isn't *done* (i.e. real money shouldn't be on the table) until Phase 3
  has run clean on demo for 2-4 weeks. Building this code now doesn't
  satisfy that; only time and a clean track record do.
- **Status: pushed for review.**

## Phase 3 — Demo paper trading with approval gate (2026-11-18)
- `tools/deriv_client.py`: added `get_proposal` (MULTUP/MULTDOWN only —
  there is no way to pass another contract_type through this method),
  `buy_contract`, `sell_contract`, `contract_update`, and
  `subscribe_open_contract`. Call shapes verified against the official
  `python-deriv-api` usage examples (see docs/DECISIONS.md) since this
  sandbox can't install the library or hold a real session.
  `limit_order.take_profit`/`stop_loss` are dollar amounts, which line up
  exactly with `RiskBreakdown.max_gain`/`max_loss` — no unit conversion
  needed between the risk model and the live order.
- `storage/db.py`: added a `trades` table, `log_trade_opened()`,
  `log_trade_closed()`, and `get_realized_pnl_today()` for the daily
  kill-switch.
- `scripts/run_phase3_demo_trading.py`: for each symbol with a signal,
  prints the full two-sided risk/reward breakdown, asks for an explicit
  y/n (`default_approval_prompt`, injectable for testing), logs the
  decision whether approved or rejected, and only calls `buy` on
  approval. Checks the daily kill-switch (realized loss today vs
  `daily_loss_limit_pct * balance`) before proposing anything. Every
  bought contract is monitored via a `proposal_open_contract` subscription
  (not polled) until it closes, and the close is logged. Refuses to run
  with `ENV=live`.
- Verified in this sandbox by direct execution (still no pip/venv here):
  the daily kill-switch threshold arithmetic against six hand-picked
  realized-P&L values, and `tests/test_daily_kill_switch.py`'s three
  scenarios (no losses yet, losses crossing the limit, net winner despite
  one losing trade) against the real `storage/db.py` functions — these
  have no pydantic dependency so they ran for real, not just by
  inspection.
- **Not verified**: the actual Deriv `proposal`/`buy`/`subscribe` calls
  against a live demo session, and whether `python_deriv_api` raises on
  an API error response or returns an `{"error": ...}` dict (the script
  currently handles both defensively — see docs/DECISIONS.md). Test this
  against your own demo account with small stakes before trusting it,
  and expect to need a few fixes once you see real responses.
- **Status: pushed for review.**

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
