"""Phase 4 entry point: Phase 3's approval-gated demo trading, hardened
with a max-concurrent-contracts cap, a currency-correlation guard,
Telegram alerting, a news-event blackout, and — opt-in via
USE_REAL_CORRELATION_MATRIX — a second correlation check against an
actually-measured price correlation (scripts/run_phase17_correlation_matrix.py),
additive alongside the currency-overlap heuristic rather than replacing
it. Falls back to the heuristic alone if no matrix has been logged yet
or the logged one is older than CORRELATION_MATRIX_MAX_AGE_HOURS.

Still demo only — refuses ENV=live, same as every prior phase. Per
docs/SPEC.md, Phase 4 is only considered *done* after Phase 3 has run
clean for 2-4 weeks; this script can be built and reviewed before that,
but don't treat its guards as license to skip that soak period before
moving toward real money (Phase 5).

The CLI y/n approval gate from Phase 3 is the default and still the only
thing that can trigger a `buy` on a live account — Telegram here is
notify-only, per docs/SPEC.md's non-negotiables ("CLI y/n for v1;
Telegram approve/reject can come later").

For unattended demo soak runs, AUTO_APPROVE_DEMO_TRADES=true (default
false) replaces the human y/n with automatic approval — every other
guard above still runs first, and this flag has NO effect at all unless
ENV=demo (enforced three separate ways: this script already refuses to
run at all with ENV=live, Settings.auto_approve_effective is AND-ed with
"not live" at the settings layer, and auto_approve_prompt() asserts that
property again at call time). --loop runs continuously instead of once;
see main() for both.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from typing import Callable

import _bootstrap  # noqa: F401
from agents.risk import build_risk_breakdown
from agents.signals import generate_signal
from config.settings import Settings, load_settings
from schemas.models import TradeProposal
from storage.db import (
    get_connection,
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


def default_approval_prompt(proposal: TradeProposal) -> bool:
    print()
    print(proposal.render())
    answer = input("\nApprove this trade? [y/N]: ").strip().lower()
    return answer == "y"


def make_auto_approve_prompt(settings: Settings) -> Callable[[TradeProposal], bool]:
    """Returns an approval function that approves every proposal without
    waiting for input() — for unattended demo soak runs (AUTO_APPROVE_DEMO_TRADES).

    Every other guard (kill-switch, concurrency, correlation, news
    blackout) still runs before a proposal ever reaches this function;
    this only replaces the human y/n, nothing else. The full two-sided
    risk/reward breakdown is still printed and logged for every trade,
    auto-approved or not — the only thing missing is a human having read
    it first.

    Takes `settings` (not a bare bool) specifically so it can assert
    `settings.auto_approve_effective` at call time — the property that's
    AND-ed with "not live" — rather than trust whatever flag the caller
    computed, as one more layer on top of main()'s own check and
    run()'s unconditional refusal to execute at all with ENV=live.
    """

    def auto_approve_prompt(proposal: TradeProposal) -> bool:
        # A plain `if`, not `assert` — assert statements are compiled
        # out entirely under `python -O`, which would silently disable
        # this defense-in-depth layer. This check must always run.
        if not settings.auto_approve_effective:
            raise RuntimeError(
                "auto_approve_prompt called without auto_approve_effective — "
                "this must never happen; refusing to approve."
            )
        print()
        print("[AUTO-APPROVED — DEMO ONLY, no human reviewed this]")
        print(proposal.render())
        return True

    return auto_approve_prompt


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
            message = f"[{symbol}] contract {contract_id} closed: {status}"
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
) -> None:
    if settings.is_live:
        raise RuntimeError(
            "Phase 4 is still demo-only — refusing to run with ENV=live."
        )

    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
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
            msg = (
                f"Daily kill-switch: realized loss today (${realized_today:.2f}) "
                f"exceeds {settings.daily_loss_limit_pct:.1%} of balance "
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
                    f"News calendar unavailable ({exc!r}) — failing closed: "
                    "not proposing any new trades this run rather than "
                    "trading blind to a possible high-impact release."
                )
                print(msg)
                await notifier.send(msg)
                return

        correlation_matrix: dict = {}
        if settings.use_real_correlation_matrix:
            correlation_matrix, computed_at = get_latest_correlation_matrix_with_timestamp(conn)
            if is_matrix_stale(computed_at, settings.correlation_matrix_max_age_hours):
                print(
                    "Real correlation matrix is missing or stale "
                    f"(>{settings.correlation_matrix_max_age_hours}h old) — "
                    "falling back to the currency-overlap heuristic alone "
                    "this run. Run scripts/run_phase17_correlation_matrix.py "
                    "to refresh it."
                )
                correlation_matrix = {}

        for symbol in settings.symbols:
            open_count = get_open_trade_count(conn)
            if open_count >= settings.max_concurrent_contracts:
                print(
                    f"[{symbol}] skipped — {open_count} contracts already open "
                    f"(max {settings.max_concurrent_contracts})"
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
                    await notifier.send(msg)
                    continue

            open_trades = get_open_trades(conn)
            correlated = correlated_open_symbols(symbol, signal.direction.value, open_trades)
            if len(correlated) >= settings.max_correlated_same_direction:
                msg = (
                    f"[{symbol}] skipped — correlation guard: already "
                    f"{signal.direction.value} on {correlated} "
                    f"(max {settings.max_correlated_same_direction} per currency/direction)"
                )
                print(msg)
                await notifier.send(msg)
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
                    await notifier.send(msg)
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
            )
            print(f"[{symbol}] bought contract {contract_id} at {buy_data['buy_price']}\n")
            auto_tag = "[AUTO-APPROVED] " if settings.auto_approve_effective else ""
            await notifier.send(
                f"{auto_tag}[{symbol}] bought {signal.direction.value} contract {contract_id}, "
                f"stake=${risk.stake}"
            )
            monitors.append(
                asyncio.create_task(_monitor_contract(client, conn, notifier, symbol, contract_id))
            )

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


async def _run_loop(settings: Settings, approval_prompt, interval_seconds: int) -> None:
    """Repeats run() forever, sleeping between passes. Each pass makes
    its own fresh Deriv connection (run() already connects/disconnects
    internally) — not held open across the sleep. Ctrl+C stops it
    cleanly; any other exception from a single pass is logged and the
    loop continues rather than taking the whole process down overnight."""
    while True:
        try:
            await run(settings, approval_prompt=approval_prompt)
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            print(f"Pass failed, will retry next interval: {exc!r}")
        print(f"--- sleeping {interval_seconds}s before the next pass ---\n")
        await asyncio.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously instead of a single pass, sleeping "
        "--interval-seconds between runs. Still blocks on input() for "
        "every trade unless AUTO_APPROVE_DEMO_TRADES=true in .env.",
    )
    parser.add_argument(
        "--interval-seconds", type=int, default=300,
        help="Seconds to sleep between passes in --loop mode (default 300).",
    )
    args = parser.parse_args()

    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    approval_prompt = (
        make_auto_approve_prompt(settings)
        if settings.auto_approve_effective
        else default_approval_prompt
    )
    if settings.auto_approve_demo_trades and not settings.auto_approve_effective:
        print(
            "AUTO_APPROVE_DEMO_TRADES is set but has no effect here "
            f"(ENV={settings.env!r}) — falling back to manual approval.",
            file=sys.stderr,
        )

    if args.loop:
        if args.interval_seconds < 1:
            print("Config error: --interval-seconds must be >= 1", file=sys.stderr)
            raise SystemExit(1)
        if not settings.auto_approve_effective:
            print(
                "WARNING: --loop without AUTO_APPROVE_DEMO_TRADES=true will "
                "block on input() the moment a signal fires, with nothing "
                "to read it. Set AUTO_APPROVE_DEMO_TRADES=true in .env for "
                "genuinely unattended operation, or stay at the terminal.",
                file=sys.stderr,
            )
        try:
            asyncio.run(_run_loop(settings, approval_prompt, args.interval_seconds))
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        asyncio.run(run(settings, approval_prompt=approval_prompt))


if __name__ == "__main__":
    main()
