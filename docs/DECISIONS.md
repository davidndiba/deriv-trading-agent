# Decisions log

Record any choice that isn't obvious from SPEC.md, with the reason.

## 2026-11-18 — Contract type is hard-restricted in code, not just by convention
`tools/deriv_client.py` only exposes the calls needed for Multipliers
(`proposal` with `contract_type=MULTUP/MULTDOWN`, `buy`, `sell`,
`proposal_open_contract`, `contract_update`). There is no generic
"send raw request" passthrough exposed to the agent layer, so a future
signal implementation cannot accidentally construct a CALL/PUT/DIGITMATCH
request even by copy-pasting a Deriv doc example.

## 2026-11-18 — Auto-approve is demo-only in three independent ways, deliberately redundant
`AUTO_APPROVE_DEMO_TRADES` removes the one thing every phase in this
project has been built around: a human explicitly approving every
`buy`. That makes "never effective when ENV=live" the single
highest-stakes property in this feature, so it isn't enforced once —
it's enforced three times, each independently sufficient on its own:
1. `scripts/run_phase4_demo_trading.py::run()` already refuses to run
   at all with `ENV=live` (pre-existing, from Phase 4's original build).
2. `Settings.auto_approve_effective` ANDs the raw flag with "not live"
   at the settings layer itself, so any new code that reads this
   property instead of the raw field gets the guarantee for free.
3. `auto_approve_prompt()` checks `auto_approve_effective` again at the
   moment it would approve a trade, and raises rather than approving if
   it's ever false — a plain `if`, not `assert`, since `assert` is
   compiled out entirely under `python -O` and a safety check that can
   be silently disabled by an interpreter flag isn't one.
No single one of these three is trusted alone; a bug in any one still
leaves two more in the way of an auto-approved live trade.

Only `scripts/run_phase4_demo_trading.py` was given this capability.
`scripts/run_phase5_live_trading.py` doesn't read `AUTO_APPROVE_DEMO_TRADES`
or `auto_approve_effective` at all — its own `default_approval_prompt()`
is hardcoded with no injection point for anything else, so there's no
code path through which auto-approval could ever reach a real account
even if every one of the three checks above were somehow bypassed.

## 2026-11-18 — Real correlation matrix is now wired in, additively and opt-in
`tools/correlation_matrix.py` and `scripts/run_phase17_correlation_matrix.py`
compute and log an actual Pearson correlation between symbols — the
"reasonable future improvement" flagged in the Phase 4 correlation-guard
decision above. It started standalone (Phase 17) and was later wired
into `scripts/run_phase{4,5}_*.py`, resolving the three open questions
from that decision:
- **Staleness**: a logged matrix older than `CORRELATION_MATRIX_MAX_AGE_HOURS`
  (default 24) is treated exactly like a missing one — `is_matrix_stale()`
  — rather than trusted indefinitely.
- **Recompute vs. read logged**: read the logged one
  (`get_latest_correlation_matrix_with_timestamp()`), not recomputed
  every trading run. Correlation is slow-moving; recomputing it inside
  the already-verified per-symbol trading loop would mean restructuring
  that loop to fetch every symbol's candles up front instead of one at a
  time, for a property that doesn't need fresh-every-run data. You keep
  it current by running `run_phase17_correlation_matrix.py` periodically
  (cron, or by hand) — the trading scripts just read what's there.
- **Candle window and threshold**: standardized on Phase 17's own
  defaults, exposed as `CORRELATION_MATRIX_THRESHOLD` (default 0.7).

It's **opt-in** (`USE_REAL_CORRELATION_MATRIX=false` by default) and
**additive**, not a replacement for the currency-overlap heuristic — a
trade is blocked if *either* guard flags it. This differs from the news
blackout's "on by default" choice: news blackout only ever needs the
free calendar feed to be reachable, with a safe fail-closed fallback
(block trading) if it isn't. The correlation matrix has an operational
dependency the user has to actively maintain (periodically running Phase
17), so defaulting it on would mean the guard silently does nothing for
anyone who hasn't established that habit — opt-in makes that dependency
visible instead of invisible.

## 2026-11-18 — News blackout guard defaults to ON, unlike every opt-in config before it
Every other configurable guard in this repo (concurrency cap,
correlation limit, Telegram) either has a sane default that doesn't
change what existing scripts do, or is explicitly optional. The news
blackout is different: it's `NEWS_BLACKOUT_ENABLED=true` by default,
meaning it changes `scripts/run_phase{4,5}_*.py`'s behavior the moment
this is deployed to an existing `.env` — fewer trades get proposed near
high-impact releases than before. This is deliberate: unlike the
backtest's `spread_pct` (which had to default to zero to keep historical
backtest numbers meaningful), a guard that only ever *skips* a trade
never adds risk, so defaulting it on is the same judgment call as
blackout *dates* being always-on rather than opt-in.

## 2026-11-18 — News calendar guard fails closed, not open
If `NEWS_BLACKOUT_ENABLED=true` and the Forex Factory feed can't be
fetched or parsed, `scripts/run_phase{4,5}_*.py` stop proposing any new
trades for that run entirely, rather than falling back to "assume no
news." A broken data source and "no high-impact events this week" must
never look the same to code that's about to risk money on that
assumption — the exact same reasoning as the daily kill-switch failing
toward caution, not toward permissiveness.

## 2026-11-18 — News calendar data source is a free export, not an official API
`tools/news_calendar.py` fetches
`https://nfs.faireconomy.media/ff_calendar_thisweek.json` — Forex
Factory's own publicly documented weekly JSON export, used by many
retail trading tools for exactly this purpose, confirmed by fetching it
directly and checking field names (`title`, `country`, `date`, `impact`,
`forecast`, `previous`) rather than assuming them. It needs no API key
and no connector/credential from the user. It is not a contractually
documented API, though — it could change shape or disappear without
notice, which is exactly why a fetch/parse failure fails closed (see
above) instead of being treated as "no news."

## 2026-11-18 — uvicorn[standard] conflicts with python_deriv_api, dropped the extra
The first real CI run (Phase 6 onward) failed every time, in ~14
seconds — too fast to have gotten past `pip install`. Checked
`python_deriv_api`'s published PyPI metadata directly: it pins
`websockets==10.3` exactly. `uvicorn[standard]`'s `[standard]` extra
requires `websockets>=13.0`. Those two constraints can never both be
satisfied, so pip's resolver fails immediately — this is a real bug this
sandbox's lack of `pip` couldn't have caught, exactly the gap Phase 6
exists to close. Fix: `requirements.txt` now pins plain `uvicorn`
(no `[standard]`), which only needs `click`/`h11` unconditionally —
confirmed from uvicorn's own PyPI metadata. `api/main.py` has no
websocket endpoints of its own, so the extra was never actually needed.

## 2026-11-18 — Spread model is a verified mechanism, not a verified number
`tools/backtest.py::backtest_symbol`'s `spread_pct` shifts a long's
effective fill price up (and a short's down) by that fraction, then
places both the stop-loss and take-profit barriers relative to that
worse fill — so a long's take-profit sits farther away and its
stop-loss sits closer, matching what real spread cost actually does.
That *mechanism* is verified by direct execution (see
tests/test_backtest_spread.py, including a case where it flips a
near-miss win into a loss). The *magnitude* used in
`scripts/run_phase12_spread_aware_backtest.py`
(`ASSUMED_SPREAD_PCT = 0.0002`) is a placeholder, explicitly not sourced
from Deriv's own published spread data for any symbol — this sandbox has
no way to check a real account's actual spreads. Treat the comparison's
shape (does a given signal's edge survive realistic friction) as
meaningful; treat the specific percentage as something to replace with
what you actually observe.

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
