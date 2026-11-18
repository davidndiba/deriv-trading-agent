# Progress log

Newest entry first. One entry per phase commit/push.

## Phase 15 — Web dashboard (2026-11-18)
Requested feature: "track up profits... analyze better." A visual view
on top of the reporting API's existing JSON endpoints.
- `api/dashboard.py`: the dashboard's HTML/JS as a plain string — no
  templating engine, no new Python dependency, no JS framework or CDN
  dependency either (vanilla JS, an inline SVG equity curve). Fetches
  `/trades` and `/trades/pnl/today` client-side; cannot place, approve,
  or reject a trade (no endpoint it calls can do that — see
  `api/main.py`'s docstring).
- `api/main.py`: `GET /dashboard` serves it.
- **Actually verified in a real browser**, not just read over — this
  sandbox can't run the FastAPI app itself (no pip), so instead: served
  the static HTML via Python's stdlib `http.server` first against no
  API at all (confirmed fetch failures are caught cleanly, no uncaught
  JS errors, page renders its placeholder state correctly), then against
  a second stdlib-server mock returning realistic trade data shaped
  exactly like `/trades`/`/trades/pnl/today`'s real responses (confirmed
  the summary cards, the color-coded trades table, and the equity curve
  — including that a win-then-loss sequence correctly plots as rising
  then falling — all compute correctly from that data). Screenshots
  confirm both states visually.
- `tests/test_dashboard.py`: structural sanity checks (well-formed HTML,
  required element ids present, only read-only endpoints referenced, no
  POST/buy/sell/approve anywhere in the page) — verified by direct
  execution. Full regression across all 12 dependency-free test modules
  confirms nothing earlier broke.
- **Not verified**: serving it through the actual FastAPI app (only the
  static HTML/JS itself was exercised in a browser) — once you have
  `pip` available, run `uvicorn api.main:app --reload` and open
  `/dashboard` to confirm the real wiring.
- **Status: pushed.**

## Phase 14 — News-event blackout guard (2026-11-18)
Requested feature: "track profits better, analyze better" — a classic
risk-management gap this agent had until now: nothing stopped it from
proposing a trade seconds before NFP, FOMC, or CPI, where price can spike
well outside anything a signal backtested on calmer conditions.
- `tools/news_calendar.py`: fetches Forex Factory's free weekly calendar
  export (no API key needed — see docs/DECISIONS.md for how this was
  found and why it's safe to rely on for this), parses it into
  `NewsEvent`s, and `is_within_news_blackout()` checks whether a given
  time falls in a configurable window around a high-impact event for a
  set of currencies.
- `config/settings.py`: `NEWS_BLACKOUT_ENABLED` (**default true** —
  the one config flag in this repo that changes existing scripts'
  behavior on deploy, deliberately, since it only ever reduces trading),
  `NEWS_BLACKOUT_MINUTES_BEFORE`/`_AFTER` (default 30/30),
  `NEWS_BLACKOUT_MIN_IMPACT` (default "High").
- Wired into `scripts/run_phase4_demo_trading.py` and
  `run_phase5_live_trading.py`: the calendar is fetched once per run;
  each symbol's currencies (reusing `tools/exposure.py::currency_exposure`,
  the same mapping the correlation guard already uses) are checked
  against it before a signal is shown for approval. A fetch/parse
  failure fails closed — no new trades proposed for that run — rather
  than silently assuming there's no news.
- Verified by direct execution: parsing (including a deliberately
  malformed row, confirming it's skipped rather than crashing the whole
  fetch), blackout-window boundary math (inclusive edges, both sides),
  currency and impact-level filtering, and the fetch path against both a
  mocked success and a mocked failure (confirming the failure
  propagates rather than returning an empty list) — using real field
  values captured from the live feed while building this, not assumed
  from documentation. Full regression across all 11 dependency-free
  test modules confirms nothing earlier broke.
- **Not verified**: wiring inside `run_phase4`/`run_phase5` themselves
  needs pydantic (same sandbox limitation as every trading script), and
  the live feed's actual behavior over time (format changes, uptime)
  is unknown — it's an unofficial export, not a contractually documented
  API.
- **Status: pushed.**

## Fix — CI was red from the first real run (2026-11-18)
Every CI run from Phase 6 onward failed in ~14 seconds — confirmed via
the GitHub Actions UI, which the detailed logs require sign-in to read,
so the root cause was tracked down from `python_deriv_api`'s and
`uvicorn`'s published PyPI metadata instead: `python_deriv_api` pins
`websockets==10.3` exactly, while `uvicorn[standard]`'s extra requires
`websockets>=13.0` — an unsatisfiable pair, so `pip install` fails
during dependency resolution before anything gets built, matching the
~14s runtime. `requirements.txt` now uses plain `uvicorn` (no
`[standard]`); confirmed from uvicorn's own metadata that this drops the
`websockets` requirement entirely, and `api/main.py` has no websocket
routes that would need it. **This is the exact kind of bug this
sandbox's missing `pip`/`venv` could never have surfaced** — every
"verified by direct execution" note throughout this build covered only
code that doesn't need installing, and a dependency conflict is
invisible to that.

**Confirmed fixed**: run #9 (commit 070fb97) passed — "Success", 31s
total, the `test` step itself ran 29s (long enough for a real
`pip install` of the full dependency set, unlike the ~14s immediate
resolver failures before it). This is the first time every
pydantic/FastAPI/`python_deriv_api`-dependent module in this repo
(`schemas/models.py`, `agents/signals.py`, `agents/risk.py`,
`agents/mean_reversion.py`, and every test file that needed them) has
actually been imported and run anywhere, not just reasoned through.

## Phase 13 — Daily/weekly performance report (2026-11-18)
- `storage/db.py`: `get_trades_closed_since()` — every closed trade for
  an env since a given ISO timestamp, oldest first.
- `tools/reporting.py`: `sparkline()` (pure-Python unicode-block equity
  curve) and `build_performance_report()` — takes plain dicts (the exact
  shape `storage.db` already returns), not pydantic models, so it has no
  third-party dependency at all.
- `scripts/run_phase13_performance_report.py` — **the only script that
  doesn't connect to Deriv at all.** Everything it needs is already in
  the local trade log, so it's safe and fast to run anytime, offline
  even. `--period daily|weekly`, `--env demo|live`, `--notify` (sends via
  the existing notify-only Telegram client), `--no-save` (skips writing
  to `reports/`, now gitignored).
- Verified by direct execution: `sparkline()` against flat/empty/
  increasing series, `build_performance_report()` against a hand-built
  set of closed trades (totals, win rate, P&L, per-symbol breakdown all
  checked), `get_trades_closed_since()` against real DB data (date
  filtering, env isolation, chronological ordering), and an end-to-end
  smoke test wiring real DB output straight into the report builder.
  Full regression across all 10 dependency-free test modules confirms
  nothing earlier broke.
- **Not verified**: the Telegram `--notify` path (needs a real bot
  token) and the CLI argument wiring itself (`argparse` behavior wasn't
  exercised, only the functions it calls).
- **Status: pushed. This closes out the recommended post-v1 roadmap
  from docs/PHASES.md (items 6-13).**

## Phase 12 — Realistic spread modeling in the backtester (2026-11-18)
- `tools/backtest.py::backtest_symbol()`/`walk_forward_report()`: new
  optional `spread_pct` parameter, **defaulting to 0.0** — every call
  site in Phase 2/7/9/10 keeps behaving exactly as before unless it
  opts in. A long's effective fill price shifts up by `spread_pct`
  (a short's shifts down); both the stop-loss and take-profit barriers
  are then placed relative to that worse fill, so a long's take-profit
  sits farther away and its stop-loss sits closer — the same direction
  real spread cost pushes both barriers.
- `scripts/run_phase12_spread_aware_backtest.py`: runs the Phase 1
  signal frictionless and spread-adjusted side by side per symbol, using
  `get_strategy_params()` for consistency with Phase 11. Refuses
  `ENV=live`.
- **`ASSUMED_SPREAD_PCT = 0.0002` is a placeholder, not a number sourced
  from Deriv's own spread data** — this sandbox has no way to check a
  real account's actual spreads. The mechanism (which barrier moves,
  which direction) is verified; the specific magnitude is yours to
  replace with what you actually observe. See docs/DECISIONS.md.
- Verified by direct execution: `spread_pct=0.0` produces byte-identical
  entry/stop-loss/take-profit values and outcomes to the pre-Phase-12
  code path (explicit backward-compatibility check), a long's and a
  short's barriers both shift against the trader in the expected
  direction with the expected magnitude, and a hand-built scenario where
  adding 1% spread flips what was a clean win at zero spread into a
  loss. Full regression across all 9 dependency-free test modules
  confirms nothing earlier broke.
- **Status: pushed.**

## Phase 11 — Per-symbol strategy parameters (2026-11-18)
- `tools/strategy_params.py`: added `SYMBOL_STRATEGY_PARAMS` (gold and
  the configured synthetic index get their own
  `atr_stop_multiple`/`reward_risk_ratio`; anything else falls back to
  the existing global defaults, so default behavior for every symbol
  not explicitly listed is unchanged) and `get_strategy_params(symbol)`.
- `agents/risk.py::build_risk_breakdown()` now looks up
  `get_strategy_params(signal.symbol)` instead of the two module-level
  constants directly — this is what Phases 3-5's live/demo sizing uses.
- Updated every backtest script (Phase 2, 7, 9's two calls, 10) to pass
  `get_strategy_params(symbol)` into `backtest_symbol()`/
  `walk_forward_report()` instead of relying on those functions' default
  args — otherwise a backtest could silently use different risk
  parameters than what live sizing would actually use for that symbol,
  undermining the whole point of backtesting before trusting a signal.
- Verified by direct execution: override lookup for both configured
  symbols, fallback to defaults for an unlisted symbol, and that the two
  overrides and the default are all genuinely distinct from each other.
  Full regression across all 8 dependency-free test modules confirms
  nothing earlier broke.
- **Status: pushed.**

## Phase 10 — A second, independently backtested signal (2026-11-18)
- `tools/indicators.py`: `sma()`, `rolling_stddev()` (population
  stddev, the standard Bollinger Bands convention), `bollinger_bands()`
  — all pure Python, same style as every other indicator here.
- `agents/mean_reversion.py`: `generate_mean_reversion_signal()` — the
  opposite style from `agents/signals.py`'s trend-following crossover.
  Fades the move (bets on reversion) when price closes outside a
  Bollinger Band AND RSI confirms the extreme, filtered by the same
  ATR% volatility band as the first signal. A separate module entirely
  — nothing shared with or changed in `agents/signals.py`.
- `scripts/run_phase10_mean_reversion_backtest.py`: backtests this
  signal through the exact same engine and audit rule as Phase 2/7.
  Refuses `ENV=live`.
- Verified by direct execution: `sma`/`rolling_stddev`/`bollinger_bands`
  against hand-computed values (including a flat series collapsing
  upper/lower bands onto the middle band exactly). Found and checked two
  synthetic series — a late sharp spike up, and a late sharp drop — that
  trigger the fade-down and fade-up cases respectively, confirmed
  against the already-verified Bollinger/RSI/ATR math before writing
  them into `tests/test_mean_reversion.py`. Full regression across all
  7 dependency-free test modules confirms nothing earlier broke.
- **Not verified**: `generate_mean_reversion_signal()` itself needs
  pydantic — same sandbox limitation as every `schemas.models`-dependent
  module throughout this build.
- **Status: pushed.**

## Phase 9 — Multi-timeframe confirmation filter (2026-11-18)
- `tools/multi_timeframe.py`: `build_htf_trend_lookup()` (trend label
  per higher-timeframe candle — 'UP'/'DOWN'/None, based on that candle's
  close vs. its own EMA) and `lookup_htf_trend()` (bisect lookup of the
  most recent HTF candle at or before a given epoch — no lookahead, by
  construction). No dependency, same as tools/indicators.py.
- `agents/signals.py`: `generate_confirmed_signal()` — a **new, separate
  function**. `generate_signal()` itself is unchanged, so every existing
  script/backtest that calls it is unaffected.
- `scripts/run_phase9_mtf_backtest.py`: backtests the baseline signal
  and the HTF-confirmed signal side by side per symbol (1m candles for
  the base signal, 15m candles for confirmation) and logs both reports.
  **This is a comparison, not a swap** — nothing here changes what
  Phases 3-5's trading scripts actually trade; see docs/DECISIONS.md.
  Refuses `ENV=live`.
- Verified by direct execution: `build_htf_trend_lookup`/
  `lookup_htf_trend` against hand-built uptrend/downtrend/flat/
  too-short-history series, confirming the None-until-warmed-up
  behavior and that an exactly-flat series never claims a trend. Full
  regression across all 7 dependency-free test modules confirms nothing
  earlier broke.
- **Not verified**: `generate_confirmed_signal()`/`tests/test_signals_htf.py`
  need pydantic (same as `test_signals.py` always has) — reasoned through
  carefully against the already-verified HTF lookup logic and the
  already-verified base-signal series from `test_signals.py`, but not
  executed here.
- **Status: pushed.**

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
