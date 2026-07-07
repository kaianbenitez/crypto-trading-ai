"""Strategy profiles — gate which modules may affect a trade decision.

The full agentic stack layers several soft confidence adjustments (SMC boost,
news nudge, memory penalty, adaptive weights, coin-brain) on top of a base TA
signal that is *already* trend-confirmed by EMA + MACD + ADX and confirmed
again by the MTF scorer. When a market is trending, all of those tend to point
the same way, so "confluence" can be one condition counted many times —
inflating confidence, producing generic theses, and encouraging late entries.

Profiles let us run a clean baseline (base signal + MTF filter + cost/risk
gates only) while the other modules keep *observing and logging* but cannot
change confidence, EV, sizing, or block/approve a trade. Nothing is deleted —
switch STRATEGY_PROFILE back to full_agentic to restore the current behavior,
so simple vs full can be compared honestly later.

Decision-active in EVERY profile (never gated off):
  ATR shock filter · regime detection · trend/mean-reversion base signal ·
  market-context penalty (premium/discount timing — only ever *reduces*
  confidence, so it can't cause upward double-counting) · MTF directional/EV
  filter · cost/edge gate · risk gates · re-entry guard.

Gated by profile:
  smc_active     — SMC order-block/FVG/sweep boost may raise confidence
  news_active    — news sentiment nudge may change confidence
  memory_active  — past-trade memory penalty/boost may change confidence
  adaptive_active— adaptive learned weights AND coin-brain (auto-disable +
                   per-coin param tuning) may affect the decision
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    smc_active: bool
    news_active: bool
    memory_active: bool
    adaptive_active: bool
    smc_verbose: bool = False       # detailed SMC ablation logging (observe-only)
    memory_verbose: bool = False    # detailed memory/adaptive ablation logging

    @property
    def decision_active_modules(self) -> list[str]:
        mods = ["atr_shock", "regime", "base_signal", "market_context", "mtf", "cost_edge", "risk", "reentry"]
        if self.smc_active:
            mods.append("smc")
        if self.news_active:
            mods.append("news")
        if self.memory_active:
            mods.append("memory")
        if self.adaptive_active:
            mods.extend(["adaptive_weights", "coin_brain"])
        return mods

    @property
    def observe_only_modules(self) -> list[str]:
        obs = []
        if not self.smc_active:
            obs.append("smc")
        if not self.news_active:
            obs.append("news")
        if not self.memory_active:
            obs.append("memory")
        if not self.adaptive_active:
            obs.extend(["adaptive_weights", "coin_brain"])
        return obs


PROFILES: dict[str, StrategyProfile] = {
    "baseline_simple": StrategyProfile(
        "baseline_simple", smc_active=False, news_active=False, memory_active=False, adaptive_active=False,
    ),
    "full_agentic": StrategyProfile(
        "full_agentic", smc_active=True, news_active=True, memory_active=True, adaptive_active=True,
    ),
    "smc_observe": StrategyProfile(
        "smc_observe", smc_active=False, news_active=False, memory_active=False, adaptive_active=False,
        smc_verbose=True,
    ),
    "memory_observe": StrategyProfile(
        "memory_observe", smc_active=False, news_active=False, memory_active=False, adaptive_active=False,
        memory_verbose=True,
    ),
}

DEFAULT_PROFILE = "baseline_simple"


def get_profile(name: str | None) -> StrategyProfile:
    """Resolve a profile by name, falling back to the safe baseline for any
    unknown/empty value (so a typo never silently re-enables the full stack)."""
    return PROFILES.get((name or DEFAULT_PROFILE).strip().lower(), PROFILES[DEFAULT_PROFILE])


def gated_delta(signal, delta: float, active: bool, label: str, breakdown: dict) -> float:
    """Record a module's *observed* confidence contribution, and apply it to
    the signal only if the active profile allows that module to affect
    decisions. Always records `<label>_observed` and `<label>_applied` in
    `breakdown` — so observe-only modules still leave a full audit trail.
    Returns the (possibly unchanged) confidence."""
    delta = float(delta or 0.0)
    breakdown[f"{label}_observed"] = round(delta, 4)
    breakdown[f"{label}_applied"] = round(delta if active else 0.0, 4)
    if active and delta != 0.0:
        signal.confidence = max(0.0, min(1.0, signal.confidence + delta))
    return signal.confidence


def alignment_report(row, side_value: str, mtf_bias: str | None) -> dict:
    """Double-counting diagnostic: flag when EMA / MACD / ADX / MTF / SMC all
    point the same way as the trade. EMA, MACD and ADX are all derived from the
    same trend, so treat them as ~one independent read; the flag fires when
    many signals agree but few are truly independent — i.e. the confidence is
    one market condition measured several times, not real confluence."""
    import pandas as pd

    def _f(key, default=0.0):
        v = row.get(key)
        try:
            return float(v) if v is not None and pd.notna(v) else default
        except Exception:
            return default

    long = side_value == "long"
    ema_dir_long = _f("ema_fast") > _f("ema_slow")
    macd_dir_long = _f("macd") > _f("macd_signal")
    adx_strong = _f("adx") >= 20
    smc_long = bool(row.get("smc_bull_sweep") or row.get("smc_near_bull_ob") or row.get("smc_fvg_bull"))
    smc_short = bool(row.get("smc_bear_sweep") or row.get("smc_near_bear_ob") or row.get("smc_fvg_bear"))

    components = {
        "ema": ema_dir_long == long,
        "macd": macd_dir_long == long,
        "adx": adx_strong and (ema_dir_long == long),
        "mtf": (mtf_bias == "bullish") == long if mtf_bias in ("bullish", "bearish") else False,
        "smc": (smc_long if long else smc_short),
    }
    aligned = sum(1 for v in components.values() if v)
    trend_cluster = sum(1 for k in ("ema", "macd", "adx") if components[k])
    independent = (1 if trend_cluster >= 2 else 0) + (1 if components["mtf"] else 0) + (1 if components["smc"] else 0)
    return {
        "aligned_count": aligned,
        "independent_signals_est": independent,
        "components": components,
        # Many agree, but the agreement collapses to ≤2 independent reads:
        # the "confluence" is mostly the trend counted several times.
        "redundancy_flag": aligned >= 4 and independent <= 2,
    }
