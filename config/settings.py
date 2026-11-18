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

    return Settings(
        app_id=app_id,
        api_token=api_token,
        env=env,
        risk_per_trade_pct=risk_per_trade_pct,
        daily_loss_limit_pct=daily_loss_limit_pct,
        blackout_dates=blackout_dates,
        symbols=symbols,
    )
