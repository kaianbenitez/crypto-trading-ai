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
  2. EV in true R multiples — EV = (win_prob × RR) − (1 − win_prob),
     where RR = atr_mult_tp / atr_mult_sl (reward per 1R risked) and
     win_prob comes from a conservative score→probability mapping,
     optionally blended with the bot's own realized win rates per
     confluence bucket (see build_ev_calibration).
     EV < 0 = negative edge → don't trade regardless of TA signal.

In live use (orchestrator): fetches each TF from the exchange directly.
In backtesting: caller passes pre-resampled DataFrames to avoid extra
API calls (resample 1h → 4h/1d with pandas).
"""
from datetime import datetime, timezone

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

# ---------------------------------------------------------------------------
# Win-probability model
# ---------------------------------------------------------------------------
# The old model used win_prob = score/100, which made a *neutral* market
# (score 50) a coin flip — wildly optimistic at 2:1 reward:risk, where real
# win rates run 35-45%. This mapping is deliberately conservative: neutral
# confluence maps to ~35% (negative EV at 2:1), and only genuine directional
# confluence produces a positive edge.
#   directional score 50 (neutral)  -> 0.35
#   directional score 65 (decent)   -> 0.44
#   directional score 75 (strong)   -> 0.50
_WIN_PROB_AT_NEUTRAL = 0.35
_WIN_PROB_SLOPE = 0.6  # probability points gained per 100 score points
_CALIBRATION_PRIOR_WEIGHT = 25  # pseudo-trades backing the base mapping
_CALIBRATION_BUCKET_WIDTH = 10


def base_win_prob(directional_score: float) -> float:
    """Map a directional confluence score (0-100, >50 = favours the trade
    direction) to a conservative win probability."""
    p = _WIN_PROB_AT_NEUTRAL + (directional_score - 50.0) / 100.0 * _WIN_PROB_SLOPE
    return min(0.85, max(0.05, p))


def win_prob(directional_score: float, calibration: dict | None = None) -> float:
    """Win probability, optionally blended with realized outcomes.

    Blending is Bayesian-style: the base mapping acts as a prior worth
    _CALIBRATION_PRIOR_WEIGHT pseudo-trades, so a thin sample nudges the
    estimate slightly while a deep one dominates it.
    """
    p = base_win_prob(directional_score)
    if not calibration:
        return p
    bucket = int(directional_score // _CALIBRATION_BUCKET_WIDTH) * _CALIBRATION_BUCKET_WIDTH
    stats = (calibration.get("buckets") or {}).get(bucket)
    if not stats:
        return p
    n = int(stats.get("n", 0))
    wins = float(stats.get("wins", 0))
    if n <= 0:
        return p
    blended = (p * _CALIBRATION_PRIOR_WEIGHT + wins) / (_CALIBRATION_PRIOR_WEIGHT + n)
    return min(0.85, max(0.05, blended))


def build_ev_calibration(session) -> dict:
    """Bucket the bot's own closed trades by directional confluence score and
    count realized wins, for blending into win_prob().

    Directional score = mtf_score for longs, 100 - mtf_score for shorts, so
    one table serves both sides. Returns {"buckets": {bucket: {n, wins}},
    "total": N}; never raises.
    """
    buckets: dict[int, dict] = {}
    total = 0
    try:
        from agent.db.models import Trade
        closed = (
            session.query(Trade)
            .filter(Trade.closed_at.isnot(None), Trade.pnl_usdt.isnot(None))
            .all()
        )
        for trade in closed:
            snap = trade.get_indicator_snapshot() or {}
            raw = snap.get("mtf_score")
            if raw is None:
                continue
            score = float(raw)
            if (trade.side or "").lower() == "short":
                score = 100.0 - score
            bucket = int(score // _CALIBRATION_BUCKET_WIDTH) * _CALIBRATION_BUCKET_WIDTH
            entry = buckets.setdefault(bucket, {"n": 0, "wins": 0})
            entry["n"] += 1
            if float(trade.pnl_usdt) > 0:
                entry["wins"] += 1
            total += 1
    except Exception:
        return {"buckets": {}, "total": 0}
    return {"buckets": buckets, "total": total}


_calibration_cache: dict | None = None
_calibration_fetched_at: datetime | None = None


def get_ev_calibration(session, refresh_hours: float = 6.0) -> dict:
    """Cached wrapper around build_ev_calibration — cheap to call every cycle."""
    global _calibration_cache, _calibration_fetched_at
    now = datetime.now(timezone.utc)
    if (
        _calibration_cache is not None
        and _calibration_fetched_at is not None
        and (now - _calibration_fetched_at).total_seconds() < refresh_hours * 3600
    ):
        return _calibration_cache
    _calibration_cache = build_ev_calibration(session)
    _calibration_fetched_at = now
    return _calibration_cache


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
    calibration: dict | None = None,
) -> dict:
    """Compute weighted MTF confluence score and EV.

    Args:
        tf_dataframes: {"15m": df, "1h": df, "4h": df, "1d": df, "1w": df}
                       Pass only the TFs you have data for — missing TFs are skipped.
        params:        Strategy params dict.
        signal_side:   "long" | "short" | None — used to compute directional EV.
        calibration:   Optional realized-outcome table from build_ev_calibration()
                       to blend into the win-probability estimate.

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

    # EV in true R multiples: risking 1R to win RR (= TP distance / SL distance).
    # EV = p×RR − (1−p). Win probability comes from the conservative mapping in
    # win_prob(), optionally blended with the bot's own realized outcomes.
    atr_sl = float(params.get("atr_mult_sl", 1.5) or 1.5)
    atr_tp = float(params.get("atr_mult_tp", 3.0) or 3.0)
    rr = atr_tp / atr_sl if atr_sl > 0 else 2.0

    win_prob_long  = win_prob(weighted_score, calibration)
    win_prob_short = win_prob(100.0 - weighted_score, calibration)

    ev_long  = (win_prob_long  * rr) - (1 - win_prob_long)
    ev_short = (win_prob_short * rr) - (1 - win_prob_short)

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
        "win_prob_long":   win_prob_long,
        "win_prob_short":  win_prob_short,
        "calibrated_trades": int((calibration or {}).get("total", 0)),
        "approved":        approved,
        "block_reason":    block_reason,
    }
