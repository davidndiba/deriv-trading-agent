"""Environment-driven settings. Nothing in here is hardcoded secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _parse_blackout_dates(raw: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        month, day = part.split("-")
        out.append((int(month), int(day)))
    return out


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    app_id: str
    api_token: str
    env: str  # "demo" or "live"
    risk_per_trade_pct: float
    daily_loss_limit_pct: float
    blackout_dates: list[tuple[int, int]] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    max_concurrent_contracts: int = 3
    max_correlated_same_direction: int = 1
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    live_max_stake_usd: float = 1.0
    live_min_demo_soak_days: int = 14
    live_min_demo_trades: int = 20

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def is_live(self) -> bool:
        return self.env.lower() == "live"

    def is_blackout_date(self, today: date | None = None) -> bool:
        d = today or date.today()
        return (d.month, d.day) in self.blackout_dates


def load_settings() -> Settings:
    app_id = os.environ.get("APP_ID", "")
    api_token = os.environ.get("API_TOKEN", "")
    if not app_id or not api_token:
        raise RuntimeError(
            "APP_ID and API_TOKEN must be set in .env — copy .env.example "
            "and fill in a DEMO account app_id + token first."
        )

    env = os.environ.get("ENV", "demo").strip().lower()
    if env not in ("demo", "live"):
        raise RuntimeError(f"ENV must be 'demo' or 'live', got {env!r}")

    risk_per_trade_pct = float(os.environ.get("RISK_PER_TRADE_PCT", "0.01"))
    daily_loss_limit_pct = float(os.environ.get("DAILY_LOSS_LIMIT_PCT", "0.03"))
    if not (0 < risk_per_trade_pct < 1):
        raise RuntimeError("RISK_PER_TRADE_PCT must be between 0 and 1")
    if not (0 < daily_loss_limit_pct < 1):
        raise RuntimeError("DAILY_LOSS_LIMIT_PCT must be between 0 and 1")

    blackout_dates = _parse_blackout_dates(os.environ.get("BLACKOUT_DATES", ""))
    symbols = _parse_symbols(
        os.environ.get("SYMBOLS", "frxEURUSD,frxXAUUSD,1HZ100V")
    )

    max_concurrent_contracts = int(os.environ.get("MAX_CONCURRENT_CONTRACTS", "3"))
    max_correlated_same_direction = int(
        os.environ.get("MAX_CORRELATED_SAME_DIRECTION", "1")
    )
    if max_concurrent_contracts < 1:
        raise RuntimeError("MAX_CONCURRENT_CONTRACTS must be >= 1")
    if max_correlated_same_direction < 1:
        raise RuntimeError("MAX_CORRELATED_SAME_DIRECTION must be >= 1")

    live_max_stake_usd = float(os.environ.get("LIVE_MAX_STAKE_USD", "1.0"))
    live_min_demo_soak_days = int(os.environ.get("LIVE_MIN_DEMO_SOAK_DAYS", "14"))
    live_min_demo_trades = int(os.environ.get("LIVE_MIN_DEMO_TRADES", "20"))
    if live_max_stake_usd <= 0:
        raise RuntimeError("LIVE_MAX_STAKE_USD must be > 0")
    if live_min_demo_soak_days < 1:
        raise RuntimeError("LIVE_MIN_DEMO_SOAK_DAYS must be >= 1")
    if live_min_demo_trades < 1:
        raise RuntimeError("LIVE_MIN_DEMO_TRADES must be >= 1")

    return Settings(
        app_id=app_id,
        api_token=api_token,
        env=env,
        risk_per_trade_pct=risk_per_trade_pct,
        daily_loss_limit_pct=daily_loss_limit_pct,
        blackout_dates=blackout_dates,
        symbols=symbols,
        max_concurrent_contracts=max_concurrent_contracts,
        max_correlated_same_direction=max_correlated_same_direction,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        live_max_stake_usd=live_max_stake_usd,
        live_min_demo_soak_days=live_min_demo_soak_days,
        live_min_demo_trades=live_min_demo_trades,
    )
