"""Per-coin regime router for strategy allocation."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class RegimeDecision:
    label: str
    confidence: float
    routing: dict[str, float]
    reasons: list[str]


BASE_ROUTING = {
    "smc": 0.30,
    "mean_reversion": 0.40,
    "momentum": 0.20,
    "funding_basis": 0.10,
}


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _atr_percentile(df: pd.DataFrame) -> float:
    if "atr" not in df or len(df) < 30:
        return 0.5
    window = df["atr"].tail(30).dropna()
    if window.empty:
        return 0.5
    latest = float(window.iloc[-1])
    return float((window <= latest).mean())


def route_regime(df: pd.DataFrame, btc_context: dict | None = None) -> RegimeDecision:
    row = df.iloc[-1]
    adx = float(row.get("adx") or 0)
    atr_pct = _atr_percentile(df)
    realized_vol = float(df["close"].pct_change().tail(30).std() or 0)
    ema_fast = float(row.get("ema_fast") or row.get("close") or 0)
    ema_slow = float(row.get("ema_slow") or row.get("close") or 0)

    reasons = [f"ADX {adx:.1f}", f"ATR percentile {atr_pct:.2f}", f"realized vol {realized_vol:.3f}"]

    if atr_pct >= 0.90 or realized_vol >= 0.06:
        return RegimeDecision("HIGH_VOL", _clip(max(atr_pct, realized_vol / 0.08)), {
            "smc": 0.70, "mean_reversion": 0.10, "momentum": 0.10, "funding_basis": 0.10,
        }, reasons)

    if adx >= 25:
        label = "TREND_UP" if ema_fast >= ema_slow else "TREND_DOWN"
        return RegimeDecision(label, _clip(adx / 40), {
            "smc": 0.35, "mean_reversion": 0.15, "momentum": 0.40, "funding_basis": 0.10,
        }, reasons)

    if adx <= 15 and atr_pct <= 0.65:
        return RegimeDecision("RANGE", _clip((20 - adx) / 20), {
            "smc": 0.20, "mean_reversion": 0.60, "momentum": 0.10, "funding_basis": 0.10,
        }, reasons)

    return RegimeDecision("CHOP", 0.55, {
        "smc": 0.20, "mean_reversion": 0.30, "momentum": 0.10, "funding_basis": 0.40,
    }, reasons + ["mixed trend/range signals; de-risk entries"])
