# Progress log

Newest entry first. One entry per phase commit/push.

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
