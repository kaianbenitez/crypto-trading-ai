"""Same-symbol re-entry rules to avoid fee/slippage churn."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from agent.strategy.signal import Signal


TP_EXIT_REASONS = {"take_profit", "trailing_take_profit"}


@dataclass
class ReentryDecision:
    allowed: bool
    reason: str
    elapsed_candles: int | None = None


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _snap_float(snapshot: dict, key: str, default: float = 0.0) -> float:
    try:
        value = snapshot.get(key, default)
        return float(value if value is not None else default)
    except Exception:
        return default


def evaluate_reentry(
    session: "Session",
    symbol: str,
    signal: "Signal",
    params: dict,
    now: datetime | None = None,
    timeframe_hours: float = 1.0,
) -> ReentryDecision:
    from agent.db.models import Trade

    last = (
        session.query(Trade)
        .filter(Trade.symbol == symbol, Trade.closed_at.isnot(None))
        .order_by(Trade.closed_at.desc())
        .first()
    )
    if not last:
        return ReentryDecision(True, "no prior closed trade for symbol")

    closed_at = _as_utc(last.closed_at)
    if closed_at is None:
        return ReentryDecision(True, "previous trade has no closed_at")

    now = _as_utc(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    max_daily_entries = int(params.get("reentry_max_trades_per_symbol_per_day", 3))
    if max_daily_entries > 0:
        entries_today = (
            session.query(Trade)
            .filter(Trade.symbol == symbol, Trade.opened_at >= day_start)
            .count()
        )
        if entries_today >= max_daily_entries:
            return ReentryDecision(
                False,
                f"daily same-symbol trade cap reached ({entries_today}/{max_daily_entries})",
                None,
            )

    candle_seconds = max(float(timeframe_hours), 0.1) * 3600
    elapsed = max(0, int((now - closed_at).total_seconds() // candle_seconds))
    exit_reason = (last.exit_reason or "").lower()

    if exit_reason in TP_EXIT_REASONS:
        cooldown = int(params.get("reentry_tp_cooldown_candles", 2))
        quality_window = int(params.get("reentry_tp_quality_window_candles", 8))
    elif exit_reason == "stop_loss":
        cooldown = int(params.get("reentry_sl_cooldown_candles", 4))
        quality_window = int(params.get("reentry_sl_quality_window_candles", 12))
    else:
        cooldown = int(params.get("reentry_other_cooldown_candles", 2))
        quality_window = cooldown

    if elapsed < cooldown:
        return ReentryDecision(
            False,
            f"same-symbol cooldown after {exit_reason or 'close'}: {elapsed}/{cooldown} candles elapsed",
            elapsed,
        )

    same_side = (last.side or "").lower() == signal.side.value.lower()
    if same_side and elapsed < quality_window:
        snap = last.get_indicator_snapshot()
        prev_ev = _snap_float(snap, "mtf_ev")
        curr_ev = _snap_float(signal.indicator_snapshot, "mtf_ev")
        prev_conf = _snap_float(snap, "confidence")
        curr_conf = float(signal.confidence or 0)
        prev_regime = str(snap.get("regime") or "")
        curr_regime = str(signal.indicator_snapshot.get("regime") or "")
        changed_context = (
            str(last.strategy_name or "") != str(signal.strategy_name or "")
            or (prev_regime and curr_regime and prev_regime != curr_regime)
        )

        min_ev_lift = float(params.get("reentry_min_ev_improvement_r", 0.25))
        min_conf_lift = float(params.get("reentry_min_conf_improvement", 0.08))
        min_ev_floor = float(params.get("min_ev_r", 0.25)) * float(params.get("reentry_min_ev_multiplier", 1.5))
        ev_ok = curr_ev >= prev_ev + min_ev_lift
        conf_ok = curr_conf >= prev_conf + min_conf_lift
        floor_ok = curr_ev >= min_ev_floor
        if not floor_ok or (not changed_context and not (ev_ok and conf_ok)):
            return ReentryDecision(
                False,
                (
                    f"same-side re-entry needs stronger setup for {quality_window} candles "
                    f"(EV {curr_ev:.2f}R vs {prev_ev:.2f}R, floor {min_ev_floor:.2f}R, "
                    f"conf {curr_conf:.2f} vs {prev_conf:.2f})"
                ),
                elapsed,
            )

    return ReentryDecision(True, f"re-entry allowed after {elapsed} candles", elapsed)
