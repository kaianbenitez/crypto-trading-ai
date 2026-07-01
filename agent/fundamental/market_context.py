"""Rolling market context — computes ATR baseline, recent structure, and
premium/discount zone from a limited candle window only (default 120 candles
= 5 days on 1h TF). Keeps signals anchored to *current* conditions rather
than a 180-day average that includes stale/irrelevant regimes."""
import pandas as pd


def add_market_context(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = df.copy()
    window = params.get("context_window_candles", 120)   # 5 days on 1h
    half = max(window // 2, 20)

    # --- ATR baseline (what is "normal" volatility right now?) ---
    # atr column already added by add_indicators
    out["mc_atr_baseline"] = out["atr"].rolling(window, min_periods=14).mean()
    out["mc_atr_ratio"] = out["atr"] / out["mc_atr_baseline"]
    # >1.5 = elevated volatility, >2.0 = shock/event — used as entry blocker

    # --- Recent range (limited window = no noise from old regimes) ---
    out["mc_recent_high"] = out["high"].rolling(window, min_periods=1).max()
    out["mc_recent_low"]  = out["low"].rolling(window, min_periods=1).min()
    out["mc_range_mid"]   = (out["mc_recent_high"] + out["mc_recent_low"]) / 2

    range_size = (out["mc_recent_high"] - out["mc_recent_low"]).replace(0, float("nan"))
    out["mc_range_position"] = (out["close"] - out["mc_recent_low"]) / range_size
    # 0.0 = at window low, 1.0 = at window high

    # Premium = upper 45–100% of range → favour shorts
    # Discount = lower 0–55% of range → favour longs
    # Small overlap at midpoint intentional — neutral zone avoids over-filtering
    out["mc_in_discount"] = out["mc_range_position"] < 0.35
    out["mc_in_premium"]  = out["mc_range_position"] > 0.65

    # --- Break of Structure (BOS) for structural bias ---
    # Compare current window's extremes to a prior half-window to detect BOS
    prior_high = out["high"].rolling(half, min_periods=1).max().shift(half)
    prior_low  = out["low"].rolling(half, min_periods=1).min().shift(half)

    bos_up   = out["close"] > prior_high   # broke prior structure high → bullish
    bos_down = out["close"] < prior_low    # broke prior structure low  → bearish

    raw = pd.Series(float("nan"), index=out.index)
    raw[bos_up]   = 1.0
    raw[bos_down] = -1.0
    raw[bos_up & bos_down] = float("nan")  # conflicting — stay neutral

    # Forward-fill: bias persists until the opposite BOS fires
    filled = raw.ffill().fillna(0)

    # Only apply bias if held for >= 20 candles — filters fresh/unconfirmed BOS
    bias_age = filled.groupby((filled != filled.shift()).cumsum()).cumcount()
    out["mc_structure_bias"] = filled.where(bias_age >= 20, other=0).astype(int)
    # 1 = bullish structure, -1 = bearish structure, 0 = unconfirmed/no BOS

    return out
