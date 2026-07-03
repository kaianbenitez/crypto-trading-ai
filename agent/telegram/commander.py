"""Telegram command scaffolding.

Destructive commands are intentionally marked pending-confirmation here. The
polling/webhook runner can call `handle_command` and enforce the returned action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DESTRUCTIVE = {"/pause", "/resume", "/close", "/close_all", "/trail", "/emergency_stop"}


@dataclass
class CommandResponse:
    text: str
    requires_confirmation: bool = False
    action: str | None = None


class TelegramCommander:
    def __init__(self, allowed_user_ids: set[str]):
        self.allowed_user_ids = allowed_user_ids
        self.last_destructive_at: datetime | None = None

    def handle_command(self, user_id: str, text: str) -> CommandResponse:
        if user_id not in self.allowed_user_ids:
            return CommandResponse("Not authorized.")
        parts = text.strip().split()
        command = parts[0].lower() if parts else "/help"
        args = parts[1:]
        if command in DESTRUCTIVE:
            now = datetime.now(timezone.utc)
            if self.last_destructive_at and now - self.last_destructive_at < timedelta(seconds=60):
                return CommandResponse("Rate limit: destructive commands are limited to once per 60s.")
            self.last_destructive_at = now
            return CommandResponse(
                f"Confirm `{command} {' '.join(args)}` within 30s before I execute it.",
                requires_confirmation=True,
                action=" ".join([command] + args),
            )
        if command == "/help":
            return CommandResponse("/status /positions /pnl /coin BTC /reasoning BTC /regime /weights /params BTC /health /report daily")
        return CommandResponse(f"{command} is recognized as read-only scaffolding; API wiring comes next.")
