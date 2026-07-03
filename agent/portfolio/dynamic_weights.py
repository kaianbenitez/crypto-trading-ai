"""Daily dynamic ensemble weights from recent realized Sharpe."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

DEFAULT_WEIGHTS = {
    "smc": 0.30,
    "mean_reversion": 0.40,
    "momentum_kama": 0.20,
    "funding_basis": 0.10,
}


def _clamp_weights(weights: dict[str, float]) -> dict[str, float]:
    clamped = {k: max(0.10, min(0.50, v)) for k, v in weights.items()}
    total = sum(clamped.values()) or 1.0
    return {k: round(v / total, 4) for k, v in clamped.items()}


def _sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    stdev = math.sqrt(max(variance, 0.0))
    return mean / stdev if stdev > 0 else 0.0


def compute_dynamic_weights(session) -> tuple[dict[str, float], str]:
    from agent.db.models import Trade
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    trades = session.query(Trade).filter(Trade.closed_at >= cutoff, Trade.closed_at.isnot(None)).all()
    by_leg: dict[str, list[float]] = {k: [] for k in DEFAULT_WEIGHTS}
    for trade in trades:
        leg = trade.strategy_name if trade.strategy_name in by_leg else "smc"
        if trade.entry_price and trade.exit_price and trade.stop_loss:
            r = abs(trade.entry_price - trade.stop_loss)
            if r > 0:
                direction = 1 if trade.side == "long" else -1
                by_leg[leg].append(((trade.exit_price - trade.entry_price) * direction) / r)

    scores = {leg: max(0.0, _sharpe(rs)) for leg, rs in by_leg.items()}
    total = sum(scores.values())
    if total <= 0:
        return DEFAULT_WEIGHTS, "not enough positive 14d Sharpe; using defaults"
    raw = {leg: score / total for leg, score in scores.items()}
    return _clamp_weights(raw), f"14d Sharpe allocation from {len(trades)} closed trades: {json.dumps(scores)}"
