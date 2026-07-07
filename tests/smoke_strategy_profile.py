"""Smoke script for the strategy profile system (agent/strategy/profiles.py
+ ensemble gating). Run: `python3 tests/smoke_strategy_profile.py`.

Proves the core guarantee: under baseline_simple, SMC / news / memory /
adaptive are OBSERVED and recorded but cannot change the confidence used for
trading; switching to full_agentic re-applies them. Also covers the
double-counting diagnostic and the "news can't create a trade" invariant.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from agent.strategy.ensemble import generate_signal  # noqa: E402
from agent.strategy.profiles import get_profile, gated_delta, alignment_report, PROFILES  # noqa: E402
from agent.strategy.signal import Side  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


# A trending-long setup that also lights up every SMC bull flag, so SMC would
# add +0.25 if allowed. prev is already EMA-aligned -> tier-2 base (0.55).
def make_row(**over):
    base = {
        "ema_fast": 101.0, "ema_slow": 100.0,
        "macd": 1.0, "macd_signal": 0.0,
        "adx": 30.0, "vol_confirmed": True,
        "close": 101.0,
        "smc_near_bull_ob": True, "smc_bull_sweep": True, "smc_fvg_bull": False,
    }
    base.update(over)
    return pd.Series(base)


PREV_ALIGNED = pd.Series({"ema_fast": 101.0, "ema_slow": 100.0})


def test_profile_resolution():
    check("Default (None) resolves to baseline_simple", get_profile(None).name == "baseline_simple")
    check("Unknown name falls back to baseline_simple", get_profile("typo-nonsense").name == "baseline_simple")
    check("full_agentic has SMC active", get_profile("full_agentic").smc_active is True)
    check("baseline_simple has SMC inactive", get_profile("baseline_simple").smc_active is False)
    check("baseline lists smc as observe-only", "smc" in get_profile("baseline_simple").observe_only_modules)
    check("full lists smc as decision-active", "smc" in get_profile("full_agentic").decision_active_modules)


def test_smc_gated_by_profile():
    row = make_row()
    base_sig = generate_signal(row, PREV_ALIGNED, {}, profile=PROFILES["baseline_simple"])
    full_sig = generate_signal(row, PREV_ALIGNED, {}, profile=PROFILES["full_agentic"])

    check("Base signal is an actionable long", base_sig.side == Side.LONG and base_sig.is_actionable)
    check(f"baseline_simple final == base 0.55 (SMC withheld) — got {base_sig.confidence}", abs(base_sig.confidence - 0.55) < 1e-9)
    check(f"full_agentic final == 0.80 (SMC applied +0.25) — got {full_sig.confidence}", abs(full_sig.confidence - 0.80) < 1e-9)

    bd_base = base_sig.indicator_snapshot["confidence_breakdown"]
    bd_full = full_sig.indicator_snapshot["confidence_breakdown"]
    check("baseline records SMC observed +0.25", abs(bd_base["smc_observed"] - 0.25) < 1e-9)
    check("baseline records SMC applied 0.0 (proof: observed but not applied)", bd_base["smc_applied"] == 0.0)
    check("full records SMC applied +0.25", abs(bd_full["smc_applied"] - 0.25) < 1e-9)
    check("breakdown carries the profile name", bd_base["profile"] == "baseline_simple")
    check("raw smc_boost still recorded for observability", abs(base_sig.indicator_snapshot["smc_boost"] - 0.25) < 1e-9)


def test_default_param_profile_is_baseline():
    # No explicit profile + no params key -> baseline (SMC withheld).
    sig = generate_signal(make_row(), PREV_ALIGNED, {})
    check("No-profile call defaults to baseline (0.55)", abs(sig.confidence - 0.55) < 1e-9)
    # params can opt into the full stack (how backtests compare simple vs full).
    sig_full = generate_signal(make_row(), PREV_ALIGNED, {"strategy_profile": "full_agentic"})
    check("params['strategy_profile']=full_agentic re-applies SMC (0.80)", abs(sig_full.confidence - 0.80) < 1e-9)


def test_gated_delta_memory_news_adaptive():
    # Memory penalty: observed but not applied under baseline; applied when active.
    sig = SimpleNamespace(confidence=0.55)
    bd = {}
    gated_delta(sig, -0.10, active=False, label="memory", breakdown=bd)
    check("memory delta observed (-0.10)", bd["memory_observed"] == -0.10)
    check("memory not applied under baseline (conf unchanged)", bd["memory_applied"] == 0.0 and sig.confidence == 0.55)
    gated_delta(sig, -0.10, active=True, label="memory", breakdown=bd)
    check("memory applied when active (0.45)", abs(sig.confidence - 0.45) < 1e-9)

    # News boost is small by design (±0.05) — observe-only under baseline.
    sig2 = SimpleNamespace(confidence=0.55)
    bd2 = {}
    gated_delta(sig2, 0.05, active=False, label="news", breakdown=bd2)
    check("news observed but not applied under baseline", bd2["news_observed"] == 0.05 and sig2.confidence == 0.55)
    gated_delta(sig2, 0.05, active=True, label="news", breakdown=bd2)
    check("news boost is small/capped even when applied (0.60)", abs(sig2.confidence - 0.60) < 1e-9)


def test_news_cannot_create_a_trade():
    # Flat market -> no base signal. SMC/news/memory run AFTER the actionable
    # check, so a non-signal can never be turned into a trade by them.
    flat = make_row(ema_fast=100.0, ema_slow=100.0, macd=0.0, macd_signal=0.0, adx=10.0)
    sig = generate_signal(flat, pd.Series({"ema_fast": 100.0, "ema_slow": 100.0}), {}, profile=PROFILES["full_agentic"])
    check("Flat market yields no actionable signal", sig.side == Side.NONE and not sig.is_actionable)
    check("No confidence on a non-signal (news/SMC can't manufacture one)", sig.confidence == 0.0)


def test_double_counting_diagnostic():
    # Trend cluster (ema/macd/adx) + MTF bullish, but NO independent SMC:
    # 4 aligned, ~2 independent -> redundancy flag fires.
    redundant = make_row(smc_near_bull_ob=False, smc_bull_sweep=False, smc_fvg_bull=False)
    rep = alignment_report(redundant, "long", "bullish")
    check(f"aligned_count == 4 (got {rep['aligned_count']})", rep["aligned_count"] == 4)
    check(f"independent est == 2 (got {rep['independent_signals_est']})", rep["independent_signals_est"] == 2)
    check("redundancy flag fires when confluence is just the trend + MTF", rep["redundancy_flag"] is True)

    # Only the base trend, MTF neutral, no SMC: 3 aligned -> not flagged.
    lone = make_row(smc_near_bull_ob=False, smc_bull_sweep=False, smc_fvg_bull=False)
    rep2 = alignment_report(lone, "long", "neutral")
    check("no redundancy flag when only the base trend agrees", rep2["redundancy_flag"] is False)


def main():
    test_profile_resolution()
    test_smc_gated_by_profile()
    test_default_param_profile_is_baseline()
    test_gated_delta_memory_news_adaptive()
    test_news_cannot_create_a_trade()
    test_double_counting_diagnostic()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
