"""Telegram polling service for reports and two-way commands."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from agent.config.settings import settings
from agent.db.models import CommandAudit, TelegramBotState, get_session
from agent.telegram.notifier import TelegramNotifier
from agent.telegram.reports import (
    coin_report,
    digest_report,
    eod_recap,
    morning_brief,
    pnl_summary,
    positions_report,
    risk_report,
    status_report,
    validation_report,
    weekly_report,
)
from webapi.app_state import get_or_create_state

MANILA = ZoneInfo("Asia/Manila")
POLL_SEC = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("telegram-bot.log")],
)
log = logging.getLogger(__name__)


def _allowed_ids() -> set[str]:
    ids = {x.strip() for x in settings.telegram_allowed_user_ids.split(",") if x.strip()}
    if settings.telegram_chat_id:
        ids.add(str(settings.telegram_chat_id))
    return ids


def _get_state(session, key: str, default: str = "") -> str:
    row = session.query(TelegramBotState).filter(TelegramBotState.key == key).first()
    return row.value if row else default


def _set_state(session, key: str, value: str) -> None:
    row = session.query(TelegramBotState).filter(TelegramBotState.key == key).first()
    if row:
        row.value = value
    else:
        session.add(TelegramBotState(key=key, value=value))
    session.commit()


def _audit(session, user_id: str, command: str, args: str, status: str) -> None:
    session.add(CommandAudit(user_id=str(user_id), command=command, args=args, status=status))
    session.commit()


class TelegramService:
    def __init__(self):
        self.notifier = TelegramNotifier()
        self.allowed_ids = _allowed_ids()
        self.pending: dict[str, tuple[str, datetime]] = {}

    @property
    def enabled(self) -> bool:
        return bool(settings.telegram_bot_token and settings.telegram_chat_id)

    def send(self, text: str) -> None:
        self.notifier.send(text)

    def _updates(self, offset: int) -> list[dict]:
        response = requests.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
            params={"offset": offset, "timeout": 20, "allowed_updates": ["message"]},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("result", [])

    def _is_allowed(self, message: dict) -> bool:
        chat_id = str(message.get("chat", {}).get("id", ""))
        user_id = str(message.get("from", {}).get("id", ""))
        return chat_id in self.allowed_ids or user_id in self.allowed_ids

    def _handle_confirm(self, session, user_id: str, text: str) -> str | None:
        if text.lower() not in {"confirm", "yes", "y"}:
            return None
        pending = self.pending.get(user_id)
        if not pending:
            return "🤷 No pending action."
        action, expires = pending
        if datetime.now(MANILA) > expires:
            self.pending.pop(user_id, None)
            return "⌛ Confirmation expired."
        self.pending.pop(user_id, None)
        return self._execute_destructive(session, user_id, action)

    def _execute_destructive(self, session, user_id: str, action: str) -> str:
        parts = action.split()
        cmd = parts[0]
        scope = parts[1] if len(parts) > 1 else "all"
        state = get_or_create_state(session)
        if cmd == "/pause" and scope == "all":
            state.kill_switch_active = True
            state.kill_switch_reason = "telegram pause"
            session.commit()
            _audit(session, user_id, cmd, scope, "executed")
            return "⏸️ Paused: kill switch is ON. New entries are blocked."
        if cmd == "/resume" and scope == "all":
            state.kill_switch_active = False
            state.kill_switch_reason = "telegram resume"
            session.commit()
            _audit(session, user_id, cmd, scope, "executed")
            return "▶️ Resumed: kill switch is OFF. New entries allowed."
        _audit(session, user_id, cmd, scope, "unsupported")
        return "🚧 That destructive command is not wired yet. Supported: /pause all, /resume all."

    def _handle_command(self, session, user_id: str, text: str) -> str:
        confirmed = self._handle_confirm(session, user_id, text)
        if confirmed is not None:
            return confirmed

        parts = text.strip().split()
        cmd = parts[0].lower() if parts else "/help"
        args = parts[1:]
        arg_text = " ".join(args)

        if cmd in {"/pause", "/resume"}:
            action = f"{cmd} {args[0] if args else 'all'}"
            self.pending[user_id] = (action, datetime.now(MANILA) + timedelta(seconds=30))
            _audit(session, user_id, cmd, arg_text, "pending_confirmation")
            return f"⚠️ Confirm {action} within 30 seconds by replying: confirm"
        if cmd == "/status":
            _audit(session, user_id, cmd, arg_text, "ok")
            return status_report(session)
        if cmd == "/positions":
            _audit(session, user_id, cmd, arg_text, "ok")
            return positions_report(session)
        if cmd == "/pnl":
            period = args[0].lower() if args else "today"
            if period not in {"today", "week", "month", "all"}:
                period = "today"
            _audit(session, user_id, cmd, period, "ok")
            return pnl_summary(session, period)
        if cmd == "/coin":
            _audit(session, user_id, cmd, arg_text, "ok")
            return coin_report(session, args[0] if args else "BTC")
        if cmd == "/digest":
            _audit(session, user_id, cmd, arg_text, "ok")
            return digest_report(session, args[0] if args else "BTC")
        if cmd == "/report":
            report_type = args[0].lower() if args else "daily"
            _audit(session, user_id, cmd, report_type, "ok")
            if report_type == "weekly":
                return weekly_report(session)
            if report_type in {"validation", "validate"}:
                return validation_report(session)
            return eod_recap(session)
        if cmd == "/risk":
            _audit(session, user_id, cmd, arg_text, "ok")
            return risk_report(session)
        if cmd in {"/validate", "/validation"}:
            _audit(session, user_id, cmd, arg_text, "ok")
            return validation_report(session)
        if cmd == "/help":
            return (
                "📖 Commands\n"
                "📊 /status\n"
                "📍 /positions\n"
                "💰 /pnl today|week|month|all\n"
                "🪙 /coin BTC\n"
                "🗞 /digest BTC\n"
                "📅 /report daily|weekly\n"
                "⏸️ /pause all\n"
                "▶️ /resume all"
            )
        _audit(session, user_id, cmd, arg_text, "unknown")
        return "❓ Unknown command. Try /help."

    def poll_once(self, session) -> None:
        offset = int(_get_state(session, "last_update_id", "0") or "0")
        for update in self._updates(offset + 1):
            update_id = int(update["update_id"])
            _set_state(session, "last_update_id", str(update_id))
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            if not text:
                continue
            if not self._is_allowed(message):
                log.warning("Rejected Telegram message from unauthorized user/chat")
                continue
            user_id = str(message.get("from", {}).get("id") or message.get("chat", {}).get("id"))
            try:
                self.send(self._handle_command(session, user_id, text))
            except Exception as exc:
                log.exception("Command failed: %s", exc)
                self.send(f"⚠️ Command failed: {exc}")

    def scheduled_reports(self, session) -> None:
        now = datetime.now(MANILA)
        jobs = [
            ("morning", now.strftime("%Y-%m-%d"), now.hour == 8 and now.minute < 5, morning_brief),
            ("eod", now.strftime("%Y-%m-%d"), now.hour == 23 and now.minute >= 55, eod_recap),
            ("weekly", now.strftime("%G-W%V"), now.weekday() == 6 and now.hour == 20 and now.minute < 5, weekly_report),
        ]
        for name, key, due, builder in jobs:
            state_key = f"sent:{name}:{key}"
            if due and _get_state(session, state_key) != "1":
                self.send(builder(session))
                _set_state(session, state_key, "1")
                log.info("Sent scheduled report: %s", name)

    def run(self) -> None:
        if not self.enabled:
            log.warning("Telegram service disabled: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return
        log.info("Telegram service starting")
        session = get_session()
        try:
            if not _get_state(session, "last_update_id"):
                updates = self._updates(0)
                if updates:
                    _set_state(session, "last_update_id", str(max(int(u["update_id"]) for u in updates)))
                    log.info("Marked %d existing Telegram update(s) as seen", len(updates))
        finally:
            session.close()
        self.send("🤖 Telegram bot online. Send /help for commands.")
        while True:
            session = get_session()
            try:
                self.scheduled_reports(session)
                self.poll_once(session)
            except Exception as exc:
                log.warning("Telegram service cycle failed: %s", exc)
                time.sleep(10)
            finally:
                session.close()
            time.sleep(POLL_SEC)


def main():
    TelegramService().run()


if __name__ == "__main__":
    main()
