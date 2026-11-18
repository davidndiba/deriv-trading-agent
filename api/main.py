"""FastAPI service wrapping the agent's internals.

Imports from agents/tools, never the other way round — see
docs/DECISIONS.md. Only a health check exists in Phase 0; Phase 1 adds a
read-only endpoint to list recent proposals once signal logging exists.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Deriv Trading Agent", version="0.0.0-phase0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
