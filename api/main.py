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
from fastapi.responses import HTMLResponse, PlainTextResponse

from api.dashboard import DASHBOARD_HTML
from storage.db import (
    get_connection,
    get_latest_correlation_matrix_with_timestamp,
    get_realized_pnl_today,
    list_backtests,
    list_proposals,
    list_trades,
)
from tools.csv_export import trades_to_csv

app = FastAPI(title="Deriv Trading Agent", version="0.2.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Equity curve, win rate, open positions, recent trades — reads the
    JSON endpoints below client-side. Cannot place, approve, or reject a
    trade; see this module's docstring."""
    return DASHBOARD_HTML


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


@app.get("/trades.csv", response_class=PlainTextResponse)
async def read_trades_csv(
    env: Literal["demo", "live"] = "demo",
    status: Literal["open", "sold", "won", "lost"] | None = None,
    limit: int = Query(1000, ge=1, le=5000),
) -> PlainTextResponse:
    conn = get_connection()
    try:
        trades = list_trades(conn, env=env, status=status, limit=limit)
    finally:
        conn.close()
    return PlainTextResponse(
        trades_to_csv(trades),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{env}_trades.csv"'},
    )


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


@app.get("/correlation")
async def read_correlation() -> dict:
    """The most recently logged run of scripts/run_phase17_correlation_matrix.py
    — {computed_at: null, pairs: []} if nothing has been logged yet."""
    conn = get_connection()
    try:
        matrix, computed_at = get_latest_correlation_matrix_with_timestamp(conn)
    finally:
        conn.close()
    return {
        "computed_at": computed_at,
        "pairs": [
            {"symbol_a": a, "symbol_b": b, "correlation": c}
            for (a, b), c in matrix.items()
        ],
    }
