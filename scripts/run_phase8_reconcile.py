"""Phase 8: reconcile the local trade log against Deriv's own portfolio.

Unlike every other trading script in this repo, this one does NOT refuse
ENV=live — it's read-only with respect to placing orders (no `buy`/
`sell`/`proposal` call exists here) and is exactly the kind of check
you'd want to run periodically against a real account, e.g. after a
crash or restart. It runs against whichever account `.env` is currently
authorized for, demo or live.

What it does:
  - "ghost" contracts: the local log still calls these open, but Deriv's
    portfolio no longer shows them. Almost always a missed close event
    (the proposal_open_contract subscription never delivered, e.g.
    because the process died). These are healed: a one-off snapshot is
    fetched from Deriv and the local record is updated to match.
  - "orphan" contracts: Deriv's portfolio shows these open, but the
    local log has no record of them at all (bought elsewhere, or from
    before this tool existed). These are only ever reported — nothing
    is written to the local log for a position this tool didn't create.
"""
from __future__ import annotations

import asyncio
import sys

from config.settings import Settings, load_settings
from storage.db import get_connection, get_open_contract_ids, log_trade_closed
from tools.deriv_client import DerivClient
from tools.reconciliation import diff_portfolio


async def run(settings: Settings) -> None:
    env = "live" if settings.is_live else "demo"

    client = DerivClient(settings)
    await client.connect()
    conn = get_connection()
    try:
        local_ids = get_open_contract_ids(conn, env=env)

        portfolio = await client.get_portfolio()
        deriv_contracts = portfolio.get("portfolio", {}).get("contracts", [])
        deriv_by_id = {c["contract_id"]: c for c in deriv_contracts}
        deriv_ids = set(deriv_by_id.keys())

        print(f"[{env}] local open: {len(local_ids)}  Deriv open: {len(deriv_ids)}")

        ghosts, orphans = diff_portfolio(local_ids, deriv_ids)

        for contract_id in sorted(ghosts):
            try:
                snapshot = await client.get_open_contract_snapshot(contract_id=contract_id)
                poc = snapshot.get("proposal_open_contract", {})
            except Exception as exc:  # noqa: BLE001 — see docs/DECISIONS.md
                print(f"  ghost {contract_id}: could not fetch snapshot: {exc!r}")
                continue
            status = poc.get("status") or "sold"
            profit = poc.get("profit") or 0.0
            sell_price = poc.get("sell_price") or 0.0
            log_trade_closed(conn, contract_id=contract_id, sell_price=sell_price, profit=profit, status=status)
            print(
                f"  healed ghost {contract_id}: was actually '{status}' "
                f"(profit=${profit:.2f}) — local record updated"
            )

        for contract_id in sorted(orphans):
            c = deriv_by_id[contract_id]
            print(
                f"  ORPHAN {contract_id}: {c.get('symbol')} buy_price="
                f"{c.get('buy_price')} — open on Deriv, no local record at "
                "all. Nothing written locally; review this one yourself."
            )

        if not ghosts and not orphans:
            print("No drift — local record matches Deriv's portfolio exactly.")
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
