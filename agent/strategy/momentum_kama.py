"""Volatility-filtered KAMA/Donchian momentum leg."""
from __future__ import annotations

import pandas as pd
import ta

from agent.strategy.signal import Signal, Side


def add_momentum_features(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = df.copy()
    kama_window = params.get("kama_window", 20)
    out["kama"] = ta.momentum.kama(out["close"], window=kama_window)
    donchian = params.get("donchian_window", 20)
    out["donchian_high"] = out["high"].rolling(donchian).max()
    out["donchian_low"] = out["low"].rolling(donchian).min()
    out["realized_vol"] = out["close"].pct_change().rolling(params.get("rv_window", 30)).std()
    return out


def momentum_kama_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    rv = float(row.get("realized_vol") or 0)
    max_rv = float(params.get("momentum_max_realized_vol", 0.045))
    snapshot = {
        "kama": row.get("kama"),
        "donchian_high": row.get("donchian_high"),
        "donchian_low": row.get("donchian_low"),
        "realized_vol": rv,
    }
    if rv > max_rv:
        return Signal(Side.NONE, 0.0, [f"Momentum blocked: realized vol {rv:.3f} > {max_rv:.3f}"], snapshot, "momentum_kama")

    close = float(row.get("close") or 0)
    prev_close = float(prev.get("close") or 0)
    kama = float(row.get("kama") or close)
    prev_kama = float(prev.get("kama") or prev_close)
    high = float(prev.get("donchian_high") or 0)
    low = float(prev.get("donchian_low") or 0)

    if close > high > 0 and close > kama and kama >= prev_kama:
        return Signal(
            Side.LONG,
            0.62,
            [f"Donchian breakout above {high:.4f} with rising KAMA; vol filter passed"],
            snapshot,
            "momentum_kama",
        )
    if close < low < prev_close and close < kama and kama <= prev_kama:
        return Signal(
            Side.SHORT,
            0.62,
            [f"Donchian breakdown below {low:.4f} with falling KAMA; vol filter passed"],
            snapshot,
            "momentum_kama",
        )
    return Signal(Side.NONE, 0.0, ["No KAMA/Donchian momentum breakout"], snapshot, "momentum_kama")
