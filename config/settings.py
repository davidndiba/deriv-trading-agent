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
    news_blackout_enabled: bool = True
    news_blackout_minutes_before: int = 30
    news_blackout_minutes_after: int = 30
    news_blackout_min_impact: str = "High"
    use_real_correlation_matrix: bool = False
    correlation_matrix_max_age_hours: int = 24
    correlation_matrix_threshold: float = 0.7
    auto_approve_demo_trades: bool = False

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def is_live(self) -> bool:
        return self.env.lower() == "live"

    @property
    def auto_approve_effective(self) -> bool:
        """The raw AUTO_APPROVE_DEMO_TRADES flag, AND-ed with "not live"
        at the settings layer itself — defense-in-depth on top of
        run_phase4_demo_trading.py already refusing to run at all with
        ENV=live, and auto_approve_prompt() asserting the same thing
        again. Any code that reads this property instead of the raw
        field gets the "never live" guarantee for free, even if a
        future refactor adds a new call site that forgets to check."""
        return self.auto_approve_demo_trades and not self.is_live

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

    news_blackout_enabled = os.environ.get("NEWS_BLACKOUT_ENABLED", "true").strip().lower() not in (
        "false", "0", "no",
    )
    news_blackout_minutes_before = int(os.environ.get("NEWS_BLACKOUT_MINUTES_BEFORE", "30"))
    news_blackout_minutes_after = int(os.environ.get("NEWS_BLACKOUT_MINUTES_AFTER", "30"))
    news_blackout_min_impact = os.environ.get("NEWS_BLACKOUT_MIN_IMPACT", "High").strip()
    if news_blackout_minutes_before < 0 or news_blackout_minutes_after < 0:
        raise RuntimeError("NEWS_BLACKOUT_MINUTES_BEFORE/AFTER must be >= 0")
    if news_blackout_min_impact not in ("Low", "Medium", "High"):
        raise RuntimeError("NEWS_BLACKOUT_MIN_IMPACT must be Low, Medium, or High")

    use_real_correlation_matrix = os.environ.get(
        "USE_REAL_CORRELATION_MATRIX", "false"
    ).strip().lower() in ("true", "1", "yes")
    correlation_matrix_max_age_hours = int(
        os.environ.get("CORRELATION_MATRIX_MAX_AGE_HOURS", "24")
    )
    correlation_matrix_threshold = float(
        os.environ.get("CORRELATION_MATRIX_THRESHOLD", "0.7")
    )
    if correlation_matrix_max_age_hours < 1:
        raise RuntimeError("CORRELATION_MATRIX_MAX_AGE_HOURS must be >= 1")
    if not (0 < correlation_matrix_threshold <= 1):
        raise RuntimeError("CORRELATION_MATRIX_THRESHOLD must be between 0 and 1")

    auto_approve_demo_trades = os.environ.get(
        "AUTO_APPROVE_DEMO_TRADES", "false"
    ).strip().lower() in ("true", "1", "yes")

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
        news_blackout_enabled=news_blackout_enabled,
        news_blackout_minutes_before=news_blackout_minutes_before,
        news_blackout_minutes_after=news_blackout_minutes_after,
        news_blackout_min_impact=news_blackout_min_impact,
        use_real_correlation_matrix=use_real_correlation_matrix,
        correlation_matrix_max_age_hours=correlation_matrix_max_age_hours,
        correlation_matrix_threshold=correlation_matrix_threshold,
        auto_approve_demo_trades=auto_approve_demo_trades,
    )
