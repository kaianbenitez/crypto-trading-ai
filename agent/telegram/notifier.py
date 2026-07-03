"""Small Telegram sender wrapper."""
from __future__ import annotations

import logging

import requests

from agent.config.settings import settings

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token if token is not None else settings.telegram_bot_token
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str, parse_mode: str | None = None) -> bool:
        if not self.enabled:
            return False
        try:
            payload = {"chat_id": self.chat_id, "text": message}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json=payload,
                timeout=10,
            ).raise_for_status()
            return True
        except Exception as exc:
            log.warning("Telegram send failed: %s", exc)
            return False
