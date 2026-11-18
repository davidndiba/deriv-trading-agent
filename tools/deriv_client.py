"""Thin wrapper around python_deriv_api.

Deliberately exposes only Multipliers calls: connect, authorize, balance,
ticks_history, proposal, buy, sell, contract_update, and a
proposal_open_contract subscription. There is no generic "send raw
request" passthrough here — see docs/DECISIONS.md for why. `get_proposal`
only ever builds a MULTUP/MULTDOWN request; there is no way to pass an
arbitrary contract_type through this client.

Call shapes below follow the official library's own usage examples
(https://github.com/deriv-com/python-deriv-api/blob/master/docs/usage_examples.md),
verified against that doc rather than guessed, since this sandbox can't
install python_deriv_api or hold a real session to test against. Still,
treat the exact response field names as unverified until exercised against
a real demo account.
"""
from __future__ import annotations

from typing import Any

from deriv_api import DerivAPI

from config.settings import Settings
from schemas.models import Candle, Direction

_CONTRACT_TYPE_BY_DIRECTION = {
    Direction.UP: "MULTUP",
    Direction.DOWN: "MULTDOWN",
}


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
        self._currency: str | None = None

    async def connect(self) -> None:
        self._api = DerivAPI(app_id=self._settings.app_id)
        resp = await self._api.authorize(self._settings.api_token)
        self._currency = resp.get("authorize", {}).get("currency")

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

    async def get_proposal(
        self,
        *,
        symbol: str,
        direction: Direction,
        stake: float,
        multiplier: int,
        take_profit: float,
        stop_loss: float,
    ) -> dict[str, Any]:
        """Price a Multipliers contract. take_profit/stop_loss are dollar
        P&L amounts (Deriv's own limit_order semantics for Multipliers),
        not price levels — matches RiskBreakdown.max_gain/max_loss."""
        api = self._require_api()
        request = {
            "proposal": 1,
            "symbol": symbol,
            "contract_type": _CONTRACT_TYPE_BY_DIRECTION[direction],
            "amount": stake,
            "basis": "stake",
            "currency": self._currency or "USD",
            "multiplier": multiplier,
            "limit_order": {"take_profit": take_profit, "stop_loss": stop_loss},
        }
        return await api.proposal(request)

    async def buy_contract(self, *, proposal_id: str, price: float) -> dict[str, Any]:
        api = self._require_api()
        return await api.buy({"buy": proposal_id, "price": price})

    async def sell_contract(self, *, contract_id: int, price: float = 0) -> dict[str, Any]:
        api = self._require_api()
        return await api.sell({"sell": contract_id, "price": price})

    async def contract_update(
        self,
        *,
        contract_id: int,
        take_profit: float | None = None,
        stop_loss: float | None = None,
    ) -> dict[str, Any]:
        api = self._require_api()
        limit_order: dict[str, float] = {}
        if take_profit is not None:
            limit_order["take_profit"] = take_profit
        if stop_loss is not None:
            limit_order["stop_loss"] = stop_loss
        return await api.contract_update(
            {"contract_update": 1, "contract_id": contract_id, "limit_order": limit_order}
        )

    async def subscribe_open_contract(self, *, contract_id: int):
        """Returns an rxpy Observable — call `.subscribe(callback)` on it,
        per the library's own usage examples. Caller owns the returned
        Disposable and is responsible for disposing it once the contract
        closes (status in {"sold", "won", "lost"})."""
        api = self._require_api()
        return await api.subscribe(
            {"proposal_open_contract": 1, "contract_id": contract_id}
        )
