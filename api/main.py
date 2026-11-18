"""FastAPI service wrapping the agent's internals.

Imports from agents/tools/storage, never the other way round — see
docs/DECISIONS.md. Read-only by design: every endpoint here reports on
state the CLI scripts already produced. There is deliberately no
endpoint that proposes, approves, or buys anything — that stays behind
the per-trade CLI y/n gate in scripts/run_phase{3,4,5}_*.py. An API that
could trigger a trade without a human typing y/n would undermine the
one non-negotiable every phase so far has preserved.
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Query

from storage.db import get_connection, get_realized_pnl_today, list_backtests, list_proposals, list_trades

app = FastAPI(title="Deriv Trading Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/proposals")
async def read_proposals(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    """Every candidate signal logged by any phase, approved or rejected."""
    conn = get_connection()
    try:
        return list_proposals(conn, limit=limit)
    finally:
        conn.close()


@app.get("/trades")
async def read_trades(
    env: Literal["demo", "live"] = "demo",
    status: Literal["open", "sold", "won", "lost"] | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    conn = get_connection()
    try:
        return list_trades(conn, env=env, status=status, limit=limit)
    finally:
        conn.close()


@app.get("/trades/pnl/today")
async def read_pnl_today(env: Literal["demo", "live"] = "demo") -> dict:
    conn = get_connection()
    try:
        return {"env": env, "realized_pnl_today": get_realized_pnl_today(conn, env=env)}
    finally:
        conn.close()


@app.get("/backtests")
async def read_backtests(
    symbol: str | None = None, limit: int = Query(50, ge=1, le=500)
) -> list[dict]:
    conn = get_connection()
    try:
        return list_backtests(conn, symbol=symbol, limit=limit)
    finally:
        conn.close()
