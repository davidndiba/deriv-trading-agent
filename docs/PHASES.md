# Phase roadmap

Each phase is a separate commit/push. A phase does not start until the
previous one is reviewed and explicitly approved. This mirrors the
qa-agent-microvision workflow: scaffold -> build -> log -> review -> next.

| Phase | Name | Buys real/demo contracts? | Exit criteria |
|---|---|---|---|
| 0 | Repo scaffold | No | Structure, config, Deriv client stub, docs, CI-less skeleton committed and pushed. |
| 1 | Data + analysis only | No | Connects to demo account, pulls `ticks_history`, runs 2-3 signals, logs full proposed risk/reward (direction, stake, TP/SL, max loss, max gain, R:R) for every candidate signal. No `buy` call exists in this phase's code at all. |
| 2 | Backtest validation | No | Signals backtested against historical `ticks_history`. Report win rate, avg R:R, max drawdown per symbol. A win rate above ~70% on a simple signal triggers a stop-and-audit, not a proceed. |
| 3 | Demo paper trading with approval gate | Demo only | Agent proposes via `proposal`, prints two-sided risk/reward, waits for explicit y/n, calls `buy` only on approval. Every proposal (approved + rejected) logged. Open contracts tracked via `proposal_open_contract` subscription, not polling. |
| 4 | Hardening | Demo only | Telegram/WhatsApp alerting, max concurrent open contracts, correlation checks across symbols. Requires Phase 3 running clean for 2-4 weeks before this phase is considered done. |
| 5 | Real-money cutover | Real (smallest stake) | Only after Phase 4 is done and the 2-4 week clean-demo bar is met. Requires `ENV=live` flag AND a second interactive confirmation prompt. Smallest viable stake first. Code exists (`scripts/run_phase5_live_trading.py`) and enforces its own soak-period/trade-count check with no override flag — but the code existing is not the same as the 2-4 week clean-demo bar actually having been met; see docs/PROGRESS.md. |

## Non-negotiables that apply to every phase
- Deriv Multipliers (MULTUP/MULTDOWN) only. Never CALL/PUT/DIGITMATCH.
- Stake is always `balance x risk_per_trade_pct`, never a flat dollar amount.
- No martingale / grid / averaging-down sizing, ever.
- No fixed daily profit targets.
- Daily kill-switch: realized loss > `daily_loss_limit_pct` of balance halts
  new proposals until the next day.
- Blackout/caution dates auto-halve stake instead of skipping the day.

## Current status
See [PROGRESS.md](./PROGRESS.md) for the running log.
