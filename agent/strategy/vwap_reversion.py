import numpy as np
import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.strategy.signal import Signal, Side


def prep_vwap(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = add_indicators(df, params)
    out["dt"] = pd.to_datetime(out["timestamp"], unit="ms")
    out["session_date"] = out["dt"].dt.date

    typical_price = (out["high"] + out["low"] + out["close"]) / 3
    pv = typical_price * out["volume"]
    cum_pv = pv.groupby(out["session_date"]).cumsum()
    cum_vol = out["volume"].groupby(out["session_date"]).cumsum()
    out["vwap"] = cum_pv / cum_vol.replace(0, np.nan)

    deviation = out["close"] - out["vwap"]
    band_window = params.get("vwap_band_window", 20)
    out["vwap_dev_std"] = deviation.rolling(band_window).std()
    band_mult = params.get("vwap_band_mult", 2.0)
    out["vwap_upper"] = out["vwap"] + band_mult * out["vwap_dev_std"]
    out["vwap_lower"] = out["vwap"] - band_mult * out["vwap_dev_std"]
    return out


def vwap_reversion_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    snapshot = {"vwap": row.get("vwap"), "close": row["close"],
                "vwap_upper": row.get("vwap_upper"), "vwap_lower": row.get("vwap_lower")}

    if pd.isna(row.get("vwap_upper")) or pd.isna(row.get("vwap_lower")):
        return Signal(Side.NONE, 0.0, ["Not enough session data yet to compute VWAP bands"], snapshot, "vwap_reversion")

    vol_ok = bool(row.get("vol_confirmed", False))

    if row["close"] <= row["vwap_lower"] and vol_ok:
        return Signal(Side.LONG, 0.6,
                      [f"Price ({row['close']:.2f}) below lower VWAP band ({row['vwap_lower']:.2f})",
                       "Volume confirms reversal interest"],
                      snapshot, "vwap_reversion")
    if row["close"] >= row["vwap_upper"] and vol_ok:
        return Signal(Side.SHORT, 0.6,
                      [f"Price ({row['close']:.2f}) above upper VWAP band ({row['vwap_upper']:.2f})",
                       "Volume confirms reversal interest"],
                      snapshot, "vwap_reversion")
    return Signal(Side.NONE, 0.0, ["Price within VWAP bands — no reversion signal"], snapshot, "vwap_reversion")
