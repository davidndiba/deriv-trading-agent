"""Phase 3 entry point: demo paper trading with an explicit approval gate.

For each symbol with a signal: print the full two-sided risk/reward
breakdown, ask for an explicit y/n, log the decision either way, and only
call `buy` on approval. Every bought contract is then monitored via a
`proposal_open_contract` subscription (not polled) until it closes.

Refuses to run with ENV=live — real money is a later decision, gated
behind a clean multi-week demo run and its own separate confirmation
flow, not something this script can reach.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Callable

from agents.risk import build_risk_breakdown
from agents.signals import generate_signal
from config.settings import Settings, load_settings
from schemas.models import TradeProposal
from storage.db import (
    get_connection,
    get_realized_pnl_today,
    log_proposal,
    log_trade_closed,
    log_trade_opened,
)
from tools.deriv_client import DerivClient, parse_candles

CANDLE_COUNT = 200
GRANULARITY_SECONDS = 60


def default_approval_prompt(proposal: TradeProposal) -> bool:
    print()
    print(proposal.render())
    answer = input("\nApprove this trade? [y/N]: ").strip().lower()
    return answer == "y"


async def _monitor_contract(client: DerivClient, conn, contract_id: int) -> None:
    """Subscribes to proposal_open_contract and logs the close when the
    contract is sold/won/lost. Runs until that happens."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()

    def on_update(response: dict) -> None:
        poc = response.get("proposal_open_contract", {})
        status = poc.get("status")
        print(f"  [{contract_id}] status={status} profit={poc.get('profit')}")
        if poc.get("is_sold") or status in ("sold", "won", "lost"):
            log_trade_closed(
                conn,
                contract_id=contract_id,
                sell_price=poc.get("sell_price") or 0.0,
                profit=poc.get("profit") or 0.0,
                status=status or "sold",
            )
            if not done.done():
                done.set_result(None)

    source = await client.subscribe_open_contract(contract_id=contract_id)
    subscription = source.subscribe(on_update)
    try:
        await done
    finally:
        subscription.dispose()


async def run(
    settings: Settings,
    approval_prompt: Callable[[TradeProposal], bool] = default_approval_prompt,
) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 3 is demo paper trading only — refusing to run with "
            "ENV=live."
        )

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    monitors: list[asyncio.Task] = []
    try:
        balance = await client.get_balance()
        print(f"Demo balance: ${balance:.2f}\n")

        realized_today = get_realized_pnl_today(conn)
        loss_limit = settings.daily_loss_limit_pct * balance
        if realized_today < -loss_limit:
            print(
                f"Daily kill-switch: realized loss today (${realized_today:.2f}) "
                f"already exceeds {settings.daily_loss_limit_pct:.1%} of balance "
                f"(${loss_limit:.2f}). Not proposing any new trades until "
                "tomorrow."
            )
            return

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
            approved = approval_prompt(proposal)
            proposal.approved = approved
            log_proposal(conn, proposal)

            if not approved:
                print(f"[{symbol}] rejected — not buying.\n")
                continue

            try:
                quote = await client.get_proposal(
                    symbol=symbol,
                    direction=signal.direction,
                    stake=risk.stake,
                    multiplier=risk.multiplier,
                    take_profit=risk.max_gain,
                    stop_loss=risk.max_loss,
                )
                if "error" in quote:
                    print(f"[{symbol}] proposal error: {quote['error']}\n")
                    continue

                proposal_data = quote["proposal"]
                buy_resp = await client.buy_contract(
                    proposal_id=proposal_data["id"], price=proposal_data["ask_price"]
                )
                if "error" in buy_resp:
                    print(f"[{symbol}] buy error: {buy_resp['error']}\n")
                    continue

                buy_data = buy_resp["buy"]
            except Exception as exc:  # noqa: BLE001 — a bad response for
                # one symbol must not crash a run that already approved
                # and logged other trades; the exact exception type this
                # library raises on API errors is unverified in this
                # sandbox, so this is deliberately broad here.
                print(f"[{symbol}] proposal/buy failed: {exc!r}\n")
                continue

            contract_id = buy_data["contract_id"]
            log_trade_opened(
                conn,
                contract_id=contract_id,
                symbol=symbol,
                direction=signal.direction.value,
                stake=risk.stake,
                multiplier=risk.multiplier,
                take_profit=risk.max_gain,
                stop_loss=risk.max_loss,
                buy_price=buy_data["buy_price"],
            )
            print(f"[{symbol}] bought contract {contract_id} at {buy_data['buy_price']}\n")
            monitors.append(asyncio.create_task(_monitor_contract(client, conn, contract_id)))

        if monitors:
            print(
                f"Monitoring {len(monitors)} open contract(s) until they close "
                "(Ctrl+C stops watching here — contracts stay open on "
                "Deriv's side either way)..."
            )
            await asyncio.gather(*monitors)
    finally:
        for task in monitors:
            if not task.done():
                task.cancel()
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
