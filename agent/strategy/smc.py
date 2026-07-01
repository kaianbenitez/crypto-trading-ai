"""Smart Money Concepts (SMC) feature engineering.

Adds three signal types as boolean columns so the ensemble can use them
as entry filters / confidence boosters without changing the bar-by-bar
engine loop:

  smc_fvg_bull / smc_fvg_bear
      Fair Value Gap (3-candle imbalance) formed in the last window.
      Indicates unfilled institutional order zone price tends to revisit.

  smc_near_bull_ob / smc_near_bear_ob
      Price within 1 ATR of a recent Order Block — last counter-trend
      candle before a strong directional move. High-probability reaction.

  smc_bull_sweep / smc_bear_sweep
      Liquidity sweep: price pierced a recent swing extreme then closed
      back inside — stop-hunt then reverse signature.

All detection is strictly backward-looking (no look-ahead bias).
"""
import pandas as pd


def add_smc(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = df.copy()
    window = params.get("context_window_candles", 120)
    atr = out["atr"]

    # ------------------------------------------------------------------
    # 1. Fair Value Gaps
    # Bullish FVG: high[i-2] < low[i]  — gap between candle i-2 and i
    # Bearish FVG: low[i-2]  > high[i] — gap between candle i-2 and i
    # ------------------------------------------------------------------
    bull_fvg_formed = out["high"].shift(2) < out["low"]
    bear_fvg_formed = out["low"].shift(2)  > out["high"]

    out["smc_fvg_bull"] = bull_fvg_formed.rolling(window, min_periods=1).max().astype(bool)
    out["smc_fvg_bear"] = bear_fvg_formed.rolling(window, min_periods=1).max().astype(bool)

    # ------------------------------------------------------------------
    # 2. Order Blocks — confirmed only after the next candle closes
    # Bullish OB: candle[i-1] bearish + candle[i] strong bull (body > ATR)
    # Bearish OB: candle[i-1] bullish + candle[i] strong bear
    # ------------------------------------------------------------------
    prev_bearish = out["close"].shift(1) < out["open"].shift(1)
    prev_bullish = out["close"].shift(1) > out["open"].shift(1)
    strong_bull  = (out["close"] - out["open"]) > atr
    strong_bear  = (out["open"] - out["close"]) > atr

    bull_ob_now = prev_bearish & strong_bull
    bear_ob_now = prev_bullish & strong_bear

    ob_bull_mid = ((out["open"].shift(1) + out["close"].shift(1)) / 2).where(bull_ob_now)
    ob_bear_mid = ((out["open"].shift(1) + out["close"].shift(1)) / 2).where(bear_ob_now)

    out["smc_ob_bull_price"] = ob_bull_mid.ffill(limit=window)
    out["smc_ob_bear_price"] = ob_bear_mid.ffill(limit=window)

    out["smc_near_bull_ob"] = (
        out["smc_ob_bull_price"].notna() &
        (out["close"] >= out["smc_ob_bull_price"] - atr) &
        (out["close"] <= out["smc_ob_bull_price"] + atr)
    )
    out["smc_near_bear_ob"] = (
        out["smc_ob_bear_price"].notna() &
        (out["close"] >= out["smc_ob_bear_price"] - atr) &
        (out["close"] <= out["smc_ob_bear_price"] + atr)
    )

    # ------------------------------------------------------------------
    # 3. Liquidity Sweeps
    # Bullish: wick below recent swing low, close back above → buy-signal
    # Bearish: wick above recent swing high, close back below → sell-signal
    # ------------------------------------------------------------------
    swing_low  = out["low"].rolling(window, min_periods=1).min().shift(1)
    swing_high = out["high"].rolling(window, min_periods=1).max().shift(1)

    out["smc_bull_sweep"] = (out["low"] < swing_low)  & (out["close"] > swing_low)
    out["smc_bear_sweep"] = (out["high"] > swing_high) & (out["close"] < swing_high)

    return out
