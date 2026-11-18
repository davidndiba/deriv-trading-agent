# Decisions log

Record any choice that isn't obvious from SPEC.md, with the reason.

## 2026-11-18 — Contract type is hard-restricted in code, not just by convention
`tools/deriv_client.py` only exposes the calls needed for Multipliers
(`proposal` with `contract_type=MULTUP/MULTDOWN`, `buy`, `sell`,
`proposal_open_contract`, `contract_update`). There is no generic
"send raw request" passthrough exposed to the agent layer, so a future
signal implementation cannot accidentally construct a CALL/PUT/DIGITMATCH
request even by copy-pasting a Deriv doc example.

## 2026-11-18 — Per-symbol strategy params live in code, not `.env`
`tools/strategy_params.py::SYMBOL_STRATEGY_PARAMS` is a plain Python
dict, not an environment variable. ATR_STOP_MULTIPLE/REWARD_RISK_RATIO
are strategy decisions — what counts as "stopped out" or "at target" for
a given symbol — not deployment configuration like an API token or a
risk percentage. Putting them in code keeps the actual strategy
reviewable in a diff; encoding them into an env-var string
(`"frxXAUUSD:2.0:2.5,..."`) would hide that same decision behind a
parsing scheme for no real benefit. `get_strategy_params()` is the one
place both `agents/risk.py` (live/demo sizing) and every backtest script
look this up, specifically so a backtest can never silently use
different parameters than what Phase 3+ would actually trade with for
that symbol — the same principle as the ATR_STOP_MULTIPLE/
REWARD_RISK_RATIO factoring-out decision from Phase 2.

## 2026-11-18 — Multi-timeframe confirmation is a comparison, not a swap
`generate_confirmed_signal()` (agents/signals.py) is a new, separate
function — `generate_signal()` itself is untouched, so every Phase 1-8
script and backtest that already calls it keeps doing exactly what it
was verified to do. `scripts/run_phase9_mtf_backtest.py` only ever
compares the confirmed signal against the baseline via the same backtest
engine; nothing wires the HTF filter into
`scripts/run_phase{3,4,5}_*.py`. Adopting it into live/demo trading is a
decision to make after reading the comparison, not something a new
script should decide unilaterally — the whole project's pattern so far
has been "backtest before trusting a signal," and this is no different
just because the signal is a refinement of one already in use.

## 2026-11-18 — Phase 5's demo-soak check has no override flag
`scripts/run_phase5_live_trading.py` refuses to proceed past its
confirmation banner unless the local trade log shows at least
`LIVE_MIN_DEMO_TRADES` closed demo trades spanning at least
`LIVE_MIN_DEMO_SOAK_DAYS` days (both from `storage.db.get_demo_track_record`,
always scoped to `env='demo'` regardless of what's being run). There is
deliberately no env var or CLI flag to skip this check. The only way
around it is editing this file directly — a conscious, visible act, not
a config toggle that could be flipped by habit or under pressure to "just
get it live." This mirrors docs/SPEC.md's own non-negotiable: "No
real-money contracts before Phase 3 has run clean on demo for at least
2-4 weeks."

## 2026-11-18 — Demo and live trades are isolated end-to-end
`trades.env` ('demo' | 'live') exists so `get_open_trades`,
`get_open_trade_count`, and `get_realized_pnl_today` can be scoped per
env. Without this, a live run's kill-switch/concurrency/correlation
guards would be polluted by demo history (or vice versa) — demo and live
are different Deriv accounts with different balances, so mixing their
P&L or position counts would make every Phase 4/5 guard meaningless.
`get_connection()` migrates a pre-existing local `trading_agent.db` (one
created before this column existed) via `ALTER TABLE ... ADD COLUMN`,
defaulting old rows to `'demo'` — verified against a hand-built
pre-migration database in this sandbox (see docs/PROGRESS.md).

## 2026-11-18 — Live stake cap scales max_gain, not risk_reward_ratio
`agents/risk.py::apply_live_stake_cap()` clamps `stake`/`max_loss` to
`LIVE_MAX_STAKE_USD` and scales `max_gain` by the same factor, so the
displayed R:R stays accurate. It deliberately does not touch
`multiplier`, since that was derived purely from the stop-loss distance
(schemas/models.py), not from stake — rescaling it would quietly change
the stop-loss distance the signal actually calculated.

## 2026-11-18 — Telegram is notify-only, never an approval channel
docs/SPEC.md's own non-negotiables say "CLI y/n for v1; Telegram
approve/reject can come later" — that's an explicit deferral, not an
oversight. `tools/telegram_notifier.py` only ever sends alerts (trade
opened/closed, kill-switch fired, correlation guard blocked a trade); it
has no inbound path (no webhook, no getUpdates polling) and cannot
influence whether a `buy` happens. Building an interactive approve/reject
flow over Telegram would mean trusting an unauthenticated inbound webhook
or a polling loop as a safety-critical control path, with zero ability to
test that against a real bot in this sandbox — that's a bigger, separate
decision than "Phase 4 hardening," so it stayed out of v1.

## 2026-11-18 — Phase 4's guards are structural, not a substitute for the soak period
docs/PHASES.md says Phase 4 is only *done* once Phase 3 has run clean on
demo for 2-4 weeks. The concurrency cap and correlation guard in
`scripts/run_phase4_demo_trading.py` are code that can be written and
reviewed now, but they don't satisfy that requirement by existing — they
reduce risk *within* a trading session, not across time. Phase 5 (real
money) still requires the actual soak period to have happened, regardless
of how hardened Phase 4's code is.

## 2026-11-18 — Correlation guard is a currency-overlap heuristic, not real correlation
`tools/exposure.py::currency_exposure()` splits a 6-letter Deriv forex
symbol into base/quote currency codes and treats any shared currency as
"correlated" when both positions are in the same direction. This is a
blunt proxy for real price correlation (e.g. EUR/USD and GBP/USD do tend
to move together when both are "long USD", but it's not a measured
correlation coefficient). Good enough to catch the exact example in
docs/SPEC.md ("don't go long 3 USD pairs at once"); a real correlation
matrix from historical returns would be a reasonable future improvement,
not required for Phase 4.

## 2026-11-18 — Phase 3 doesn't use deal cancellation
`get_proposal()` always sets `limit_order: {take_profit, stop_loss}` on
the proposal request itself (dollar P&L amounts — Deriv's own Multipliers
semantics for `limit_order`, matching `RiskBreakdown.max_gain`/`max_loss`
exactly). Deal cancellation is never requested, so the edge case in
docs/SPEC.md ("deal cancellation and take-profit can't both be set at
open... add take-profit via `contract_update` only after the cancellation
window expires") doesn't apply to v1. `contract_update` still exists on
`DerivClient` for later use (e.g. tightening a stop after entry), just not
exercised by the Phase 3 script itself.

## 2026-11-18 — Phase 3's Deriv call shapes are verified against docs, not a live session
This sandbox can't install `python_deriv_api` or hold a real demo session,
so `tools/deriv_client.py`'s `get_proposal`/`buy_contract`/`sell_contract`/
`contract_update`/`subscribe_open_contract` request shapes were checked
against the library's own usage examples
(github.com/deriv-com/python-deriv-api/blob/master/docs/usage_examples.md)
rather than executed. Response field names (`proposal.id`, `proposal.ask_price`,
`buy.contract_id`, `buy.buy_price`, `proposal_open_contract.status/profit/
is_sold/sell_price`) are standard Deriv API fields from documentation, but
unverified end-to-end here. `scripts/run_phase3_demo_trading.py` wraps the
propose/buy calls in a broad `except Exception` specifically because it's
unknown whether this library raises on an API error response or returns an
`{"error": ...}` dict — run it against your own demo account and tighten
that except clause once you've seen the actual failure mode.

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
