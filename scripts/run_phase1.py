"""Phase 1 entry point: connect to a DEMO account, pull candles, run the
signal, log the full risk/reward breakdown for every candidate signal.

No `buy`/`sell`/`proposal` call exists anywhere in this script or the
modules it imports — that's Phase 3. This only looks and logs.
"""
from __future__ import annotations

import asyncio
import sys

from agents.risk import build_risk_breakdown
from agents.signals import generate_signal
from config.settings import Settings, load_settings
from schemas.models import TradeProposal
from storage.db import get_connection, log_proposal
from tools.deriv_client import DerivClient, parse_candles

CANDLE_COUNT = 200
GRANULARITY_SECONDS = 60  # 1-minute candles


async def run(settings: Settings) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 1 is data+analysis only — refusing to run with ENV=live. "
            "No buy call exists in this phase regardless, but this guard "
            "stops it from even touching a real-money session."
        )

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    try:
        balance = await client.get_balance()
        print(f"Demo balance: ${balance:.2f}\n")

        for symbol in settings.symbols:
            response = await client.get_ticks_history(
                symbol, count=CANDLE_COUNT, granularity=GRANULARITY_SECONDS
            )
            candles = parse_candles(response)
            signal = generate_signal(symbol, candles)
            if signal is None:
                print(f"[{symbol}] no signal")
                continue

            risk = build_risk_breakdown(signal, balance, settings)
            proposal = TradeProposal(signal=signal, risk=risk)
            print(proposal.render())
            print()
            log_proposal(conn, proposal)
    finally:
        await client.disconnect()
        conn.close()


def main() -> None:
    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
