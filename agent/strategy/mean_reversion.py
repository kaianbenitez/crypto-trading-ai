import pandas as pd

from agent.strategy.signal import Signal, Side


def mean_reversion_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    """RSI extremes OR Bollinger Band touch — either is sufficient.

    Two tiers:
      - Both RSI extreme + BB touch (0.65): strongest mean-reversion setup
      - RSI extreme only OR BB touch only (0.45): weaker but still actionable
    """
    rsi_oversold = params.get("rsi_oversold", 35)
    rsi_overbought = params.get("rsi_overbought", 65)

    snapshot = {
        "rsi": row.get("rsi"), "bb_upper": row.get("bb_upper"), "bb_lower": row.get("bb_lower"),
        "close": row.get("close"), "vol_confirmed": row.get("vol_confirmed"),
    }

    rsi = float(row.get("rsi", 50))
    close = float(row.get("close", 0))
    bb_lower = float(row.get("bb_lower", 0))
    bb_upper = float(row.get("bb_upper", 0))

    rsi_long  = rsi <= rsi_oversold
    bb_long   = close <= bb_lower and bb_lower > 0
    rsi_short = rsi >= rsi_overbought
    bb_short  = close >= bb_upper and bb_upper > 0

    # --- LONG setups ---
    if rsi_long and bb_long:
        return Signal(
            Side.LONG, confidence=0.65,
            reasoning=[
                f"RSI ({rsi:.1f}) oversold + price at lower BB — strong mean-reversion setup",
            ],
            indicator_snapshot=snapshot, strategy_name="mean_reversion",
        )
    if rsi_long or bb_long:
        reason = f"RSI ({rsi:.1f}) oversold" if rsi_long else f"Price at lower Bollinger Band"
        return Signal(
            Side.LONG, confidence=0.45,
            reasoning=[f"{reason} — moderate mean-reversion setup"],
            indicator_snapshot=snapshot, strategy_name="mean_reversion",
        )

    # --- SHORT setups ---
    if rsi_short and bb_short:
        return Signal(
            Side.SHORT, confidence=0.65,
            reasoning=[
                f"RSI ({rsi:.1f}) overbought + price at upper BB — strong mean-reversion setup",
            ],
            indicator_snapshot=snapshot, strategy_name="mean_reversion",
        )
    if rsi_short or bb_short:
        reason = f"RSI ({rsi:.1f}) overbought" if rsi_short else f"Price at upper Bollinger Band"
        return Signal(
            Side.SHORT, confidence=0.45,
            reasoning=[f"{reason} — moderate mean-reversion setup"],
            indicator_snapshot=snapshot, strategy_name="mean_reversion",
        )

    return Signal(
        Side.NONE, confidence=0.0,
        reasoning=[f"No RSI extreme (RSI={rsi:.1f}) or BB touch"],
        indicator_snapshot=snapshot, strategy_name="mean_reversion",
    )
