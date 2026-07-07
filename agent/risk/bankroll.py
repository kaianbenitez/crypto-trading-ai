"""Equity-aware bankroll and risk-tier selection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent.db.models import RiskSnapshot
from agent.portfolio.performance import build_performance_metrics, leg_readiness, live_readiness


@dataclass
class RiskProfile:
    effective_bankroll_usdt: float
    configured_bankroll_usdt: float
    account_equity_usdt: float | None
    risk_pct: float
    tier: str
    mode: str
    drawdown_pct: float
    reason: str
    bankroll_divergence_pct: float | None = None


def _fetch_equity(adapter) -> float | None:
    if adapter is None:
        return None
    try:
        if hasattr(adapter, "get_account_equity"):
            return float(adapter.get_account_equity("USDT"))
        return float(adapter.get_balance("USDT"))
    except Exception:
        return None


def _bankroll_divergence_pct(configured: float, equity: float | None) -> float | None:
    """Fix 1: how far the configured bankroll and live exchange equity have
    drifted apart. Every %-based validation gate assumes these are roughly
    the same base; a large divergence means ROI%/drawdown% don't mean what
    they claim, independent of the per-trade normalization in performance.py."""
    if equity is None or equity <= 0 or configured <= 0:
        return None
    return abs(equity - configured) / configured * 100


def _get_or_set_validation_start(session) -> datetime:
    """First read sets the anchor; every read after that returns the same
    date, so the fixed 30-day window (Fix 5/9) doesn't reset itself. Local
    import to avoid agent/ depending on webapi/ at module load time (the
    reverse of the normal dependency direction) — same pattern already used
    for daily risk-state persistence in agent/orchestrator.py."""
    from webapi.app_state import get_or_create_state
    state = get_or_create_state(session)
    if state.validation_started_at is None:
        state.validation_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
    return state.validation_started_at


def _effective_bankroll(settings, account_equity: float | None) -> tuple[float, str]:
    configured = float(settings.bankroll_usdt)
    source = "configured"
    effective = configured

    if settings.bankroll_mode == "equity" and account_equity and account_equity > 0:
        source = "exchange_equity"
        if settings.bankroll_compounding:
            effective = account_equity
        else:
            effective = min(account_equity, configured)

    if settings.bankroll_max_usdt > 0:
        effective = min(effective, float(settings.bankroll_max_usdt))
    effective = max(effective, float(settings.bankroll_min_usdt))
    return effective, source


def choose_risk_tier(metrics, settings, days_elapsed: int | None = None) -> tuple[str, float, str]:
    ceiling = float(settings.max_risk_per_trade_pct)
    if settings.risk_tier_mode == "fixed":
        risk = min(ceiling, float(settings.risk_base_pct))
        return "fixed", risk, f"fixed risk tier at {risk:.2f}%"

    if metrics.max_drawdown_pct >= settings.risk_drawdown_trigger_pct:
        risk = min(ceiling, float(settings.risk_drawdown_pct))
        return "drawdown", risk, f"drawdown {metrics.max_drawdown_pct:.1f}% >= {settings.risk_drawdown_trigger_pct:.1f}%"

    # Fix 8: the loss-streak trigger is configurable (default 3, was a
    # hardcoded 2 — ~20% likely for a 55%+ win-rate system on pure variance,
    # which shrank size and distorted the very stats being validated).
    streak_trigger = int(getattr(settings, "risk_recovery_loss_streak_trigger", 2))
    if metrics.max_drawdown_pct >= settings.risk_recovery_drawdown_pct or metrics.max_consecutive_losses >= streak_trigger:
        risk = min(ceiling, float(settings.risk_recovery_pct))
        return "recovery", risk, f"recent drawdown/loss streak ({metrics.max_consecutive_losses}) requires smaller size"

    readiness = live_readiness(metrics, settings, days_elapsed=days_elapsed)
    if readiness["ready"]:
        risk = min(ceiling, float(settings.risk_proven_pct))
        return "proven", risk, "30d validation checks passed"

    risk = min(ceiling, float(settings.risk_base_pct))
    reason = "validation not mature enough for proven risk"
    if readiness["failed"]:
        reason += f" (blocked: {', '.join(readiness['failed'])})"
    return "normal", risk, reason


class BankrollManager:
    def __init__(self, settings):
        self.settings = settings

    def sync(self, session, adapter=None) -> RiskProfile:
        account_equity = _fetch_equity(adapter)
        effective_bankroll, mode_source = _effective_bankroll(self.settings, account_equity)
        divergence = _bankroll_divergence_pct(float(self.settings.bankroll_usdt), account_equity)
        if divergence is not None and divergence >= self.settings.bankroll_divergence_warn_pct:
            import logging
            logging.getLogger("agent").warning(
                f"Bankroll divergence {divergence:.1f}% — configured ${self.settings.bankroll_usdt:.2f} "
                f"vs live equity ${account_equity:.2f}. %-based validation gates assume these track "
                f"together; consider BANKROLL_MODE=equity or updating BANKROLL_USDT."
            )

        validation_start = _get_or_set_validation_start(session)
        days_elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - validation_start).days

        metrics = build_performance_metrics(session, effective_bankroll, days=30, settings=self.settings)
        tier, risk_pct, tier_reason = choose_risk_tier(metrics, self.settings, days_elapsed=days_elapsed)
        reason = f"{mode_source}; {tier_reason}"

        profile = RiskProfile(
            effective_bankroll_usdt=effective_bankroll,
            configured_bankroll_usdt=float(self.settings.bankroll_usdt),
            account_equity_usdt=account_equity,
            risk_pct=risk_pct,
            tier=tier,
            mode=self.settings.bankroll_mode,
            drawdown_pct=metrics.max_drawdown_pct,
            reason=reason,
            bankroll_divergence_pct=divergence,
        )
        session.add(RiskSnapshot(
            effective_bankroll_usdt=profile.effective_bankroll_usdt,
            configured_bankroll_usdt=profile.configured_bankroll_usdt,
            account_equity_usdt=profile.account_equity_usdt,
            risk_pct=profile.risk_pct,
            tier=profile.tier,
            mode=profile.mode,
            drawdown_pct=profile.drawdown_pct,
            reason=profile.reason,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        session.commit()
        return profile


def latest_risk_snapshot(session, settings) -> dict:
    row = session.query(RiskSnapshot).order_by(RiskSnapshot.created_at.desc()).first()

    validation_start = _get_or_set_validation_start(session)
    days_elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - validation_start).days
    days_remaining = max(0, int(settings.risk_proven_min_days) - days_elapsed)

    bankroll = float(settings.bankroll_usdt)
    metrics = build_performance_metrics(session, bankroll, days=30, settings=settings)
    metrics_fixed_window = build_performance_metrics(session, bankroll, since=validation_start, settings=settings)
    readiness = live_readiness(metrics, settings, days_elapsed=days_elapsed)
    readiness_fixed_window = live_readiness(metrics_fixed_window, settings, days_elapsed=days_elapsed)
    legs = leg_readiness(session, bankroll, settings, since=validation_start)
    leg_summary = {
        key: {"closed_count": v["metrics"].closed_count, "ready": v["readiness"]["ready"], "failed": v["readiness"]["failed"]}
        for key, v in legs.items()
    }
    validation_meta = {
        "validation_started_at": validation_start,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "min_days_required": int(settings.risk_proven_min_days),
        "leg_readiness": leg_summary,
    }

    if not row:
        tier, risk_pct, reason = choose_risk_tier(metrics, settings, days_elapsed=days_elapsed)
        return {
            "effective_bankroll_usdt": settings.bankroll_usdt,
            "configured_bankroll_usdt": settings.bankroll_usdt,
            "account_equity_usdt": None,
            "bankroll_divergence_pct": None,
            "risk_pct": risk_pct,
            "tier": tier,
            "mode": settings.bankroll_mode,
            "drawdown_pct": metrics.max_drawdown_pct,
            "reason": reason,
            "created_at": None,
            "metrics": metrics,
            "metrics_fixed_window": metrics_fixed_window,
            "readiness": readiness,
            "readiness_fixed_window": readiness_fixed_window,
            "validation": validation_meta,
        }
    return {
        "effective_bankroll_usdt": row.effective_bankroll_usdt,
        "configured_bankroll_usdt": row.configured_bankroll_usdt,
        "account_equity_usdt": row.account_equity_usdt,
        "bankroll_divergence_pct": _bankroll_divergence_pct(row.configured_bankroll_usdt, row.account_equity_usdt),
        "risk_pct": row.risk_pct,
        "tier": row.tier,
        "mode": row.mode,
        "drawdown_pct": row.drawdown_pct,
        "reason": row.reason,
        "created_at": row.created_at,
        "metrics": metrics,
        "metrics_fixed_window": metrics_fixed_window,
        "readiness": readiness,
        "readiness_fixed_window": readiness_fixed_window,
        "validation": validation_meta,
    }

