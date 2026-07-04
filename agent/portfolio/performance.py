"""Portfolio performance metrics for validation and risk tiers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Iterable

from agent.db.models import Trade


@dataclass
class PerformanceMetrics:
    days: int
    bankroll_usdt: float
    trade_count: int = 0
    closed_count: int = 0
    open_count: int = 0
    total_pnl_usdt: float = 0.0
    roi_pct: float = 0.0
    win_rate_pct: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    max_consecutive_losses: int = 0
    distinct_symbols: int = 0
    reentry_count: int = 0
    reentry_pnl_usdt: float = 0.0
    reentry_expectancy_r: float = 0.0
    avg_estimated_cost_r: float = 0.0
    high_cost_trade_count: int = 0
    runner_count: int = 0
    runner_pnl_usdt: float = 0.0
    by_symbol: dict[str, dict] = field(default_factory=dict)
    by_strategy: dict[str, dict] = field(default_factory=dict)


def _as_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def r_multiple(trade: Trade) -> float:
    if not trade.entry_price or not trade.stop_loss:
        return 0.0
    initial_r = abs(float(trade.entry_price) - float(trade.stop_loss))
    if initial_r <= 0:
        return 0.0
    direction = 1 if trade.side == "long" else -1
    exit_price = float(trade.exit_price or trade.entry_price)
    return ((exit_price - float(trade.entry_price)) * direction) / initial_r


def _bucket(items: Iterable[Trade], key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for trade in items:
        name = str(getattr(trade, key) or "unknown")
        row = out.setdefault(name, {"count": 0, "pnl": 0.0, "wins": 0, "avg_r": 0.0})
        row["count"] += 1
        row["pnl"] += float(trade.pnl_usdt or 0)
        row["wins"] += 1 if (trade.pnl_usdt or 0) > 0 else 0
        row["avg_r"] += r_multiple(trade)
    for row in out.values():
        count = max(row["count"], 1)
        row["win_rate_pct"] = row["wins"] / count * 100
        row["avg_r"] = row["avg_r"] / count
        row["pnl"] = round(row["pnl"], 4)
        row["win_rate_pct"] = round(row["win_rate_pct"], 2)
        row["avg_r"] = round(row["avg_r"], 4)
    return out


def _drawdown_pct(bankroll: float, closed: list[Trade]) -> float:
    equity = bankroll
    peak = bankroll
    max_dd = 0.0
    for trade in closed:
        equity += float(trade.pnl_usdt or 0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)
    return max_dd


def _max_loss_streak(closed: list[Trade]) -> int:
    streak = 0
    max_streak = 0
    for trade in closed:
        if (trade.pnl_usdt or 0) < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _mark_reentries(closed: list[Trade], window_hours: float = 8.0) -> set[int]:
    by_symbol: dict[str, Trade] = {}
    reentry_ids: set[int] = set()
    for trade in closed:
        prev = by_symbol.get(trade.symbol)
        if prev and prev.closed_at and trade.opened_at:
            prev_closed = _as_utc_naive(prev.closed_at)
            opened = _as_utc_naive(trade.opened_at)
            if prev_closed and opened:
                hours = (opened - prev_closed).total_seconds() / 3600
                if 0 <= hours <= window_hours and prev.side == trade.side:
                    reentry_ids.add(trade.id)
        by_symbol[trade.symbol] = trade
    return reentry_ids


def build_performance_metrics(session, bankroll_usdt: float, days: int = 30) -> PerformanceMetrics:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    query = session.query(Trade)
    trades = query.filter(Trade.opened_at >= cutoff).order_by(Trade.opened_at.asc()).all()
    closed = [t for t in trades if t.closed_at is not None]
    open_count = len([t for t in trades if t.closed_at is None])
    pnl = sum(float(t.pnl_usdt or 0) for t in closed)
    wins = [t for t in closed if (t.pnl_usdt or 0) > 0]
    losses = [t for t in closed if (t.pnl_usdt or 0) < 0]
    rs = [r_multiple(t) for t in closed]
    gross_win = sum(float(t.pnl_usdt or 0) for t in wins)
    gross_loss = abs(sum(float(t.pnl_usdt or 0) for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    if not isfinite(profit_factor):
        profit_factor = 999.0

    reentry_ids = _mark_reentries(closed)
    reentries = [t for t in closed if t.id in reentry_ids]
    reentry_rs = [r_multiple(t) for t in reentries]
    estimated_cost_rs = []
    high_cost_count = 0
    runners = []
    for trade in closed:
        snap = trade.get_indicator_snapshot()
        try:
            cost_r = float(snap.get("estimated_cost_r") or 0.0)
        except Exception:
            cost_r = 0.0
        if cost_r > 0:
            estimated_cost_rs.append(cost_r)
            realized_r = abs(r_multiple(trade))
            if realized_r > 0 and cost_r / realized_r >= 0.2:
                high_cost_count += 1
        if trade.exit_reason == "trailing_take_profit":
            runners.append(trade)

    return PerformanceMetrics(
        days=days,
        bankroll_usdt=bankroll_usdt,
        trade_count=len(trades),
        closed_count=len(closed),
        open_count=open_count,
        total_pnl_usdt=round(pnl, 4),
        roi_pct=round((pnl / bankroll_usdt * 100) if bankroll_usdt else 0.0, 4),
        win_rate_pct=round((len(wins) / len(closed) * 100) if closed else 0.0, 2),
        expectancy_r=round((sum(rs) / len(rs)) if rs else 0.0, 4),
        profit_factor=round(profit_factor, 4),
        max_drawdown_pct=round(_drawdown_pct(bankroll_usdt, closed), 4),
        max_consecutive_losses=_max_loss_streak(closed),
        distinct_symbols=len({t.symbol for t in closed}),
        reentry_count=len(reentries),
        reentry_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in reentries), 4),
        reentry_expectancy_r=round((sum(reentry_rs) / len(reentry_rs)) if reentry_rs else 0.0, 4),
        avg_estimated_cost_r=round((sum(estimated_cost_rs) / len(estimated_cost_rs)) if estimated_cost_rs else 0.0, 4),
        high_cost_trade_count=high_cost_count,
        runner_count=len(runners),
        runner_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in runners), 4),
        by_symbol=_bucket(closed, "symbol"),
        by_strategy=_bucket(closed, "strategy_name"),
    )


def live_readiness(metrics: PerformanceMetrics, settings) -> dict:
    checks = {
        "sample_size": metrics.closed_count >= settings.risk_proven_min_trades,
        "expectancy": metrics.expectancy_r >= settings.risk_proven_min_expectancy_r,
        "profit_factor": metrics.profit_factor >= settings.risk_proven_min_profit_factor,
        "drawdown": metrics.max_drawdown_pct <= settings.risk_proven_max_drawdown_pct,
        "symbol_diversity": metrics.distinct_symbols >= settings.risk_proven_min_symbols,
        "reentry_not_bleeding": metrics.reentry_count == 0 or metrics.reentry_expectancy_r >= 0,
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "failed": [key for key, passed in checks.items() if not passed],
    }
