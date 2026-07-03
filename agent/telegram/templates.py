"""Telegram message templates with compact reasoning."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MANILA = ZoneInfo("Asia/Manila")


def _ts() -> str:
    return datetime.now(MANILA).strftime("%d %b %Y, %H:%M PH")


def opened(symbol: str, side: str, entry: float, stop: float, take_profit: float, qty: float, leg: str, regime: str, confidence: float, thesis: list[str]) -> str:
    thesis_text = "\n".join((thesis or ["Setup passed strategy checks."])[:2])
    rr = abs(take_profit - entry) / max(abs(entry - stop), 1e-9)
    return (
        f"🟢 OPENED | {symbol} {side.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Entry: `{entry:.4f}`  Size: `{qty:.5f}`\n"
        f"SL: `{stop:.4f}`  TP: `{take_profit:.4f}`  R:R `{rr:.2f}`\n"
        f"🧠 Leg: {leg}  🌡 Regime: {regime}\n"
        f"📊 Confidence: `{confidence:.2f}`\n\n"
        f"💭 Thesis:\n{thesis_text}\n\n"
        f"⏰ {_ts()}"
    )


def closed(symbol: str, side: str, exit_price: float, pnl: float, outcome: str, reason: str, reflection: list[str] | None = None) -> str:
    icon = "✅" if outcome == "win" else "🔴" if outcome == "loss" else "⚪"
    notes = "\n".join((reflection or [reason])[:2])
    return (
        f"{icon} CLOSED | {symbol} {side.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Exit: `{exit_price:.4f}`  PnL: `{pnl:+.2f} USDT`\n"
        f"Outcome: {outcome.upper()}  Reason: {reason}\n\n"
        f"💭 Reflection:\n{notes}\n\n"
        f"⏰ {_ts()}"
    )


def trail(symbol: str, old_stop: float, new_stop: float, mode: str, reason: str) -> str:
    return (
        f"🛡 TRAIL MOVED | {symbol}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"SL: `{old_stop:.4f}` → `{new_stop:.4f}`\n"
        f"Mode: {mode}\n"
        f"Why: {reason}\n\n"
        f"⏰ {_ts()}"
    )


def brain_update(symbol: str, version: int, reason: str, disabled_legs: list[str]) -> str:
    disabled = ", ".join(disabled_legs) if disabled_legs else "none"
    return (
        f"🧠 BRAIN UPDATED | {symbol}\n"
        f"v{version} | Disabled legs: {disabled}\n"
        f"Reason: {reason}\n"
        f"⏰ {_ts()}"
    )
