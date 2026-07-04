"""Telegram message templates, written in plain English for people with
little to no trading background. Jargon translation lives in
agent/dashboard/plain_english.py so both TG and the dashboard stay consistent."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agent.dashboard.plain_english import (
    friendly_exit_reason,
    friendly_regime,
    friendly_strategy,
    friendly_trail_mode,
    simplify_line,
    simplify_lines,
)

MANILA = ZoneInfo("Asia/Manila")


def _ts() -> str:
    return datetime.now(MANILA).strftime("%d %b %Y, %H:%M PH")


def opened(symbol: str, side: str, entry: float, stop: float, take_profit: float, qty: float, leg: str, regime: str, confidence: float, thesis: list[str]) -> str:
    simplified = simplify_lines(thesis)[:2] or ["This setup passed our entry checks."]
    thesis_text = "\n".join(f"• {line}" for line in simplified)
    rr = abs(take_profit - entry) / max(abs(entry - stop), 1e-9)
    return (
        f"🟢 OPENED | {symbol} {side.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Entry: `{entry:.4f}`  Size: `{qty:.5f}`\n"
        f"🛑 Safety stop: `{stop:.4f}`  🎯 Target: `{take_profit:.4f}`\n"
        f"Potential reward vs risk: `{rr:.2f}x` (higher = better payoff for the risk)\n"
        f"🧠 Style: {friendly_strategy(leg)}  🌡 Market: {friendly_regime(regime)}\n"
        f"📊 Confidence: `{confidence:.2f}` (0–1 scale, higher = stronger setup)\n\n"
        f"💭 Why we took this trade:\n{thesis_text}\n\n"
        f"⏰ {_ts()}"
    )


def closed(symbol: str, side: str, exit_price: float, pnl: float, outcome: str, reason: str, reflection: list[str] | None = None) -> str:
    icon = "✅" if outcome == "win" else "🔴" if outcome == "loss" else "⚪"
    outcome_word = {"win": "made money", "loss": "lost money", "breakeven": "broke even"}.get(outcome, outcome)
    notes = "\n".join(f"• {line}" for line in simplify_lines(reflection or [reason])[:2])
    return (
        f"{icon} CLOSED | {symbol} {side.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Exit price: `{exit_price:.4f}`  Result: `{pnl:+.2f} USDT`\n"
        f"This trade {outcome_word} — it {friendly_exit_reason(reason)}\n\n"
        f"💭 What we learned:\n{notes}\n\n"
        f"⏰ {_ts()}"
    )


def trail(symbol: str, old_stop: float, new_stop: float, mode: str, reason: str) -> str:
    return (
        f"🛡 SAFETY STOP MOVED UP | {symbol}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"`{old_stop:.4f}` → `{new_stop:.4f}` (locking in more profit, never moves backward)\n"
        f"How: {friendly_trail_mode(mode)}\n"
        f"Why: {simplify_line(reason)}\n\n"
        f"⏰ {_ts()}"
    )


def coin_digest_report(digests: list) -> str:
    lines = [f"🗞 Daily Coin Digest — {_ts()}", "━━━━━━━━━━━━━━━━━━━━"]
    for d in digests:
        coin = d.symbol.split("/")[0]
        watch = ""
        if d.watching_side and d.watch_low is not None and d.watch_high is not None:
            watch = f" | 👀 {d.watching_side.upper()} zone {d.watch_low:.4f}–{d.watch_high:.4f}"
        change = f"{d.price_change_pct_24h:+.1f}%" if d.price_change_pct_24h is not None else "—"
        sentiment_icon = {"positive": "🙂", "negative": "🙁", "neutral": "😐", "no data": "🤷"}.get(d.sentiment_label, "😐")
        lines.append(
            f"\n🪙 {coin} ({friendly_regime(d.regime)}, {change}){watch}\n"
            f"{sentiment_icon} News: {d.sentiment_label}"
        )
    return "\n".join(lines)


def brain_update(symbol: str, version: int, reason: str, disabled_legs: list[str]) -> str:
    disabled = ", ".join(friendly_strategy(leg) for leg in disabled_legs) if disabled_legs else "none"
    return (
        f"🧠 STRATEGY ADJUSTED | {symbol}\n"
        f"Update #{version} | Styles paused for this coin: {disabled}\n"
        f"Why: {simplify_line(reason)}\n"
        f"⏰ {_ts()}"
    )
