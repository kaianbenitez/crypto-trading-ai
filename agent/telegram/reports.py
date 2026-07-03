"""Telegram report builders for scheduled summaries and commands."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from agent.config.settings import settings
from agent.db.models import Trade
from webapi.app_state import get_or_create_state

MANILA = ZoneInfo("Asia/Manila")


def _now_manila() -> datetime:
    return datetime.now(MANILA)


def _fmt_money(value: float) -> str:
    return f"{value:+.2f} USDT"


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "today":
        local = _now_manila()
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_local.astimezone(timezone.utc).replace(tzinfo=None)
    if period == "week":
        return (now - timedelta(days=7)).replace(tzinfo=None)
    if period == "month":
        return (now - timedelta(days=30)).replace(tzinfo=None)
    return None


def closed_trades(session: Session, period: str = "today") -> list[Trade]:
    query = session.query(Trade).filter(Trade.closed_at.isnot(None))
    start = _period_start(period)
    if start is not None:
        query = query.filter(Trade.closed_at >= start)
    return query.order_by(Trade.closed_at.desc()).all()


def open_trades(session: Session) -> list[Trade]:
    return session.query(Trade).filter(Trade.closed_at.is_(None)).order_by(Trade.opened_at.desc()).all()


def pnl_summary(session: Session, period: str = "today") -> str:
    trades = closed_trades(session, period)
    pnl = sum(t.pnl_usdt or 0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl_usdt or 0) > 0)
    losses = sum(1 for t in trades if (t.pnl_usdt or 0) < 0)
    wr = (wins / len(trades) * 100) if trades else 0.0
    icon = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
    return (
        f"💰 P&L {period}\n"
        f"🔢 Trades: {len(trades)} | 🎯 WR: {wr:.1f}%\n"
        f"✅ {wins}W / ❌ {losses}L | {icon} P&L: {_fmt_money(pnl)}"
    )


def status_report(session: Session) -> str:
    state = get_or_create_state(session)
    opens = open_trades(session)
    kill_icon = "🔴" if state.kill_switch_active else "🟢"
    return (
        "🤖 Bot status\n"
        f"🧪 Mode: {'TESTNET' if settings.binance_testnet else '🔴 LIVE'}\n"
        f"🏦 Exchange: {settings.exchange}\n"
        f"{kill_icon} Kill switch: {'ON' if state.kill_switch_active else 'OFF'}\n"
        f"📊 Open positions: {len(opens)}\n"
        f"💵 Bankroll: {settings.bankroll_usdt:.2f} USDT\n"
        f"⏰ Time: {_now_manila().strftime('%d %b %Y %H:%M PH')}"
    )


def positions_report(session: Session) -> str:
    trades = open_trades(session)
    if not trades:
        return "📊 Open positions\n👀 None right now. Bot is scanning."
    lines = ["📊 Open positions"]
    for t in trades:
        side_icon = "🟢" if t.side == "long" else "🔴"
        lines.extend([
            f"{side_icon} {t.symbol} {t.side.upper()} | {t.strategy_name}",
            f"Entry {t.entry_price:.4f} | SL {t.stop_loss:.4f} | TP {t.take_profit:.4f}",
        ])
    return "\n".join(lines)


def coin_report(session: Session, symbol_text: str) -> str:
    symbol = symbol_text.upper()
    if "/" not in symbol:
        symbol = f"{symbol}/USDT"
    trades = (
        session.query(Trade)
        .filter(Trade.symbol == symbol, Trade.closed_at.isnot(None))
        .order_by(Trade.closed_at.desc())
        .limit(20)
        .all()
    )
    pnl = sum(t.pnl_usdt or 0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl_usdt or 0) > 0)
    wr = (wins / len(trades) * 100) if trades else 0.0
    open_trade = session.query(Trade).filter(Trade.symbol == symbol, Trade.closed_at.is_(None)).first()
    return (
        f"🧠 {symbol} brain\n"
        f"📍 Open: {'✅ yes' if open_trade else '❌ no'}\n"
        f"🔢 Last 20 closed: {len(trades)} | 🎯 WR {wr:.1f}% | 💰 P&L {_fmt_money(pnl)}"
    )


def morning_brief(session: Session) -> str:
    opens = open_trades(session)
    yesterday = closed_trades(session, "today")
    pnl = sum(t.pnl_usdt or 0 for t in yesterday)
    state = get_or_create_state(session)
    kill_icon = "🔴" if state.kill_switch_active else "🟢"
    lines = [
        "🌅 Morning brief",
        _now_manila().strftime("%d %b %Y, 08:00 PH"),
        f"💰 Overnight/today P&L: {_fmt_money(pnl)} from {len(yesterday)} closed trade(s)",
        f"📊 Open positions: {len(opens)}",
        f"{kill_icon} Kill switch: {'ON' if state.kill_switch_active else 'OFF'}",
    ]
    if opens:
        lines.append("📍 Open:")
        for t in opens[:6]:
            side_icon = "🟢" if t.side == "long" else "🔴"
            lines.append(f"{side_icon} {t.symbol} {t.side.upper()} entry {t.entry_price:.4f} SL {t.stop_loss:.4f}")
    else:
        lines.append("👀 Watch: no open exposure; bot is scanning all active symbols.")
    return "\n".join(lines)


def eod_recap(session: Session) -> str:
    trades = closed_trades(session, "today")
    pnl = sum(t.pnl_usdt or 0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl_usdt or 0) > 0)
    losses = sum(1 for t in trades if (t.pnl_usdt or 0) < 0)
    lines = [
        "🌙 End-of-day recap",
        _now_manila().strftime("%d %b %Y, %H:%M PH"),
        f"🔢 Closed trades: {len(trades)} | ✅ {wins}W / ❌ {losses}L",
        f"💰 Realized P&L: {_fmt_money(pnl)}",
        f"📊 Open positions: {len(open_trades(session))}",
    ]
    for t in trades[:5]:
        icon = "✅" if t.outcome == "win" else "❌" if t.outcome == "loss" else "⚪"
        lines.append(f"{icon} {t.symbol} {t.side.upper()} {t.outcome or ''} {_fmt_money(t.pnl_usdt or 0)}")
    return "\n".join(lines)


def weekly_report(session: Session) -> str:
    trades = closed_trades(session, "week")
    pnl = sum(t.pnl_usdt or 0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl_usdt or 0) > 0)
    wr = (wins / len(trades) * 100) if trades else 0.0
    by_symbol: dict[str, float] = {}
    by_leg: dict[str, float] = {}
    for t in trades:
        by_symbol[t.symbol] = by_symbol.get(t.symbol, 0.0) + (t.pnl_usdt or 0)
        by_leg[t.strategy_name] = by_leg.get(t.strategy_name, 0.0) + (t.pnl_usdt or 0)
    top_symbols = sorted(by_symbol.items(), key=lambda item: item[1], reverse=True)[:5]
    top_legs = sorted(by_leg.items(), key=lambda item: item[1], reverse=True)[:5]
    lines = [
        "📅 Weekly report",
        _now_manila().strftime("Week ending %d %b %Y"),
        f"🔢 Trades: {len(trades)} | 🎯 WR {wr:.1f}% | 💰 P&L {_fmt_money(pnl)}",
        "🪙 By coin:",
    ]
    lines.extend([f"- {sym}: {_fmt_money(val)}" for sym, val in top_symbols] or ["- no closed trades"])
    lines.append("🧩 By leg:")
    lines.extend([f"- {leg}: {_fmt_money(val)}" for leg, val in top_legs] or ["- no closed trades"])
    return "\n".join(lines)
