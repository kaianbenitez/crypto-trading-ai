"""Equity-aware bankroll and risk-tier selection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent.db.models import RiskSnapshot
from agent.portfolio.performance import build_performance_metrics, live_readiness


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


def _fetch_equity(adapter) -> float | None:
    if adapter is None:
        return None
    try:
        if hasattr(adapter, "get_account_equity"):
            return float(adapter.get_account_equity("USDT"))
        return float(adapter.get_balance("USDT"))
    except Exception:
        return None


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


def choose_risk_tier(metrics, settings) -> tuple[str, float, str]:
    ceiling = float(settings.max_risk_per_trade_pct)
    if settings.risk_tier_mode == "fixed":
        risk = min(ceiling, float(settings.risk_base_pct))
        return "fixed", risk, f"fixed risk tier at {risk:.2f}%"

    if metrics.max_drawdown_pct >= settings.risk_drawdown_trigger_pct:
        risk = min(ceiling, float(settings.risk_drawdown_pct))
        return "drawdown", risk, f"drawdown {metrics.max_drawdown_pct:.1f}% >= {settings.risk_drawdown_trigger_pct:.1f}%"

    if metrics.max_drawdown_pct >= settings.risk_recovery_drawdown_pct or metrics.max_consecutive_losses >= 2:
        risk = min(ceiling, float(settings.risk_recovery_pct))
        return "recovery", risk, "recent drawdown/loss streak requires smaller size"

    readiness = live_readiness(metrics, settings)
    if readiness["ready"]:
        risk = min(ceiling, float(settings.risk_proven_pct))
        return "proven", risk, "30d validation checks passed"

    risk = min(ceiling, float(settings.risk_base_pct))
    return "normal", risk, "validation not mature enough for proven risk"


class BankrollManager:
    def __init__(self, settings):
        self.settings = settings

    def sync(self, session, adapter=None) -> RiskProfile:
        account_equity = _fetch_equity(adapter)
        effective_bankroll, mode_source = _effective_bankroll(self.settings, account_equity)
        metrics = build_performance_metrics(session, effective_bankroll, days=30)
        tier, risk_pct, tier_reason = choose_risk_tier(metrics, self.settings)
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
    metrics = build_performance_metrics(session, float(settings.bankroll_usdt), days=30)
    readiness = live_readiness(metrics, settings)
    if not row:
        tier, risk_pct, reason = choose_risk_tier(metrics, settings)
        return {
            "effective_bankroll_usdt": settings.bankroll_usdt,
            "configured_bankroll_usdt": settings.bankroll_usdt,
            "account_equity_usdt": None,
            "risk_pct": risk_pct,
            "tier": tier,
            "mode": settings.bankroll_mode,
            "drawdown_pct": metrics.max_drawdown_pct,
            "reason": reason,
            "created_at": None,
            "metrics": metrics,
            "readiness": readiness,
        }
    return {
        "effective_bankroll_usdt": row.effective_bankroll_usdt,
        "configured_bankroll_usdt": row.configured_bankroll_usdt,
        "account_equity_usdt": row.account_equity_usdt,
        "risk_pct": row.risk_pct,
        "tier": row.tier,
        "mode": row.mode,
        "drawdown_pct": row.drawdown_pct,
        "reason": row.reason,
        "created_at": row.created_at,
        "metrics": metrics,
        "readiness": readiness,
    }

