"""Portfolio performance metrics for validation and risk tiers.

Bankroll consistency note (Fix 1): ROI%/drawdown% are computed by normalizing
each trade's P&L against the bankroll actually snapshotted on THAT trade
(indicator_snapshot["effective_bankroll_usdt"]), not one global static number.
A history sized on mixed bankrolls (e.g. testnet equity drifting from $1,000
to $5,000) is otherwise reported as if every dollar of P&L came from the same
capital base, which silently inflates ROI% and distorts every %-based gate.
Where a trade predates that snapshot, it falls back to the bankroll_usdt this
function was called with, and the fallback count is reported so that's visible
rather than silent.

Drawdown note (Fix 10): max_drawdown_pct walks a normalized percentage-point
equity curve built from CLOSED trades only (peak-to-trough in the same
bankroll-normalized % space as ROI). It does not include unrealized excursion
on currently open positions — build_performance_metrics has no live mark
price, so it can't compute true open drawdown. `open_risk_usdt` is reported as
a rough proxy (capital currently at stake on open trades) so a deep open hole
isn't invisible, but it is NOT the same as live unrealized drawdown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Iterable

from agent.db.models import Trade

# Exit reasons that mark a manual/duplicate-fix close rather than a real
# strategy signal outcome — excluded from clean validation metrics (Fix 7).
_RECONCILIATION_MARKERS = ("reconcile", "manual", "duplicate")


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
    avg_net_r_after_estimated_cost: float = 0.0
    expectancy_after_estimated_cost_r: float = 0.0
    tiny_win_count: int = 0
    runner_count: int = 0
    runner_pnl_usdt: float = 0.0
    exit_reason_breakdown: dict[str, int] = field(default_factory=dict)
    by_symbol: dict[str, dict] = field(default_factory=dict)
    by_strategy: dict[str, dict] = field(default_factory=dict)

    # --- Fix 1: bankroll consistency ---
    trades_missing_bankroll_snapshot: int = 0

    # --- Fix 4: concentration by contribution, not coin count ---
    pnl_excluding_best_coin: float = 0.0
    pnl_excluding_top2_coins: float = 0.0
    pnl_excluding_best_trade: float = 0.0
    top_coin_contribution_pct: float = 0.0
    top3_trades_contribution_pct: float = 0.0
    concentration_pass: bool = False
    concentration_reason: str = ""

    # --- Fix 5: regime/leg mix visibility ---
    by_regime: dict[str, dict] = field(default_factory=dict)
    by_side: dict[str, dict] = field(default_factory=dict)

    # --- Fix 7: reconciliation exclusion (reported separately) ---
    gross_closed_count: int = 0
    gross_pnl_usdt: float = 0.0
    reconciliation_count: int = 0
    reconciliation_pnl_usdt: float = 0.0

    # --- Fix 10: open-position exposure proxy (not true unrealized drawdown) ---
    open_risk_usdt: float = 0.0


def _as_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _is_reconciliation(trade: Trade) -> bool:
    reason = (trade.exit_reason or "").lower()
    return any(marker in reason for marker in _RECONCILIATION_MARKERS)


def _trade_bankroll(trade: Trade, fallback_bankroll: float) -> tuple[float, bool]:
    """Bankroll to normalize this trade's % contribution against: the bankroll
    actually snapshotted at entry, falling back to the caller's bankroll_usdt
    (and flagging it) if the trade predates that snapshot."""
    try:
        snap = trade.get_indicator_snapshot()
        b = float(snap.get("effective_bankroll_usdt") or 0)
    except Exception:
        b = 0.0
    if b > 0:
        return b, False
    return float(fallback_bankroll or 0.0), True


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


def _roi_and_drawdown(closed: list[Trade], fallback_bankroll: float) -> tuple[float, float, int]:
    """Bankroll-normalized ROI% (sum of each trade's own pnl/its-snapshotted-
    bankroll) and max drawdown walked in that same normalized percentage-point
    space, starting from 100.0. Returns (roi_pct, max_drawdown_pct,
    trades_missing_snapshot_count)."""
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    roi_pct = 0.0
    missing = 0
    for trade in closed:
        bankroll, used_fallback = _trade_bankroll(trade, fallback_bankroll)
        if used_fallback:
            missing += 1
        if bankroll <= 0:
            continue
        contrib_pct = float(trade.pnl_usdt or 0) / bankroll * 100
        roi_pct += contrib_pct
        equity += contrib_pct
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)
    return roi_pct, max_dd, missing


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


def _concentration(closed: list[Trade], by_symbol: dict[str, dict], total_pnl: float, max_top_coin_pct: float) -> tuple[float, float, float, float, float, bool, str]:
    """Fix 4: concentration measured by CONTRIBUTION, not coin count. A bot
    trading 9 coins where one coin's P&L exceeds the whole account's total
    (i.e. every other coin is net-negative) must fail this, even though a
    naive "distinct_symbols >= 3" check would pass it."""
    if not closed or not by_symbol:
        return 0.0, 0.0, 0.0, 0.0, 0.0, False, "no closed trades yet"

    coin_pnls = sorted((row["pnl"] for row in by_symbol.values()), reverse=True)
    best_coin_pnl = coin_pnls[0]
    top2_pnl = sum(coin_pnls[:2])
    pnl_ex_best_coin = round(total_pnl - best_coin_pnl, 4)
    pnl_ex_top2 = round(total_pnl - top2_pnl, 4)

    trade_pnls = sorted((float(t.pnl_usdt or 0) for t in closed), reverse=True)
    best_trade_pnl = trade_pnls[0] if trade_pnls else 0.0
    top3_trade_pnl = sum(trade_pnls[:3])
    pnl_ex_best_trade = round(total_pnl - best_trade_pnl, 4)

    if total_pnl > 0:
        top_coin_pct = round(best_coin_pnl / total_pnl * 100, 2)
        top3_trades_pct = round(top3_trade_pnl / total_pnl * 100, 2)
    else:
        top_coin_pct = 0.0
        top3_trades_pct = 0.0

    reasons = []
    if total_pnl <= 0:
        reasons.append("total P&L is not positive")
    if pnl_ex_best_coin <= 0:
        reasons.append(f"P&L excluding best coin is {pnl_ex_best_coin:+.2f} (not positive without it)")
    if total_pnl > 0 and top_coin_pct > max_top_coin_pct:
        reasons.append(f"top coin is {top_coin_pct:.0f}% of net P&L (max {max_top_coin_pct:.0f}%)")

    passed = len(reasons) == 0
    reason = "passes concentration checks" if passed else "; ".join(reasons)
    return pnl_ex_best_coin, pnl_ex_top2, pnl_ex_best_trade, top_coin_pct, top3_trades_pct, passed, reason


def _compute_metrics_from_trades(all_trades: list[Trade], bankroll_usdt: float, days: int, settings=None) -> PerformanceMetrics:
    """Core computation over an already-time-filtered trade list. Shared by
    the rolling-window, fixed-window, and per-leg call sites so the logic
    (including reconciliation exclusion and concentration) lives in one place."""
    open_count = len([t for t in all_trades if t.closed_at is None])
    gross_closed = [t for t in all_trades if t.closed_at is not None]
    reconciliation_trades = [t for t in gross_closed if _is_reconciliation(t)]
    closed = [t for t in gross_closed if not _is_reconciliation(t)]  # clean, drives every metric below

    open_trades = [t for t in all_trades if t.closed_at is None]
    open_risk_usdt = 0.0
    for t in open_trades:
        try:
            snap = t.get_indicator_snapshot()
            open_risk_usdt += float(snap.get("actual_risk_usdt") or snap.get("planned_risk_usdt") or 0.0)
        except Exception:
            pass

    pnl = sum(float(t.pnl_usdt or 0) for t in closed)
    wins = [t for t in closed if (t.pnl_usdt or 0) > 0]
    losses = [t for t in closed if (t.pnl_usdt or 0) < 0]
    rs = [r_multiple(t) for t in closed]
    gross_win = sum(float(t.pnl_usdt or 0) for t in wins)
    gross_loss = abs(sum(float(t.pnl_usdt or 0) for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    if not isfinite(profit_factor):
        profit_factor = 999.0

    roi_pct, max_dd, missing_bankroll_count = _roi_and_drawdown(closed, bankroll_usdt)

    reentry_ids = _mark_reentries(closed)
    reentries = [t for t in closed if t.id in reentry_ids]
    reentry_rs = [r_multiple(t) for t in reentries]
    estimated_cost_rs = []
    net_r_after_cost_list = []
    high_cost_count = 0
    tiny_win_count = 0
    runners = []
    exit_reason_breakdown: dict[str, int] = {}
    for trade in closed:
        snap = trade.get_indicator_snapshot()
        try:
            cost_r = float(snap.get("estimated_cost_r") or 0.0)
        except Exception:
            cost_r = 0.0
        realized_r = r_multiple(trade)
        if cost_r > 0:
            estimated_cost_rs.append(cost_r)
            net_r_after_cost_list.append(realized_r - cost_r)
            if abs(realized_r) > 0 and cost_r / abs(realized_r) >= 0.2:
                high_cost_count += 1
        else:
            net_r_after_cost_list.append(realized_r)
        if 0 < realized_r < 0.5:
            tiny_win_count += 1
        if trade.exit_reason == "trailing_take_profit":
            runners.append(trade)

        reason = (trade.exit_reason or "other").lower()
        if reason == "take_profit":
            bucket = "take_profit"
        elif reason == "stop_loss":
            bucket = "stop_loss"
        elif reason == "trailing_take_profit":
            bucket = "trailing_take_profit"
        elif reason == "trailing_stop":
            bucket = "trailing_stop"
        elif reason == "max_hold_timeout":
            bucket = "max_hold_timeout"
        elif "manual" in reason:
            bucket = "manual"
        else:
            bucket = "other"
        exit_reason_breakdown[bucket] = exit_reason_breakdown.get(bucket, 0) + 1

    by_symbol = _bucket(closed, "symbol")
    pnl_ex_best_coin, pnl_ex_top2, pnl_ex_best_trade, top_coin_pct, top3_trades_pct, conc_pass, conc_reason = _concentration(
        closed, by_symbol, pnl, float(getattr(settings, "risk_proven_max_top_coin_pct", 50.0) if settings else 50.0)
    )

    return PerformanceMetrics(
        days=days,
        bankroll_usdt=bankroll_usdt,
        trade_count=len(all_trades),
        closed_count=len(closed),
        open_count=open_count,
        total_pnl_usdt=round(pnl, 4),
        roi_pct=round(roi_pct, 4),
        win_rate_pct=round((len(wins) / len(closed) * 100) if closed else 0.0, 2),
        expectancy_r=round((sum(rs) / len(rs)) if rs else 0.0, 4),
        profit_factor=round(profit_factor, 4),
        max_drawdown_pct=round(max_dd, 4),
        max_consecutive_losses=_max_loss_streak(closed),
        distinct_symbols=len({t.symbol for t in closed}),
        reentry_count=len(reentries),
        reentry_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in reentries), 4),
        reentry_expectancy_r=round((sum(reentry_rs) / len(reentry_rs)) if reentry_rs else 0.0, 4),
        avg_estimated_cost_r=round((sum(estimated_cost_rs) / len(estimated_cost_rs)) if estimated_cost_rs else 0.0, 4),
        high_cost_trade_count=high_cost_count,
        avg_net_r_after_estimated_cost=round(
            (sum(net_r_after_cost_list) / len(net_r_after_cost_list)) if net_r_after_cost_list else 0.0, 4
        ),
        expectancy_after_estimated_cost_r=round(
            (sum(net_r_after_cost_list) / len(net_r_after_cost_list)) if net_r_after_cost_list else 0.0, 4
        ),
        tiny_win_count=tiny_win_count,
        runner_count=len(runners),
        runner_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in runners), 4),
        exit_reason_breakdown=exit_reason_breakdown,
        by_symbol=by_symbol,
        by_strategy=_bucket(closed, "strategy_name"),
        trades_missing_bankroll_snapshot=missing_bankroll_count,
        pnl_excluding_best_coin=pnl_ex_best_coin,
        pnl_excluding_top2_coins=pnl_ex_top2,
        pnl_excluding_best_trade=pnl_ex_best_trade,
        top_coin_contribution_pct=top_coin_pct,
        top3_trades_contribution_pct=top3_trades_pct,
        concentration_pass=conc_pass,
        concentration_reason=conc_reason,
        by_regime=_bucket(closed, "regime"),
        by_side=_bucket(closed, "side"),
        gross_closed_count=len(gross_closed),
        gross_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in gross_closed), 4),
        reconciliation_count=len(reconciliation_trades),
        reconciliation_pnl_usdt=round(sum(float(t.pnl_usdt or 0) for t in reconciliation_trades), 4),
        open_risk_usdt=round(open_risk_usdt, 4),
    )


def build_performance_metrics(
    session, bankroll_usdt: float, days: int = 30, since: datetime | None = None, settings=None,
) -> PerformanceMetrics:
    """Rolling window by default (last `days`); pass `since` for a fixed
    window anchored to a specific start (Fix 9 — e.g. the validation start
    date), so "proven" status can't silently decay just because a rolling
    window's trade count dropped after a quiet week."""
    cutoff = _as_utc_naive(since) if since is not None else (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    )
    trades = session.query(Trade).filter(Trade.opened_at >= cutoff).order_by(Trade.opened_at.asc()).all()
    return _compute_metrics_from_trades(trades, bankroll_usdt, days, settings)


def leg_readiness(session, bankroll_usdt: float, settings, days: int = 30, since: datetime | None = None) -> dict[str, dict]:
    """Fix 6: separate validation per (strategy_name, regime) leg. A proven
    trend_following/trending track record must NOT promote sizing for
    mean_reversion/ranging, which needs its own sample and its own
    cost-adjusted expectancy."""
    cutoff = _as_utc_naive(since) if since is not None else (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    )
    trades = session.query(Trade).filter(Trade.opened_at >= cutoff).order_by(Trade.opened_at.asc()).all()

    legs: dict[str, list[Trade]] = {}
    for t in trades:
        key = f"{t.strategy_name or 'unknown'}/{t.regime or 'unknown'}"
        legs.setdefault(key, []).append(t)

    out: dict[str, dict] = {}
    min_trades_per_leg = int(getattr(settings, "risk_proven_min_trades_per_leg", 30))
    for key, leg_trades in legs.items():
        metrics = _compute_metrics_from_trades(leg_trades, bankroll_usdt, days, settings)
        readiness = live_readiness(metrics, settings, min_trades_override=min_trades_per_leg)
        out[key] = {"metrics": metrics, "readiness": readiness}
    return out


def live_readiness(metrics: PerformanceMetrics, settings, days_elapsed: int | None = None, min_trades_override: int | None = None) -> dict:
    """Promotion gate. `days_elapsed` (Fix 5) and `min_trades_override` (Fix 6,
    used by leg_readiness) are optional so existing callers keep working."""
    min_trades = min_trades_override if min_trades_override is not None else settings.risk_proven_min_trades

    checks = {
        "sample_size": metrics.closed_count >= min_trades,
        "expectancy": metrics.expectancy_r >= settings.risk_proven_min_expectancy_r,
        # Fix 3: raw expectancy must exceed the measured cost per trade, or
        # clearing the raw floor doesn't actually mean there's an edge.
        "expectancy_above_cost": metrics.avg_estimated_cost_r <= 0 or metrics.expectancy_r > metrics.avg_estimated_cost_r,
        # Fix 2: the primary expectancy gate is cost-adjusted, not raw.
        "cost_adjusted_expectancy": metrics.avg_net_r_after_estimated_cost >= settings.risk_proven_min_net_r_after_cost,
        "profit_factor": metrics.profit_factor >= settings.risk_proven_min_profit_factor,
        "drawdown": metrics.max_drawdown_pct <= settings.risk_proven_max_drawdown_pct,
        "symbol_diversity": metrics.distinct_symbols >= settings.risk_proven_min_symbols,
        # Fix 4: replaces "coin count" with "coin contribution."
        "concentration": metrics.concentration_pass,
        "reentry_not_bleeding": metrics.reentry_count == 0 or metrics.reentry_expectancy_r >= 0,
    }
    if days_elapsed is not None:
        # Fix 5: N trades in one lucky week can't promote.
        checks["calendar_time"] = days_elapsed >= settings.risk_proven_min_days

    return {
        "ready": all(checks.values()),
        "checks": checks,
        "failed": [key for key, passed in checks.items() if not passed],
        "concentration_reason": metrics.concentration_reason,
    }
