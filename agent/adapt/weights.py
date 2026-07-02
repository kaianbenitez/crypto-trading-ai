"""Adaptive indicator weight engine — per-symbol, per-regime.

Each symbol maintains its own weight vector across indicators.
After every closed trade, indicators that fired correctly get boosted,
indicators that fired incorrectly get penalised.

Weights influence signal confidence in ensemble.py — they do NOT change
strategy logic or which indicators are checked. They are a learned
multiplier on top of the existing signal stack.

Weight storage: SQLite via IndicatorWeight model.
Weight update: called from orchestrator after every trade close.
Weight apply: called from ensemble.py before returning signal.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.db.models import Trade

# All trackable indicators
INDICATORS = [
    "ema_cross",
    "macd",
    "rsi",
    "adx",
    "bb",
    "structure_bias",
    "zone",          # premium/discount
    "smc_ob",        # order block
    "smc_fvg",       # fair value gap
    "smc_sweep",     # liquidity sweep
    "volume",
    "atr",
]

# Regime labels
REGIMES = ["trending", "ranging", "unknown"]

# Learning rate — how fast weights shift per trade
LEARN_RATE = 0.08

# Weight bounds — never let any indicator fully dominate or disappear
WEIGHT_MIN = 0.20
WEIGHT_MAX = 2.50

# Default weight for all indicators (neutral)
DEFAULT_WEIGHT = 1.0

# Minimum trades before weights start shifting
MIN_TRADES = 5


def _default_weights() -> dict:
    return {ind: DEFAULT_WEIGHT for ind in INDICATORS}


def load_weights(symbol: str, regime: str, session) -> dict:
    """Load weights for a symbol+regime. Returns defaults if none stored."""
    from agent.db.models import IndicatorWeight
    record = (
        session.query(IndicatorWeight)
        .filter(IndicatorWeight.symbol == symbol, IndicatorWeight.regime == regime)
        .first()
    )
    if not record:
        return _default_weights()
    try:
        w = json.loads(record.weights)
        # Ensure all indicators present (handles new indicators added later)
        defaults = _default_weights()
        defaults.update(w)
        return defaults
    except Exception:
        return _default_weights()


def save_weights(symbol: str, regime: str, weights: dict, session) -> None:
    """Persist weights for a symbol+regime."""
    from agent.db.models import IndicatorWeight
    record = (
        session.query(IndicatorWeight)
        .filter(IndicatorWeight.symbol == symbol, IndicatorWeight.regime == regime)
        .first()
    )
    if record:
        record.weights = json.dumps(weights)
    else:
        session.add(IndicatorWeight(
            symbol=symbol,
            regime=regime,
            weights=json.dumps(weights),
            trade_count=0,
        ))
    session.commit()


def _clamp(v: float) -> float:
    return max(WEIGHT_MIN, min(WEIGHT_MAX, v))


def update_weights(trade: "Trade", session) -> dict:
    """Update indicator weights after a closed trade.

    Reads the indicator snapshot stored at entry, determines which
    indicators fired, then nudges weights based on outcome.

    Returns the updated weight dict.
    """
    try:
        snap = json.loads(trade.indicator_snapshot or "{}")
    except Exception:
        snap = {}

    regime = trade.regime or snap.get("regime", "unknown")
    outcome = trade.outcome or "unknown"
    won = outcome == "win"

    # Load current weights
    weights = load_weights(trade.symbol, regime, session)

    # Determine which indicators fired at entry
    fired: dict[str, bool] = {
        "ema_cross":      bool(snap.get("ema_cross_bull") or snap.get("ema_cross_bear")),
        "macd":           bool(snap.get("macd_bull") or snap.get("macd_bear")),
        "rsi":            bool(snap.get("rsi_oversold") or snap.get("rsi_overbought")),
        "adx":            bool(snap.get("adx", 0) >= 20),
        "bb":             bool(snap.get("bb_lower_touch") or snap.get("bb_upper_touch")),
        "structure_bias": bool(snap.get("structure_bias") is not None),
        "zone":           bool(snap.get("range_position") is not None),
        "smc_ob":         bool(snap.get("smc_boost", 0) > 0 and (
                              snap.get("smc_near_bull_ob") or snap.get("smc_near_bear_ob"))),
        "smc_fvg":        bool(snap.get("smc_fvg_bull") or snap.get("smc_fvg_bear")),
        "smc_sweep":      bool(snap.get("smc_bull_sweep") or snap.get("smc_bear_sweep")),
        "volume":         bool(snap.get("volume_confirm")),
        "atr":            bool(snap.get("atr_ratio") is not None),
    }

    # Nudge weights
    for ind, did_fire in fired.items():
        if not did_fire:
            continue  # indicator wasn't active — no update
        current = weights.get(ind, DEFAULT_WEIGHT)
        if won:
            weights[ind] = _clamp(current * (1 + LEARN_RATE))
        else:
            weights[ind] = _clamp(current * (1 - LEARN_RATE))

    save_weights(trade.symbol, regime, weights, session)

    # Update trade count
    from agent.db.models import IndicatorWeight
    record = (
        session.query(IndicatorWeight)
        .filter(IndicatorWeight.symbol == trade.symbol, IndicatorWeight.regime == regime)
        .first()
    )
    if record:
        record.trade_count = (record.trade_count or 0) + 1
        session.commit()

    return weights


def apply_weights(signal, row, symbol: str, session) -> float:
    """Return a confidence delta based on learned indicator weights.

    Called from orchestrator before entry — reads current weights for
    this symbol+regime and computes a weighted confidence adjustment.
    """
    try:
        regime = str(row.get("regime", row.get("mc_structure_bias", "unknown")))
        if regime not in REGIMES:
            regime = "unknown"

        weights = load_weights(symbol, regime, session)

        # Check if we have enough data to trust weights
        from agent.db.models import IndicatorWeight
        record = (
            session.query(IndicatorWeight)
            .filter(IndicatorWeight.symbol == symbol, IndicatorWeight.regime == regime)
            .first()
        )
        if not record or (record.trade_count or 0) < MIN_TRADES:
            return 0.0  # not enough data yet — neutral

        # Score each active indicator by its learned weight
        weight_sum = 0.0
        active_count = 0

        snap = signal.indicator_snapshot

        checks = {
            "ema_cross":      snap.get("ema_cross_bull") or snap.get("ema_cross_bear"),
            "macd":           snap.get("macd_bull") or snap.get("macd_bear"),
            "rsi":            snap.get("rsi_oversold") or snap.get("rsi_overbought"),
            "adx":            (snap.get("adx", 0) or 0) >= 20,
            "bb":             snap.get("bb_lower_touch") or snap.get("bb_upper_touch"),
            "structure_bias": snap.get("structure_bias") is not None,
            "zone":           snap.get("range_position") is not None,
            "smc_ob":         snap.get("smc_near_bull_ob") or snap.get("smc_near_bear_ob"),
            "smc_fvg":        snap.get("smc_fvg_bull") or snap.get("smc_fvg_bear"),
            "smc_sweep":      snap.get("smc_bull_sweep") or snap.get("smc_bear_sweep"),
            "volume":         snap.get("volume_confirm"),
            "atr":            snap.get("atr_ratio") is not None,
        }

        for ind, active in checks.items():
            if active:
                weight_sum += weights.get(ind, DEFAULT_WEIGHT)
                active_count += 1

        if active_count == 0:
            return 0.0

        avg_weight = weight_sum / active_count
        # Convert avg weight to confidence delta: weight=1.0 → 0 delta
        # weight=2.0 → +0.10, weight=0.5 → -0.10
        delta = (avg_weight - 1.0) * 0.10
        return max(-0.20, min(0.20, delta))

    except Exception:
        return 0.0
