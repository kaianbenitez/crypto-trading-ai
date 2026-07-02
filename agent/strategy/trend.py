import pandas as pd

from agent.strategy.signal import Signal, Side


def trend_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    """EMA trend alignment + MACD confirmation, gated by volume and ADX.

    Two tiers:
      - Crossover (0.70): EMA fast just crossed slow this candle + MACD aligned + volume
      - Aligned  (0.55): EMA fast persistently above/below slow + MACD aligned + ADX > 20 + volume
        (fires every candle the trend is intact, not just the moment of cross)
    """
    snapshot = {
        "ema_fast": row.get("ema_fast"), "ema_slow": row.get("ema_slow"),
        "macd": row.get("macd"), "macd_signal": row.get("macd_signal"),
        "adx": row.get("adx"), "vol_confirmed": row.get("vol_confirmed"),
    }

    ema_bull  = row["ema_fast"] > row["ema_slow"]
    ema_bear  = row["ema_fast"] < row["ema_slow"]
    # True crossover: alignment just flipped vs previous candle
    ema_bull_cross = prev["ema_fast"] <= prev["ema_slow"] and ema_bull
    ema_bear_cross = prev["ema_fast"] >= prev["ema_slow"] and ema_bear
    macd_bull = row["macd"] > row["macd_signal"]
    macd_bear = row["macd"] < row["macd_signal"]
    vol_ok    = bool(row.get("vol_confirmed", False))
    adx_ok    = float(row.get("adx", 0)) > 20

    # --- Tier 1: fresh crossover (highest confidence) ---
    if ema_bull_cross and macd_bull and vol_ok:
        return Signal(
            Side.LONG, confidence=0.70,
            reasoning=[
                "EMA fast crossed above EMA slow (bullish crossover)",
                "MACD above signal line, confirming upward momentum",
                "Volume above SMA, confirming move is not low-conviction",
            ],
            indicator_snapshot=snapshot, strategy_name="trend_following",
        )

    if ema_bear_cross and macd_bear and vol_ok:
        return Signal(
            Side.SHORT, confidence=0.70,
            reasoning=[
                "EMA fast crossed below EMA slow (bearish crossover)",
                "MACD below signal line, confirming downward momentum",
                "Volume above SMA, confirming move is not low-conviction",
            ],
            indicator_snapshot=snapshot, strategy_name="trend_following",
        )

    # --- Tier 2: trend persistently aligned (ADX gates quality; no vol gate — low vol ≠ no trend) ---
    if ema_bull and macd_bull and adx_ok:
        return Signal(
            Side.LONG, confidence=0.55,
            reasoning=[
                "EMA fast above EMA slow — bullish trend intact",
                "MACD above signal line, momentum positive",
                f"ADX {row.get('adx', 0):.1f} confirms directional trend",
            ],
            indicator_snapshot=snapshot, strategy_name="trend_following",
        )

    if ema_bear and macd_bear and adx_ok:
        return Signal(
            Side.SHORT, confidence=0.55,
            reasoning=[
                "EMA fast below EMA slow — bearish trend intact",
                "MACD below signal line, momentum negative",
                f"ADX {row.get('adx', 0):.1f} confirms directional trend",
            ],
            indicator_snapshot=snapshot, strategy_name="trend_following",
        )

    # Log exactly which condition failed
    reasons = []
    if not adx_ok:   reasons.append(f"ADX {row.get('adx', 0):.1f} < 20 (weak trend)")
    if not (ema_bull or ema_bear): reasons.append("EMA fast/slow not aligned")
    elif ema_bull and not macd_bull: reasons.append("EMA bullish but MACD not confirming")
    elif ema_bear and not macd_bear: reasons.append("EMA bearish but MACD not confirming")

    return Signal(
        Side.NONE, confidence=0.0,
        reasoning=[f"No trend signal: {'; '.join(reasons) or 'mixed conditions'}"],
        indicator_snapshot=snapshot, strategy_name="trend_following",
    )
