"""Self-diagnosis checks for the trading agent."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def build_self_report(session, bankroll_usdt: float) -> dict:
    from agent.db.models import Trade
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    month_ago = now - timedelta(days=30)
    day_trades = session.query(Trade).filter(Trade.closed_at >= day_ago, Trade.closed_at.isnot(None)).all()
    month_trades = session.query(Trade).filter(Trade.closed_at >= month_ago, Trade.closed_at.isnot(None)).all()
    open_count = session.query(Trade).filter(Trade.closed_at.is_(None)).count()
    day_pnl = sum(t.pnl_usdt or 0 for t in day_trades)
    month_pnl = sum(t.pnl_usdt or 0 for t in month_trades)
    warnings = []
    if bankroll_usdt and day_pnl <= -0.03 * bankroll_usdt:
        warnings.append("Daily loss circuit threshold reached or exceeded")
    by_symbol = {}
    for t in month_trades:
        stats = by_symbol.setdefault(t.symbol, {"count": 0, "pnl": 0.0, "wins": 0})
        stats["count"] += 1
        stats["pnl"] += t.pnl_usdt or 0
        stats["wins"] += 1 if t.outcome == "win" else 0
    for symbol, stats in by_symbol.items():
        if stats["count"] >= 30 and stats["pnl"] < 0:
            warnings.append(f"{symbol} negative expectancy over last 30d; consider shadow mode")
    return {
        "created_at": now.isoformat(),
        "open_positions": open_count,
        "day_pnl": day_pnl,
        "month_pnl": month_pnl,
        "symbols": by_symbol,
        "warnings": warnings,
    }


def persist_self_report(session, report_type: str, report: dict) -> None:
    from agent.db.models import SelfMonitorReport
    session.add(SelfMonitorReport(
        report_type=report_type,
        payload=json.dumps(report, default=str),
        warning_count=len(report.get("warnings") or []),
    ))
    session.commit()
