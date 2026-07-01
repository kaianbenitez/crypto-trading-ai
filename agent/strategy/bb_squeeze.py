import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.strategy.signal import Signal, Side


def prep_bb_squeeze(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = add_indicators(df, params)
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"]

    lookback = params.get("squeeze_lookback", 100)
    percentile = params.get("squeeze_percentile", 0.2)
    out["bb_width_threshold"] = out["bb_width"].rolling(lookback).quantile(percentile)
    out["in_squeeze"] = out["bb_width"] <= out["bb_width_threshold"]

    confirm_window = params.get("squeeze_recent_window", 5)
    out["recently_squeezed"] = out["in_squeeze"].rolling(confirm_window).max().astype(bool)
    return out


def bb_squeeze_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    snapshot = {"bb_width": row.get("bb_width"), "recently_squeezed": row.get("recently_squeezed"),
                "close": row["close"], "bb_upper": row.get("bb_upper"), "bb_lower": row.get("bb_lower")}

    if pd.isna(row.get("bb_width_threshold")):
        return Signal(Side.NONE, 0.0, ["Not enough history to establish squeeze baseline"], snapshot, "bb_squeeze")

    vol_ok = bool(row.get("vol_confirmed", False))
    if not row.get("recently_squeezed"):
        return Signal(Side.NONE, 0.0, ["No recent volatility squeeze — skipping"], snapshot, "bb_squeeze")

    broke_up = prev["close"] <= prev["bb_upper"] and row["close"] > row["bb_upper"]
    broke_down = prev["close"] >= prev["bb_lower"] and row["close"] < row["bb_lower"]

    if broke_up and vol_ok:
        return Signal(Side.LONG, 0.65,
                      ["Bollinger Band squeeze detected in recent bars", "Price broke above upper band on expansion",
                       "Volume confirms breakout"],
                      snapshot, "bb_squeeze")
    if broke_down and vol_ok:
        return Signal(Side.SHORT, 0.65,
                      ["Bollinger Band squeeze detected in recent bars", "Price broke below lower band on expansion",
                       "Volume confirms breakout"],
                      snapshot, "bb_squeeze")
    return Signal(Side.NONE, 0.0, ["Squeeze present but no breakout yet"], snapshot, "bb_squeeze")
