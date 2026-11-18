"""Thin wrapper around python_deriv_api.

Deliberately exposes only the calls Phase 0/1 need: connect, authorize,
balance, ticks_history. There is no generic "send raw request" passthrough
here — see docs/DECISIONS.md for why. `proposal`/`buy`/`sell`/
`contract_update` are added in Phase 3, restricted to MULTUP/MULTDOWN only.
"""
from __future__ import annotations

from typing import Any

from deriv_api import DerivAPI

from config.settings import Settings
from schemas.models import Candle


def parse_candles(ticks_history_response: dict[str, Any]) -> list[Candle]:
    """Parse a `style=candles` ticks_history response into Candle models."""
    raw_candles = ticks_history_response.get("candles")
    if raw_candles is None:
        raise ValueError(
            "Response has no 'candles' key — was the request made with "
            "style='candles'? (raw ticks need a different parser)"
        )
    return [
        Candle(
            epoch=c["epoch"],
            open=float(c["open"]),
            high=float(c["high"]),
            low=float(c["low"]),
            close=float(c["close"]),
        )
        for c in raw_candles
    ]


class DerivClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._api: DerivAPI | None = None

    async def connect(self) -> None:
        self._api = DerivAPI(app_id=self._settings.app_id)
        await self._api.authorize(self._settings.api_token)

    async def disconnect(self) -> None:
        if self._api is not None:
            await self._api.clear()
            self._api = None

    def _require_api(self) -> DerivAPI:
        if self._api is None:
            raise RuntimeError("DerivClient.connect() must be awaited first")
        return self._api

    async def get_balance(self) -> float:
        api = self._require_api()
        resp = await api.balance()
        return float(resp["balance"]["balance"])

    async def get_ticks_history(
        self,
        symbol: str,
        *,
        count: int = 500,
        granularity: int | None = None,
        style: str = "candles",
    ) -> dict[str, Any]:
        """Pull historical ticks/candles for a symbol.

        granularity in seconds (e.g. 60 for 1m candles); omit for raw ticks.
        """
        api = self._require_api()
        request: dict[str, Any] = {
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": style,
        }
        if granularity is not None and style == "candles":
            request["granularity"] = granularity
        return await api.ticks_history(request)
