import pandas as pd

from agent.strategy.signal import Signal, Side


def trend_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    """EMA crossover + MACD confirmation, gated by volume confirmation."""
    reasoning = []
    snapshot = {
        "ema_fast": row.get("ema_fast"), "ema_slow": row.get("ema_slow"),
        "macd": row.get("macd"), "macd_signal": row.get("macd_signal"),
        "adx": row.get("adx"), "vol_confirmed": row.get("vol_confirmed"),
    }

    ema_bull_cross = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
    ema_bear_cross = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]
    macd_bull = row["macd"] > row["macd_signal"]
    macd_bear = row["macd"] < row["macd_signal"]
    vol_ok = bool(row.get("vol_confirmed", False))

    if ema_bull_cross and macd_bull and vol_ok:
        reasoning = [
            "EMA fast crossed above EMA slow (bullish crossover)",
            "MACD above signal line, confirming upward momentum",
            "Volume above SMA, confirming move is not low-conviction",
        ]
        return Signal(Side.LONG, confidence=0.7, reasoning=reasoning,
                       indicator_snapshot=snapshot, strategy_name="trend_following")

    if ema_bear_cross and macd_bear and vol_ok:
        reasoning = [
            "EMA fast crossed below EMA slow (bearish crossover)",
            "MACD below signal line, confirming downward momentum",
            "Volume above SMA, confirming move is not low-conviction",
        ]
        return Signal(Side.SHORT, confidence=0.7, reasoning=reasoning,
                       indicator_snapshot=snapshot, strategy_name="trend_following")

    return Signal(Side.NONE, confidence=0.0, reasoning=["No qualifying EMA/MACD crossover with volume confirmation"],
                  indicator_snapshot=snapshot, strategy_name="trend_following")
