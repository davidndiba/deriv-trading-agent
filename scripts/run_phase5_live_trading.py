"""Phase 5: real-money cutover. The ONLY script in this repo that will
run against a live account — every other script refuses ENV=live
outright.

Guards, in the order they run, any one of which stops the script before
it can place a single real order:
  1. ENV=live required (a config edit alone does nothing without this).
  2. Demo track record check: at least `LIVE_MIN_DEMO_TRADES` closed demo
     trades, spanning at least `LIVE_MIN_DEMO_SOAK_DAYS` days, must exist
     in the *local* trade log before this will even print the warning
     banner. There is no override flag — bypassing this means editing
     this file, which is a deliberate, visible act, not a quick flag.
  3. A second, explicit interactive confirmation (an exact phrase, not a
     y/n) separate from the ENV=live flag itself.
  4. Every individual trade still needs its own y/n, exactly like every
     other phase — this script does not relax that non-negotiable.
  5. Stake is capped at `LIVE_MAX_STAKE_USD` regardless of what the
     risk-% sizing would otherwise produce ("smallest viable stake
     first" — docs/SPEC.md Phase 4->5).

Everything else (daily kill-switch, concurrency cap, correlation guard,
news blackout, Telegram alerts) is identical to Phase 4, scoped to
env='live' trades only so a live run is never influenced by — or
influences — demo history. The opt-in real-correlation-matrix check
(USE_REAL_CORRELATION_MATRIX) is also identical to Phase 4's — the
correlation_matrix table has no env column, since price correlation is
market data, not account data.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Callable

from agents.risk import apply_live_stake_cap, build_risk_breakdown
from agents.signals import generate_signal
from config.settings import Settings, load_settings
from schemas.models import TradeProposal
from storage.db import (
    get_connection,
    get_demo_track_record,
    get_latest_correlation_matrix_with_timestamp,
    get_open_trade_count,
    get_open_trades,
    get_realized_pnl_today,
    log_proposal,
    log_trade_closed,
    log_trade_opened,
)
from tools.correlation_matrix import correlated_by_matrix, is_matrix_stale
from tools.deriv_client import DerivClient, parse_candles
from tools.exposure import correlated_open_symbols, currency_exposure
from tools.news_calendar import fetch_this_weeks_events, is_within_news_blackout
from tools.telegram_notifier import TelegramNotifier

CANDLE_COUNT = 200
GRANULARITY_SECONDS = 60
CONFIRMATION_PHRASE = "TRADE REAL MONEY"


def check_demo_track_record(settings: Settings, conn) -> tuple[bool, str]:
    closed_count, earliest_opened_at = get_demo_track_record(conn)
    if closed_count < settings.live_min_demo_trades:
        return False, (
            f"Only {closed_count} closed demo trades on record "
            f"(need {settings.live_min_demo_trades}). Run Phases 3-4 on "
            "demo longer before this."
        )
    if earliest_opened_at is None:
        return False, "No demo trade history found at all."

    from datetime import datetime, timezone

    earliest = datetime.fromisoformat(earliest_opened_at)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    soak_days = (datetime.now(timezone.utc) - earliest).days
    if soak_days < settings.live_min_demo_soak_days:
        return False, (
            f"Demo trading history only spans {soak_days} day(s) "
            f"(need {settings.live_min_demo_soak_days}). Keep running "
            "Phases 3-4 on demo."
        )
    return True, (
        f"{closed_count} closed demo trades over {soak_days} days — "
        "track record check passed."
    )


def confirm_live_trading() -> bool:
    print(
        "\n"
        "########################################################\n"
        "#  WARNING: THIS WILL TRADE REAL MONEY ON A LIVE DERIV #\n"
        "#  ACCOUNT. Every trade is still capped and gated, but  #\n"
        "#  losses here are real losses.                         #\n"
        "########################################################\n"
    )
    answer = input(f'Type exactly "{CONFIRMATION_PHRASE}" to continue: ')
    return answer == CONFIRMATION_PHRASE


def default_approval_prompt(proposal: TradeProposal) -> bool:
    print()
    print("*** LIVE — REAL MONEY ***")
    print(proposal.render())
    answer = input("\nApprove this REAL trade? [y/N]: ").strip().lower()
    return answer == "y"


async def _monitor_contract(
    client: DerivClient, conn, notifier: TelegramNotifier, symbol: str, contract_id: int
) -> None:
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()

    def on_update(response: dict) -> None:
        poc = response.get("proposal_open_contract", {})
        status = poc.get("status")
        profit = poc.get("profit")
        print(f"  [{contract_id}] status={status} profit={profit}")
        if poc.get("is_sold") or status in ("sold", "won", "lost"):
            log_trade_closed(
                conn,
                contract_id=contract_id,
                sell_price=poc.get("sell_price") or 0.0,
                profit=profit or 0.0,
                status=status or "sold",
            )
            message = f"[LIVE][{symbol}] contract {contract_id} closed: {status}"
            if profit is not None:
                message += f", profit=${profit:.2f}"
            asyncio.create_task(notifier.send(message))
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
    confirm: Callable[[], bool] = confirm_live_trading,
) -> None:
    if not settings.is_live:
        raise RuntimeError(
            "This is the live-trading script — it refuses to run unless "
            "ENV=live. Use scripts/run_phase4_demo_trading.py for demo."
        )

    conn = get_connection()
    ok, reason = check_demo_track_record(settings, conn)
    print(reason)
    if not ok:
        print("Refusing to proceed to real money.")
        conn.close()
        return

    if not confirm():
        print("Confirmation phrase did not match. Aborting — nothing was done.")
        conn.close()
        return

    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    client = DerivClient(settings)
    await client.connect()
    monitors: list[asyncio.Task] = []
    try:
        balance = await client.get_balance()
        print(f"LIVE balance: ${balance:.2f}\n")

        realized_today = get_realized_pnl_today(conn, env="live")
        loss_limit = settings.daily_loss_limit_pct * balance
        if realized_today < -loss_limit:
            msg = (
                f"[LIVE] Daily kill-switch: realized loss today "
                f"(${realized_today:.2f}) exceeds "
                f"{settings.daily_loss_limit_pct:.1%} of balance "
                f"(${loss_limit:.2f}). Not proposing any new trades today."
            )
            print(msg)
            await notifier.send(msg)
            return

        news_events = []
        if settings.news_blackout_enabled:
            try:
                news_events = fetch_this_weeks_events()
            except Exception as exc:  # noqa: BLE001 — see docs/DECISIONS.md
                msg = (
                    f"[LIVE] News calendar unavailable ({exc!r}) — failing "
                    "closed: not proposing any new trades this run rather "
                    "than trading blind to a possible high-impact release."
                )
                print(msg)
                await notifier.send(msg)
                return

        correlation_matrix: dict = {}
        if settings.use_real_correlation_matrix:
            correlation_matrix, computed_at = get_latest_correlation_matrix_with_timestamp(conn)
            if is_matrix_stale(computed_at, settings.correlation_matrix_max_age_hours):
                print(
                    "[LIVE] Real correlation matrix is missing or stale "
                    f"(>{settings.correlation_matrix_max_age_hours}h old) — "
                    "falling back to the currency-overlap heuristic alone "
                    "this run. Run scripts/run_phase17_correlation_matrix.py "
                    "to refresh it."
                )
                correlation_matrix = {}

        for symbol in settings.symbols:
            open_count = get_open_trade_count(conn, env="live")
            if open_count >= settings.max_concurrent_contracts:
                print(
                    f"[{symbol}] skipped — {open_count} live contracts already "
                    f"open (max {settings.max_concurrent_contracts})"
                )
                continue

            response = await client.get_ticks_history(
                symbol, count=CANDLE_COUNT, granularity=GRANULARITY_SECONDS
            )
            candles = parse_candles(response)
            signal = generate_signal(symbol, candles)
            if signal is None:
                print(f"[{symbol}] no signal")
                continue

            if settings.news_blackout_enabled:
                blocked, event = is_within_news_blackout(
                    currency_exposure(symbol),
                    news_events,
                    datetime.now(timezone.utc),
                    minutes_before=settings.news_blackout_minutes_before,
                    minutes_after=settings.news_blackout_minutes_after,
                    min_impact=settings.news_blackout_min_impact,
                )
                if blocked:
                    msg = (
                        f"[{symbol}] skipped — news blackout: "
                        f"{event.impact} impact '{event.title}' ({event.currency}) "
                        f"at {event.at.isoformat()}"
                    )
                    print(msg)
                    await notifier.send(f"[LIVE] {msg}")
                    continue

            open_trades = get_open_trades(conn, env="live")
            correlated = correlated_open_symbols(symbol, signal.direction.value, open_trades)
            if len(correlated) >= settings.max_correlated_same_direction:
                msg = (
                    f"[{symbol}] skipped — correlation guard: already "
                    f"{signal.direction.value} on {correlated}"
                )
                print(msg)
                await notifier.send(f"[LIVE] {msg}")
                continue

            if correlation_matrix:
                matrix_correlated = correlated_by_matrix(
                    symbol, signal.direction.value, open_trades, correlation_matrix,
                    threshold=settings.correlation_matrix_threshold,
                )
                if matrix_correlated:
                    msg = (
                        f"[{symbol}] skipped — real-correlation guard: "
                        f"{signal.direction.value} stacks with {matrix_correlated} "
                        f"(|correlation| >= {settings.correlation_matrix_threshold})"
                    )
                    print(msg)
                    await notifier.send(f"[LIVE] {msg}")
                    continue

            risk = build_risk_breakdown(signal, balance, settings)
            risk = apply_live_stake_cap(risk, settings.live_max_stake_usd)
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
            except Exception as exc:  # noqa: BLE001 — see docs/DECISIONS.md
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
                env="live",
            )
            print(f"[{symbol}] LIVE bought contract {contract_id} at {buy_data['buy_price']}\n")
            await notifier.send(
                f"[LIVE][{symbol}] bought {signal.direction.value} contract "
                f"{contract_id}, stake=${risk.stake}"
            )
            monitors.append(
                asyncio.create_task(_monitor_contract(client, conn, notifier, symbol, contract_id))
            )

        if monitors:
            print(f"Monitoring {len(monitors)} open LIVE contract(s) until they close...")
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
