"""Multi-timeframe (MTF) confluence scorer.

For each symbol, scores 5 timeframes (15m → 1w) on a 0-100 scale:
  50 = neutral
  >55 = bullish bias
  <45 = bearish bias

Timeframes are weighted by their reliability / noise level:
  15m  5%  — entry timing only, very noisy
  1h  10%  — primary signal TF
  4h  30%  — intermediate trend context
  1d  40%  — dominant structure, highest weight
  1w  15%  — macro bias

Weighted confluence score drives two outputs:
  1. Overall bias (bullish / neutral / bearish)
  2. EV in R — expected value per trade given the confluence level,
     computed as: EV = (win_prob × TP_mult) − ((1 − win_prob) × SL_mult)
     where win_prob is derived from the confluence score.
     EV < 0 = negative edge → don't trade regardless of TA signal.

In live use (orchestrator): fetches each TF from the exchange directly.
In backtesting: caller passes pre-resampled DataFrames to avoid extra
API calls (resample 1h → 4h/1d with pandas).
"""
import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.fundamental.market_context import add_market_context
from agent.strategy.smc import add_smc

TF_WEIGHTS = {
    "15m": 0.05,
    "1h":  0.20,
    "4h":  0.35,
    "1d":  0.25,
    "1w":  0.15,
}

MIN_EV_R = 0.25


def score_single_tf(df: pd.DataFrame, params: dict) -> dict:
    """Score one timeframe. Returns score (0-100), bias, and component breakdown."""
    try:
        df = add_indicators(df, params)
        df = add_market_context(df, params)
        df = add_smc(df, params)
        df = df.dropna().reset_index(drop=True)
    except Exception:
        return {"score": 50, "bias": "neutral", "components": {}}

    if len(df) < 2:
        return {"score": 50, "bias": "neutral", "components": {}}

    row  = df.iloc[-1]
    components = {}
    score = 50.0

    # --- EMA trend direction (+/- 10) ---
    ema_bull = float(row.get("ema_fast", 0)) > float(row.get("ema_slow", 0))
    delta = 10 if ema_bull else -10
    score += delta
    components["ema"] = delta

    # --- MACD momentum (+/- 8) ---
    macd_bull = float(row.get("macd", 0)) > float(row.get("macd_signal", 0))
    delta = 8 if macd_bull else -8
    score += delta
    components["macd"] = delta

    # --- RSI level (+/- 7) ---
    rsi = float(row.get("rsi", 50))
    if rsi > 55:
        delta = 7
    elif rsi < 45:
        delta = -7
    else:
        delta = 0
    score += delta
    components["rsi"] = delta

    # --- ADX amplifies EMA direction (+/- 5) ---
    adx = float(row.get("adx", 0))
    if adx > 25:
        delta = 5 if ema_bull else -5
        score += delta
        components["adx"] = delta
    else:
        components["adx"] = 0

    # --- Bollinger Band position (+/- 5) ---
    bb_upper = float(row.get("bb_upper", 0))
    bb_lower = float(row.get("bb_lower", 0))
    close    = float(row.get("close", 0))
    bb_range = bb_upper - bb_lower
    if bb_range > 0:
        bb_pos = (close - bb_lower) / bb_range
        if bb_pos > 0.6:
            delta = 5
        elif bb_pos < 0.4:
            delta = -5
        else:
            delta = 0
        score += delta
        components["bb"] = delta
    else:
        components["bb"] = 0

    # --- Market structure bias (+/- 10) ---
    bias_val = int(row.get("mc_structure_bias", 0))
    delta = bias_val * 10
    score += delta
    components["structure"] = delta

    # --- Premium / discount zone (+/- 5) ---
    if bool(row.get("mc_in_discount", False)):
        score += 5
        components["zone"] = 5
    elif bool(row.get("mc_in_premium", False)):
        score -= 5
        components["zone"] = -5
    else:
        components["zone"] = 0

    # --- SMC signals (+/- 8 sweep, +/- 5 OB) ---
    smc_delta = 0
    if bool(row.get("smc_bull_sweep", False)):
        smc_delta += 8
    if bool(row.get("smc_bear_sweep", False)):
        smc_delta -= 8
    if bool(row.get("smc_near_bull_ob", False)):
        smc_delta += 5
    if bool(row.get("smc_near_bear_ob", False)):
        smc_delta -= 5
    score += smc_delta
    components["smc"] = smc_delta

    score = max(0.0, min(100.0, score))
    bias  = "bullish" if score > 55 else ("bearish" if score < 45 else "neutral")

    return {"score": score, "bias": bias, "components": components}


def resample_ohlcv(df_1h: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """Resample 1h OHLCV DataFrame to a higher timeframe.
    Used in backtesting so we don't need extra API calls per TF."""
    rules = {"4h": "4h", "1d": "1D", "1w": "1W"}
    rule  = rules.get(target_tf)
    if not rule:
        return df_1h

    df = df_1h.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")

    resampled = df.resample(rule).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna().reset_index()

    resampled["timestamp"] = resampled["timestamp"].astype("int64") // 1_000_000
    return resampled


def compute_confluence(
    tf_dataframes: dict[str, pd.DataFrame],
    params: dict,
    signal_side: str | None = None,
) -> dict:
    """Compute weighted MTF confluence score and EV.

    Args:
        tf_dataframes: {"15m": df, "1h": df, "4h": df, "1d": df, "1w": df}
                       Pass only the TFs you have data for — missing TFs are skipped.
        params:        Strategy params dict.
        signal_side:   "long" | "short" | None — used to compute directional EV.

    Returns dict with:
        weighted_score    float 0-100
        confluence_pct    same (alias)
        overall_bias      "bullish" | "neutral" | "bearish"
        tf_scores         {tf: {score, bias, components}}
        ev_long           float (R multiples)
        ev_short          float (R multiples)
        ev                float — EV for signal_side direction (None if no side given)
        approved          bool — True if EV > MIN_EV_R and bias aligns with signal
        block_reason      str | None
    """
    tf_scores  = {}
    total_w    = 0.0
    weighted   = 0.0

    for tf, df in tf_dataframes.items():
        if df is None or len(df) < 10:
            continue
        w      = TF_WEIGHTS.get(tf, 0)
        result = score_single_tf(df, params)
        tf_scores[tf] = {**result, "weight": w}
        weighted  += result["score"] * w
        total_w   += w

    if total_w == 0:
        return {
            "weighted_score": 50, "confluence_pct": 50,
            "overall_bias": "neutral", "tf_scores": {},
            "ev_long": 0, "ev_short": 0, "ev": 0,
            "approved": False, "block_reason": "No TF data available",
        }

    # Normalise if we don't have all TFs
    weighted_score = weighted / total_w

    overall_bias = (
        "bullish" if weighted_score > 55 else
        ("bearish" if weighted_score < 45 else "neutral")
    )

    # EV calculation
    # win_prob for LONG = how bullish the score is (score/100)
    # win_prob for SHORT = how bearish (1 - score/100)
    atr_sl = params.get("atr_mult_sl", 1.5)
    atr_tp = params.get("atr_mult_tp", 3.0)

    win_prob_long  = weighted_score / 100
    win_prob_short = 1.0 - win_prob_long

    ev_long  = (win_prob_long  * atr_tp) - ((1 - win_prob_long)  * atr_sl)
    ev_short = (win_prob_short * atr_tp) - ((1 - win_prob_short) * atr_sl)

    ev           = None
    approved     = False
    block_reason = None
    min_ev_r = float(params.get("min_ev_r", MIN_EV_R))

    if signal_side == "long":
        ev = ev_long
        if overall_bias == "bearish":
            block_reason = f"MTF bias is BEARISH (score {weighted_score:.1f}) — blocks long signal"
        elif ev < min_ev_r:
            block_reason = f"EV {ev:.2f}R below minimum {min_ev_r:.2f}R — poor risk/reward"
        else:
            approved = True

    elif signal_side == "short":
        ev = ev_short
        if overall_bias == "bullish":
            block_reason = f"MTF bias is BULLISH (score {weighted_score:.1f}) — blocks short signal"
        elif ev < min_ev_r:
            block_reason = f"EV {ev:.2f}R below minimum {min_ev_r:.2f}R — poor risk/reward"
        else:
            approved = True

    return {
        "weighted_score":  weighted_score,
        "confluence_pct":  weighted_score,
        "overall_bias":    overall_bias,
        "tf_scores":       tf_scores,
        "ev_long":         ev_long,
        "ev_short":        ev_short,
        "ev":              ev,
        "approved":        approved,
        "block_reason":    block_reason,
    }
