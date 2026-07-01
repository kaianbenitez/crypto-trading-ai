import pandas as pd
from enum import Enum


class Regime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"


def detect_regime(row: pd.Series, params: dict) -> Regime:
    """ADX-based regime detection. ADX > threshold = trending, else ranging."""
    adx_threshold = params.get("adx_trend_threshold", 25)
    adx = row.get("adx")
    if adx is None or pd.isna(adx):
        return Regime.RANGING
    return Regime.TRENDING if adx >= adx_threshold else Regime.RANGING
