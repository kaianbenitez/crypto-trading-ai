"""Opening Range Breakout. Crypto has no exchange "open," so we treat each UTC
day as a session and use the first N minutes of it as the opening range.
"""
import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.strategy.signal import Signal, Side


def prep_orb(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = add_indicators(df, params)
    out["dt"] = pd.to_datetime(out["timestamp"], unit="ms")
    out["session_date"] = out["dt"].dt.date
    minutes_into_day = out["dt"].dt.hour * 60 + out["dt"].dt.minute
    or_window_minutes = params.get("orb_window_minutes", 30)
    out["in_opening_range"] = minutes_into_day < or_window_minutes

    or_high = out[out["in_opening_range"]].groupby("session_date")["high"].max()
    or_low = out[out["in_opening_range"]].groupby("session_date")["low"].min()
    out["or_high"] = out["session_date"].map(or_high)
    out["or_low"] = out["session_date"].map(or_low)
    return out


def orb_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    snapshot = {"or_high": row.get("or_high"), "or_low": row.get("or_low"), "close": row["close"]}

    if row.get("in_opening_range") or pd.isna(row.get("or_high")) or pd.isna(row.get("or_low")):
        return Signal(Side.NONE, 0.0, ["Inside or before opening range window — no breakout signal yet"],
                      snapshot, "orb")

    vol_ok = bool(row.get("vol_confirmed", False))
    broke_up = prev["close"] <= row["or_high"] and row["close"] > row["or_high"]
    broke_down = prev["close"] >= row["or_low"] and row["close"] < row["or_low"]

    if broke_up and vol_ok:
        return Signal(Side.LONG, 0.65,
                      [f"Price broke above opening range high ({row['or_high']:.2f})", "Volume confirms breakout"],
                      snapshot, "orb")
    if broke_down and vol_ok:
        return Signal(Side.SHORT, 0.65,
                      [f"Price broke below opening range low ({row['or_low']:.2f})", "Volume confirms breakout"],
                      snapshot, "orb")
    return Signal(Side.NONE, 0.0, ["No opening-range breakout with volume confirmation"], snapshot, "orb")
