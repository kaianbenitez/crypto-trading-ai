"""Telegram message templates, written in plain English for people with
little to no trading background. Jargon translation lives in
agent/dashboard/plain_english.py so both TG and the dashboard stay consistent."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agent.config.settings import settings
from agent.dashboard.plain_english import (
    friendly_regime,
    friendly_strategy,
    friendly_trail_mode,
    simplify_line,
)
from agent.dashboard.trade_narrative import build_narrative

MANILA = ZoneInfo("Asia/Manila")


def _ts() -> str:
    return datetime.now(MANILA).strftime("%d %b %Y, %H:%M PH")


def opened(trade, session=None) -> str:
    """Structured open notification: direction/strategy, confidence+EV,
    fact-based thesis, why accepted, weakness, plan, invalidation, and past
    same-symbol context — all built deterministically from trade_narrative."""
    n = build_narrative(trade, session)
    icon = "🟢" if n.side == "long" else "🔴"
    conf = f"{n.confidence:.2f}" if n.confidence is not None else "—"
    ev = f"{n.ev_r:+.2f}R" if n.ev_r is not None else "—"
    risk = f"{n.risk_pct:.2f}%" if n.risk_pct is not None else "—"

    lines = [
        f"{icon} {n.side.upper()} | {n.symbol} | {n.strategy_name}",
        f"Conf {conf} | EV {ev} | Risk {risk}",
        "",
        "Thesis:",
        " ".join(n.thesis_lines),
    ]
    if n.why_accepted_lines:
        lines += ["", "Why accepted:", " ".join(n.why_accepted_lines)]
    if n.weakness_line:
        lines += ["", "Weakness:", n.weakness_line]
    lines += [
        "",
        "Plan:",
        f"Entry {n.entry:.4f} | SL {n.stop_loss:.4f} | TP {n.take_profit:.4f} | R:R {n.rr:.1f}",
        f"Invalidation: {n.invalidation_line}",
        "",
        "Past:",
        n.past_context_line,
        "",
        f"⏰ {_ts()}",
    ]
    return "\n".join(lines)


def closed(trade, session=None) -> str:
    """Structured close/postmortem: outcome, why it failed/worked tied back
    to whatever concern was flagged at entry (not a generic restatement),
    the lesson, and compact stats."""
    n = build_narrative(trade, session)
    icon = "✅" if n.outcome == "win" else "🔴" if n.outcome == "loss" else "⚪"
    outcome_label = (n.outcome or "closed").upper()
    pnl = n.pnl_usdt if n.pnl_usdt is not None else 0.0

    lines = [f"{icon} CLOSED | {n.symbol} | {outcome_label} | {pnl:+.2f} USDT", ""]
    if n.failure_line:
        lines += ["Why it failed:" if n.outcome == "loss" else "Result:", n.failure_line, ""]
    if settings.telegram_show_close_lessons and n.lesson_line:
        lines += ["Lesson:", n.lesson_line, ""]

    r_txt = f"{n.r_multiple:+.1f}R" if n.r_multiple is not None else "—"
    held_txt = n.held_duration or "—"
    lines += ["Stats:", f"Exit reason: {n.exit_reason or '—'} | R: {r_txt} | Held: {held_txt}", "", f"⏰ {_ts()}"]
    return "\n".join(lines)


def trail(symbol: str, old_stop: float, new_stop: float, mode: str, reason: str) -> str:
    return (
        f"🛡 SAFETY STOP MOVED UP | {symbol}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"`{old_stop:.4f}` → `{new_stop:.4f}` (locking in more profit, never moves backward)\n"
        f"How: {friendly_trail_mode(mode)}\n"
        f"Why: {simplify_line(reason)}\n\n"
        f"⏰ {_ts()}"
    )


def choch_alert(symbol: str, trade_side: str, price: float) -> str:
    """CHoCH (change of character) against an open position's direction —
    the one structure event worth interrupting someone for. A BOS
    (continuation, structure still agrees with the trade) never fires this;
    see agent/analysis/smc_structure.py."""
    new_bias = "bullish" if trade_side == "short" else "bearish"
    return (
        f"🔀 CHoCH DETECTED | {symbol}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Structure just turned {new_bias} — against your {trade_side.upper()} position.\n"
        f"Broke through `{price:.4f}`.\n"
        f"This doesn't close the trade — your stop/target are unchanged — but it's "
        f"worth a look; the trend that supported this trade may be reversing.\n\n"
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
