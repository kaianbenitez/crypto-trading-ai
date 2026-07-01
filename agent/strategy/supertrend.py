import numpy as np
import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.strategy.signal import Signal, Side


def prep_supertrend(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = add_indicators(df, params)
    multiplier = params.get("supertrend_mult", 3.0)

    hl2 = (out["high"] + out["low"]) / 2
    upper_basic = hl2 + multiplier * out["atr"]
    lower_basic = hl2 - multiplier * out["atr"]

    upper = upper_basic.copy()
    lower = lower_basic.copy()
    direction = pd.Series(1, index=out.index)  # 1 = uptrend, -1 = downtrend

    close = out["close"].to_numpy(copy=True)
    upper_v = upper.to_numpy(copy=True)
    lower_v = lower.to_numpy(copy=True)
    upper_basic_v = upper_basic.to_numpy(copy=True)
    lower_basic_v = lower_basic.to_numpy(copy=True)
    direction_v = direction.to_numpy(copy=True)

    for i in range(1, len(out)):
        upper_v[i] = min(upper_basic_v[i], upper_v[i - 1]) if close[i - 1] <= upper_v[i - 1] else upper_basic_v[i]
        lower_v[i] = max(lower_basic_v[i], lower_v[i - 1]) if close[i - 1] >= lower_v[i - 1] else lower_basic_v[i]

        if close[i] > upper_v[i - 1]:
            direction_v[i] = 1
        elif close[i] < lower_v[i - 1]:
            direction_v[i] = -1
        else:
            direction_v[i] = direction_v[i - 1]

    out["supertrend_upper"] = upper_v
    out["supertrend_lower"] = lower_v
    out["supertrend_direction"] = direction_v
    out["supertrend_line"] = np.where(direction_v == 1, lower_v, upper_v)
    return out


def supertrend_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    snapshot = {"supertrend_line": row.get("supertrend_line"), "direction": row.get("supertrend_direction"),
                "close": row["close"]}
    vol_ok = bool(row.get("vol_confirmed", False))

    flipped_up = prev.get("supertrend_direction") == -1 and row.get("supertrend_direction") == 1
    flipped_down = prev.get("supertrend_direction") == 1 and row.get("supertrend_direction") == -1

    if flipped_up and vol_ok:
        return Signal(Side.LONG, 0.65, ["Supertrend flipped to uptrend", "Volume confirms the flip"],
                      snapshot, "supertrend")
    if flipped_down and vol_ok:
        return Signal(Side.SHORT, 0.65, ["Supertrend flipped to downtrend", "Volume confirms the flip"],
                      snapshot, "supertrend")
    return Signal(Side.NONE, 0.0, ["No Supertrend flip this bar"], snapshot, "supertrend")
