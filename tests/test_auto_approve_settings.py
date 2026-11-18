"""The settings-layer defense-in-depth for AUTO_APPROVE_DEMO_TRADES —
the single most important property in this whole feature: the flag must
never be effective when ENV=live, even if left set by mistake.

scripts/run_phase4_demo_trading.py's make_auto_approve_prompt() itself
can't be imported here (needs pydantic/deriv_api, same limitation as
every trading script in this build), but its guard logic is a one-line
`if not settings.auto_approve_effective: raise` against this exact
property — see docs/PROGRESS.md for how it was verified by direct
execution against a reimplementation before being written down as a
permanent part of the file.
"""
import sys
import types

# config/settings.py needs python-dotenv, which isn't installed in this
# sandbox — stub it only if it's genuinely missing (an ImportError, not
# just "not imported yet"), so this never shadows the real package when
# it IS installed (CI, or anyone's actual dev environment).
try:
    import dotenv  # noqa: F401
except ImportError:
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = fake_dotenv

from config.settings import Settings


def _settings(env: str, auto_approve_demo_trades: bool) -> Settings:
    return Settings(
        app_id="x", api_token="y", env=env,
        risk_per_trade_pct=0.01, daily_loss_limit_pct=0.03,
        auto_approve_demo_trades=auto_approve_demo_trades,
    )


def test_auto_approve_off_by_default():
    s = _settings("demo", auto_approve_demo_trades=False)
    assert s.auto_approve_effective is False


def test_auto_approve_effective_when_demo_and_enabled():
    s = _settings("demo", auto_approve_demo_trades=True)
    assert s.auto_approve_effective is True


def test_auto_approve_never_effective_when_live_even_if_flag_is_set():
    s = _settings("live", auto_approve_demo_trades=True)
    assert s.auto_approve_demo_trades is True  # the raw flag is still set...
    assert s.auto_approve_effective is False   # ...but it's never effective
