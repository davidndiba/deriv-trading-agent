"""Minimal Telegram alerting. Stdlib-only (urllib) — no new dependency
for something this small.

Notify-only. The per-trade approval gate stays the CLI y/n built in
Phase 3: docs/SPEC.md's non-negotiables explicitly deferred interactive
Telegram approve/reject past v1 ("CLI y/n for v1; Telegram approve/reject
can come later"). This class only ever sends alerts; it never decides
anything or feeds a decision back into the trading loop.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def _send_sync(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = json.dumps({"chat_id": self._chat_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.URLError as exc:
            print(f"[telegram] notify failed: {exc!r}")

    async def send(self, text: str) -> None:
        """No-op when not configured, so callers never need an `if
        telegram_enabled` guard at every call site."""
        if not self.enabled:
            return
        await asyncio.to_thread(self._send_sync, text)
