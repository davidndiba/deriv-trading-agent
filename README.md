# Deriv Trading Agent

[![CI](https://github.com/davidndiba/deriv-trading-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/davidndiba/deriv-trading-agent/actions/workflows/ci.yml)

Automated market-analysis agent for Deriv (forex, gold, commodities, stocks,
synthetic indices). Proposes **Multipliers (MULTUP/MULTDOWN)** trades with an
explicit two-sided risk/reward breakdown and only ever fires a real contract
after explicit human approval.

Full scope: [docs/SPEC.md](docs/SPEC.md).
Phase roadmap + exit criteria: [docs/PHASES.md](docs/PHASES.md).
Progress log: [docs/PROGRESS.md](docs/PROGRESS.md).

## Non-negotiables
- Deriv Multipliers only. No CALL/PUT/DIGITMATCH, ever.
- Stake = `balance x risk_per_trade_pct`, never a flat dollar amount, never
  martingale/grid/averaging-down.
- No `buy` call happens without an explicit per-trade human approval.
- Starts and stays on a DEMO account until Phase 3 has run clean for
  2-4 weeks (see docs/PHASES.md). Real money requires `ENV=live` **and** a
  second interactive confirmation.
- Daily kill-switch + blackout-date stake halving are always active.

## Reporting API
`uvicorn api.main:app --reload` serves read-only reporting over the same
SQLite log the CLI scripts write to: `/proposals`, `/trades`,
`/trades/pnl/today`, `/backtests`, `/health`. No endpoint can propose,
approve, or buy anything — that stays behind each script's CLI y/n gate.

## Setup
1. Register an app at https://api.deriv.com to get an `app_id`.
2. Create a Deriv **demo** account and generate an API token scoped to
   read + trade only (never withdrawals/transfers).
3. `cp .env.example .env` and fill in `APP_ID` / `API_TOKEN`.
4. `python3 -m venv .venv && source .venv/bin/activate`
5. `pip install -r requirements.txt`
6. `python -m pytest tests/ -q` to confirm the signal/risk logic locally.
7. `python scripts/run_phase1.py` to pull candles against your demo
   account and log candidate signals (no contracts bought — see
   docs/PHASES.md).
8. `python scripts/run_phase2_backtest.py` to backtest that signal against
   5000 historical candles per symbol and print win rate / avg R / max
   drawdown (still no contracts bought).
9. `python scripts/run_phase3_demo_trading.py` to paper-trade on your demo
   account: every proposal needs an explicit y/n before anything is
   bought. Start with tiny demo stakes and watch it closely the first few
   times — see docs/DECISIONS.md for what's unverified in this phase.
10. `python scripts/run_phase4_demo_trading.py` adds a concurrency cap, a
    currency-correlation guard, and optional Telegram alerts (fill in
    `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` to enable — leave blank to
    skip). Telegram only ever notifies; the CLI y/n gate still decides.
    Still demo-only, and this code existing doesn't replace the 2-4 week
    clean demo run docs/PHASES.md asks for before Phase 5.
11. `scripts/run_phase5_live_trading.py` is the **only** script here that
    will touch a real account. It refuses to run unless `ENV=live`, then
    refuses further unless your local demo trade log already shows
    `LIVE_MIN_DEMO_TRADES`+ closed trades spanning
    `LIVE_MIN_DEMO_SOAK_DAYS`+ days — there's no flag to skip that check.
    Past that it asks you to type an exact confirmation phrase, then
    still asks a per-trade y/n like every other phase, with stake capped
    at `LIVE_MAX_STAKE_USD` on top of the normal risk-% sizing. Don't run
    this until you've actually put in the demo time — the code enforcing
    that check is not a substitute for it.
12. `python scripts/run_phase7_walk_forward_backtest.py` splits the same
    historical window into 4 chronological folds and reports each one
    separately, so a signal that only "worked" in one stretch of history
    is visible as exactly that.
13. `python scripts/run_phase8_reconcile.py` cross-checks the local
    trade log against Deriv's own portfolio for whichever account
    `.env` currently authorizes — the one script here that's safe to
    run against a live account anytime, since it places no orders.
14. `python scripts/run_phase9_mtf_backtest.py` backtests the Phase 1
    signal with and without a higher-timeframe trend filter, side by
    side. A comparison only — it doesn't change what Phases 3-5 trade;
    that's your call to make after reading the numbers.
15. `python scripts/run_phase10_mean_reversion_backtest.py` backtests a
    second, independent signal (`agents/mean_reversion.py` — Bollinger
    Band fade + RSI) through the same engine as Phase 2/7.
16. `python scripts/run_phase12_spread_aware_backtest.py` runs the same
    signal frictionless and spread-adjusted side by side. The placeholder
    spread assumption in the script isn't sourced from real Deriv data —
    replace it with what you actually observe before trusting the
    magnitude of the difference.

## Layout
```
agents/     strategy/signal logic (EMA/RSI/ATR etc.)
tools/      Deriv API client wrapper, indicators
config/     env-driven settings loader
schemas/    pydantic domain models (Signal, RiskBreakdown, TradeProposal)
api/        FastAPI service exposing the agent over REST
storage/    SQLite logging for signals/proposals
scripts/    CLI entry points, one per phase
docs/       spec, phase roadmap, progress log, decisions log
```

## Status
See [docs/PROGRESS.md](docs/PROGRESS.md) for the current phase.
