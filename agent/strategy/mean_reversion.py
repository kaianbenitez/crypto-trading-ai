import pandas as pd

from agent.strategy.signal import Signal, Side


def mean_reversion_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    """RSI extremes + Bollinger Band touch, gated by volume confirmation."""
    rsi_oversold = params.get("rsi_oversold", 30)
    rsi_overbought = params.get("rsi_overbought", 70)

    snapshot = {
        "rsi": row.get("rsi"), "bb_upper": row.get("bb_upper"), "bb_lower": row.get("bb_lower"),
        "close": row.get("close"), "vol_confirmed": row.get("vol_confirmed"),
    }
    vol_ok = bool(row.get("vol_confirmed", False))

    if row["rsi"] <= rsi_oversold and row["close"] <= row["bb_lower"] and vol_ok:
        reasoning = [
            f"RSI ({row['rsi']:.1f}) at/below oversold threshold ({rsi_oversold})",
            "Price at/below lower Bollinger Band, indicating statistical extreme",
            "Volume above SMA, confirming reversal interest",
        ]
        return Signal(Side.LONG, confidence=0.6, reasoning=reasoning,
                       indicator_snapshot=snapshot, strategy_name="mean_reversion")

    if row["rsi"] >= rsi_overbought and row["close"] >= row["bb_upper"] and vol_ok:
        reasoning = [
            f"RSI ({row['rsi']:.1f}) at/above overbought threshold ({rsi_overbought})",
            "Price at/above upper Bollinger Band, indicating statistical extreme",
            "Volume above SMA, confirming reversal interest",
        ]
        return Signal(Side.SHORT, confidence=0.6, reasoning=reasoning,
                       indicator_snapshot=snapshot, strategy_name="mean_reversion")

    return Signal(Side.NONE, confidence=0.0, reasoning=["No qualifying RSI/BB extreme with volume confirmation"],
                  indicator_snapshot=snapshot, strategy_name="mean_reversion")
