import pandas as pd

from agent.strategy.regime import detect_regime, Regime
from agent.strategy.trend import trend_signal
from agent.strategy.mean_reversion import mean_reversion_signal
from agent.strategy.signal import Signal, Side


def generate_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    """Regime-gated ensemble — all filters are soft except ATR shock.

    Layer order:
      1. ATR shock filter (hard-block during volatility spikes)
      2. Regime detection (trend vs mean-reversion) → TA signal
      3. Market context (structure bias + premium/discount → confidence penalties)
      4. SMC confidence boost (OB, FVG, liquidity sweep alignment)
    """

    # ------------------------------------------------------------------
    # 1. ATR shock filter — skip new entries during volatility spikes
    # ------------------------------------------------------------------
    atr_ratio = row.get("mc_atr_ratio")
    if atr_ratio is not None and pd.notna(atr_ratio):
        if atr_ratio > params.get("max_atr_ratio", 2.5):
            return Signal(
                Side.NONE, 0.0,
                reasoning=[f"ATR ratio {atr_ratio:.2f}× baseline — shock/event in progress, standing aside"],
                indicator_snapshot={"atr_ratio": atr_ratio},
                strategy_name="volatility_filter",
            )

    # ------------------------------------------------------------------
    # 2. Regime detection + TA signal
    # ------------------------------------------------------------------
    regime = detect_regime(row, params)
    if regime == Regime.TRENDING:
        signal = trend_signal(row, prev, params)
    else:
        signal = mean_reversion_signal(row, prev, params)

    signal.reasoning.insert(0, f"Regime: {regime.value} (ADX={row.get('adx', 0):.1f})")
    signal.indicator_snapshot["regime"] = regime.value

    if not signal.is_actionable:
        return signal

    # ------------------------------------------------------------------
    # 3. Market context — soft penalties (never hard-block)
    # ------------------------------------------------------------------
    structure_bias = row.get("mc_structure_bias")
    in_discount    = row.get("mc_in_discount")
    in_premium     = row.get("mc_in_premium")
    range_pos      = row.get("mc_range_position")

    ctx_penalty = 0.0
    if structure_bias is not None and pd.notna(structure_bias):
        if signal.side == Side.LONG and int(structure_bias) == -1:
            ctx_penalty += 0.15
            signal.reasoning.append("Structure bias BEARISH — confidence reduced (counter-trend)")
        if signal.side == Side.SHORT and int(structure_bias) == 1:
            ctx_penalty += 0.15
            signal.reasoning.append("Structure bias BULLISH — confidence reduced (counter-trend)")

    if in_premium is not None and pd.notna(in_premium):
        if signal.side == Side.LONG and bool(in_premium):
            ctx_penalty += 0.10
            signal.reasoning.append(f"Price in PREMIUM zone ({range_pos:.2f}) — unfavourable for longs")

    if in_discount is not None and pd.notna(in_discount):
        if signal.side == Side.SHORT and bool(in_discount):
            ctx_penalty += 0.10
            signal.reasoning.append(f"Price in DISCOUNT zone ({range_pos:.2f}) — unfavourable for shorts")

    signal.confidence = max(0.0, signal.confidence - ctx_penalty)

    # ------------------------------------------------------------------
    # 4. SMC confidence boost (soft filter — aligns, does not hard-block)
    # ------------------------------------------------------------------
    smc_boost   = 0.0
    smc_reasons = []

    if signal.side == Side.LONG:
        if row.get("smc_near_bull_ob", False):
            smc_boost += 0.10
            smc_reasons.append("Near bullish Order Block — institutional support level")
        if row.get("smc_fvg_bull", False):
            smc_boost += 0.05
            smc_reasons.append("Bullish FVG present in recent range")
        if row.get("smc_bull_sweep", False):
            smc_boost += 0.15
            smc_reasons.append("Bullish liquidity sweep — sell-side grabbed, reversal likely")

    if signal.side == Side.SHORT:
        if row.get("smc_near_bear_ob", False):
            smc_boost += 0.10
            smc_reasons.append("Near bearish Order Block — institutional resistance level")
        if row.get("smc_fvg_bear", False):
            smc_boost += 0.05
            smc_reasons.append("Bearish FVG present in recent range")
        if row.get("smc_bear_sweep", False):
            smc_boost += 0.15
            smc_reasons.append("Bearish liquidity sweep — buy-side grabbed, reversal likely")

    signal.confidence = min(signal.confidence + smc_boost, 1.0)
    signal.reasoning.extend(smc_reasons)
    signal.indicator_snapshot.update({
        "atr_ratio":       atr_ratio,
        "structure_bias":  structure_bias,
        "range_position":  range_pos,
        "smc_boost":       smc_boost,
    })

    return signal
