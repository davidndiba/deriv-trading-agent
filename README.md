# Deriv Trading Agent

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

## Setup
1. Register an app at https://api.deriv.com to get an `app_id`.
2. Create a Deriv **demo** account and generate an API token scoped to
   read + trade only (never withdrawals/transfers).
3. `cp .env.example .env` and fill in `APP_ID` / `API_TOKEN`.
4. `python3 -m venv .venv && source .venv/bin/activate`
5. `pip install -r requirements.txt`

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
