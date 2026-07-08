"""Bounded parameter auto-tuner.

Hard rule: this module may ONLY adjust numeric values inside PARAM_BOUNDS.
It must never modify strategy logic, add/remove rules, or change code.
Adjustments are nudges (small steps) based on rolling trade stats, not a
single trade's outcome, to avoid overfitting to noise.
"""

from agent.db.models import Trade

PARAM_BOUNDS = {
    "atr_mult_sl": (1.0, 3.0),
    "atr_mult_tp": (1.5, 5.0),
    "rsi_oversold": (15, 35),
    "rsi_overbought": (65, 85),
    "adx_trend_threshold": (18, 35),
    "vol_confirm_mult": (0.8, 1.5),
    "max_risk_per_trade_pct": (0.5, 2.0),  # never exceeds user-configured ceiling either
}

STEP = 0.05  # 5% nudge per adjustment, applied multiplicatively
MIN_SAMPLE_SIZE = 10  # don't tune until we have enough closed trades to trust the signal


def _clamp(value: float, key: str) -> float:
    lo, hi = PARAM_BOUNDS[key]
    return max(lo, min(hi, value))


def tune_parameters(recent_trades: list[Trade], current_params: dict) -> dict:
    """Returns a new params dict. Only called with a rolling window (e.g. last
    20-30 closed trades) — never reacts to a single trade in isolation."""
    if len(recent_trades) < MIN_SAMPLE_SIZE:
        return current_params

    new_params = dict(current_params)

    losses = [t for t in recent_trades if t.outcome == "loss"]
    wins = [t for t in recent_trades if t.outcome == "win"]
    win_rate = len(wins) / len(recent_trades) if recent_trades else 0

    sl_hit_losses = [t for t in losses if t.exit_reason in ("stop_loss", "trailing_stop")]
    sl_hit_ratio = len(sl_hit_losses) / len(recent_trades) if recent_trades else 0

    # Stops getting hit too often relative to overall sample -> widen SL distance
    if sl_hit_ratio > 0.35:
        key = "atr_mult_sl"
        new_params[key] = _clamp(new_params.get(key, 1.5) * (1 + STEP), key)

    # Win rate healthy and stops rarely hit -> can afford tighter risk-adjusted stops
    # for better reward:risk, nudge TP multiple up slightly
    if win_rate > 0.55 and sl_hit_ratio < 0.2:
        key = "atr_mult_tp"
        new_params[key] = _clamp(new_params.get(key, 3.0) * (1 + STEP), key)

    # Weak overall win rate -> tighten volume confirmation to reduce false signals
    if win_rate < 0.4:
        key = "vol_confirm_mult"
        new_params[key] = _clamp(new_params.get(key, 1.0) * (1 + STEP), key)

        # also trim risk per trade while win rate is below target
        key2 = "max_risk_per_trade_pct"
        new_params[key2] = _clamp(new_params.get(key2, 1.5) * (1 - STEP), key2)

    # Strong win rate -> can afford to size back up toward (but not above) the ceiling
    if win_rate > 0.6:
        key2 = "max_risk_per_trade_pct"
        new_params[key2] = _clamp(new_params.get(key2, 1.5) * (1 + STEP), key2)

    return new_params


def diff_params(old: dict, new: dict) -> list[str]:
    changes = []
    for key, new_val in new.items():
        old_val = old.get(key)
        if old_val is not None and abs(old_val - new_val) > 1e-9:
            changes.append(f"{key}: {old_val:.4f} -> {new_val:.4f}")
    return changes
