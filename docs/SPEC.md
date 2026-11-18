# Build Spec v2 — Deriv Trading Agent (Multipliers, Linux-native)

> Source of truth for scope. Any implementation decision that deviates from
> this must be recorded in [DECISIONS.md](./DECISIONS.md) with a reason.

## Goal
Build an automated market-analysis + trading agent on Deriv's native API.
It analyzes forex, gold, commodities, stocks and synthetic indices, proposes
trades using Multipliers contracts with explicit two-sided risk/reward, and
only fires a REAL contract after explicit human approval. No guaranteed-profit
logic anywhere — stake size is risk-based (% of balance), never target-based.

## Broker / contract type — read this before writing any trading code
- Deriv only. Contract type: MULTUP / MULTDOWN (Multipliers) exclusively.
- Do NOT implement CALL/PUT, DIGITMATCH, or any other binary/digital-option
  contract type — different risk profile entirely (fixed short-expiry
  all-or-nothing payout), not what this agent is for. If a Deriv doc example
  uses one of those, ignore it.
- Trade lifecycle per Deriv's own docs: request a price with `proposal`,
  execute with `buy` using the proposal id, monitor the open position with
  `proposal_open_contract`, close early with `sell` or let it run to the
  take-profit/stop-loss/auto-stop-out.
- Set stop_loss + take_profit via `limit_order` on the buy, or afterward via
  `contract_update` (server-side exit, not client-side stream-watching).
- Stake = max possible loss on that contract by design (never exceeds stake
  even without a stop loss, due to automatic stop-out). This IS the
  risk-per-trade amount — no separate position-size formula needed.
- Edge case: deal cancellation and take-profit can't both be set at open on
  the same contract — if you use deal cancellation, add take-profit via
  `contract_update` only after the cancellation window expires.

## Non-negotiables
- NEVER call `buy` without an explicit per-trade confirmation (CLI y/n for
  v1; Telegram approve/reject can come later).
- Every proposed trade must print BOTH sides before asking for approval:
  symbol, direction, stake, multiplier, take_profit, stop_loss, max $ loss
  (= stake), max $ gain (at take_profit), R:R ratio.
- Stake = current Deriv balance (via `balance` call) × max-risk-per-trade %,
  default 1%, configurable. Never a flat dollar stake.
- Starts against a DEMO account (virtual-money login) only. Switching to a
  real-money account requires an explicit ENV=live flag AND a second
  confirmation prompt — not just a config edit.
- Daily kill-switch: if realized loss for the day exceeds X% of balance
  (default 3%), stop proposing new trades until the next day, log why.
- Blackout/caution dates (configurable list — Dec 24-26, Dec 31-Jan 2, major
  bank holidays): auto-halve stake instead of trading normal size.

## Stack
- Python 3.11+, fully native Linux, no Wine/Windows/VM.
- `python_deriv_api` (official, `pip install python_deriv_api`,
  `from deriv_api import DerivAPI`) for the WebSocket connection,
  authorize/balance/ticks_history/proposal/buy/sell/contract_update calls.
- FastAPI service wrapping the agent's internals, so other services can call
  in later over REST/MCP instead of trading logic getting reimplemented
  elsewhere.
- SQLite for trade/signal logs.
- asyncio event loop (the Deriv client is async-native) instead of a
  polling while-loop where possible — subscribe to ticks, don't re-poll.

## Setup prerequisites (do this before writing code)
- Register an app at api.deriv.com to get an `app_id`.
- Create a Deriv demo account, generate an API token scoped to read +
  trade (not withdrawals/transfers) for the demo account only.
- Store app_id + token in `.env`, never hardcoded.

## Phase 1 — Data + analysis only (no contracts bought)
- Connect, authorize, pull `ticks_history` for a small symbol list to start
  (frxEURUSD, frxXAUUSD for gold, one volatility index e.g. 1HZ100V for
  weekend/off-hours testing since synthetics trade 24/7).
- Implement 2-3 signals max (e.g. EMA crossover + RSI filter + ATR
  volatility filter). Don't add ten indicators before one works.
- For each candidate signal, compute and log: direction, proposed stake
  (from current demo balance x risk %), proposed take_profit/stop_loss,
  max $ loss, max $ gain, R:R. No `buy` call exists yet in this phase.

## Phase 2 — Backtest validation
- Backtest signal logic against historical `ticks_history` data per symbol
  before touching a live tick.
- Report win rate, avg R:R, max drawdown.
- Sanity check: a backtested win rate above ~70% on a simple signal is
  almost always a lookahead/data bug — stop and audit, don't proceed.

## Phase 3 — Demo paper trading with approval gate
- Agent proposes trades on live demo ticks via `proposal`, prints the full
  two-sided risk/reward breakdown, waits for human y/n, then calls `buy`
  only on approval.
- Log every proposal, approved AND rejected, for later review.
- Track open contracts via `proposal_open_contract`; don't poll balance in
  a tight loop, subscribe instead.

## Phase 4 — Hardening (only after Phase 3 runs clean for 2-4 weeks)
- Move alerting from CLI to Telegram/WhatsApp.
- Add max concurrent open contracts, correlation checks (don't go long 3
  USD pairs at once and call it diversification).
- Only after this: switch to a real-money Deriv account, smallest viable
  stake, with the ENV=live double-confirmation from the non-negotiables.

## Explicitly out of scope for v1
- No binary/digital options contract types, ever.
- No fixed daily profit targets of any kind.
- No martingale / grid / averaging-down stake sizing.
- No real-money contracts before Phase 3 has run clean on demo for at
  least 2-4 weeks.

## Deliver
Scaffold the repo (agents/tools/config/types), implement Phase 1
end-to-end, and stop there for review before touching Phase 2.
