"""Challenger strategy backtest: 4H trend filter + 1H breakout execution.

Purpose:
  Test whether BTC/SOL/ADA deserve to become active trade candidates using a
  simpler trend-following strategy than the current ensemble.

Rules:
  - 4H trend filter:
      Long only if close > EMA200 and EMA50 > EMA200.
      Short only if close < EMA200 and EMA50 < EMA200.
  - 1H entry:
      Long breaks prior N-candle high.
      Short breaks prior N-candle low.
  - Volatility filter:
      ATR must be above a minimum ATR% and below a shock ATR ratio.
  - Exits/sizing:
      Reuses existing RiskEngine through run_backtest.
"""

import time

import pandas as pd
import ta

from agent.backtest.engine import run_backtest
from agent.backtest.validate import walk_forward_split
from agent.data.fetch import fetch_historical_ohlcv
from agent.strategy.signal import Side, Signal


SYMBOLS = ["BTC/USDT", "SOL/USDT", "ADA/USDT"]
TIMEFRAME = "1h"
LOOKBACK_DAYS = 180
EQUITY = 1000.0

PARAMS = {
    "max_risk_per_trade_pct": 1.0,
    "atr_period": 14,
    "atr_mult_sl": 2.0,
    "atr_mult_tp": 4.0,
    "breakout_lookback": 20,
    "min_atr_pct": 0.25,
    "max_atr_ratio": 2.75,
    "leverage": 3,
}


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    indexed = df.copy()
    indexed["dt"] = pd.to_datetime(indexed["timestamp"], unit="ms", utc=True)
    indexed = indexed.set_index("dt")
    out = indexed.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "timestamp": "last",
    }).dropna()
    out["trend_ema_50"] = ta.trend.ema_indicator(out["close"], window=50)
    out["trend_ema_200"] = ta.trend.ema_indicator(out["close"], window=200)
    out["trend_long"] = (out["close"] > out["trend_ema_200"]) & (out["trend_ema_50"] > out["trend_ema_200"])
    out["trend_short"] = (out["close"] < out["trend_ema_200"]) & (out["trend_ema_50"] < out["trend_ema_200"])
    return out[["trend_long", "trend_short"]]


def prepare_breakout_df(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = df.copy()
    lookback = params["breakout_lookback"]
    out["atr"] = ta.volatility.average_true_range(
        out["high"], out["low"], out["close"], window=params["atr_period"]
    )
    out["atr_pct"] = out["atr"] / out["close"] * 100
    out["atr_baseline"] = out["atr"].rolling(120).mean()
    out["atr_ratio"] = out["atr"] / out["atr_baseline"]
    out["breakout_high"] = out["high"].shift(1).rolling(lookback).max()
    out["breakout_low"] = out["low"].shift(1).rolling(lookback).min()

    trend_4h = _resample_4h(out)
    out["dt"] = pd.to_datetime(out["timestamp"], unit="ms", utc=True)
    out = out.set_index("dt").join(trend_4h, how="left")
    out[["trend_long", "trend_short"]] = out[["trend_long", "trend_short"]].ffill().fillna(False)
    return out.reset_index(drop=True)


def trend_breakout_signal(row: pd.Series, prev: pd.Series, params: dict) -> Signal:
    atr_ok = row["atr_pct"] >= params["min_atr_pct"]
    shock_ok = row["atr_ratio"] <= params["max_atr_ratio"]

    if not atr_ok:
        return Signal(Side.NONE, 0.0, ["ATR too low for breakout"], strategy_name="trend_breakout")
    if not shock_ok:
        return Signal(Side.NONE, 0.0, ["ATR shock filter blocked"], strategy_name="trend_breakout")

    long_break = row["close"] > row["breakout_high"] and prev["close"] <= prev["breakout_high"]
    short_break = row["close"] < row["breakout_low"] and prev["close"] >= prev["breakout_low"]

    if row["trend_long"] and long_break:
        return Signal(
            Side.LONG,
            0.68,
            ["4H trend bullish; 1H closed above prior breakout high."],
            {
                "trend_4h": "bullish",
                "atr_pct": round(float(row["atr_pct"]), 2),
                "atr_ratio": round(float(row["atr_ratio"]), 2),
            },
            "trend_breakout",
        )

    if row["trend_short"] and short_break:
        return Signal(
            Side.SHORT,
            0.68,
            ["4H trend bearish; 1H closed below prior breakout low."],
            {
                "trend_4h": "bearish",
                "atr_pct": round(float(row["atr_pct"]), 2),
                "atr_ratio": round(float(row["atr_ratio"]), 2),
            },
            "trend_breakout",
        )

    return Signal(Side.NONE, 0.0, ["No trend breakout"], strategy_name="trend_breakout")


def summarize(results: list) -> dict:
    n = len(results)
    return {
        "win_rate": sum(r.win_rate for r in results) / n * 100,
        "roi": sum(r.roi_pct for r in results) / n,
        "max_dd": sum(r.max_drawdown_pct for r in results) / n,
        "trades": sum(len(r.trades) for r in results),
        "pf": sum(r.profit_factor for r in results) / n,
    }


def evaluate_symbol(symbol: str) -> dict:
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    raw = fetch_historical_ohlcv(symbol, TIMEFRAME, since_ms)
    prepared = prepare_breakout_df(raw, PARAMS).dropna().reset_index(drop=True)

    fold_results = []
    for _, test_df in walk_forward_split(prepared, n_splits=4):
        result = run_backtest(
            test_df,
            PARAMS,
            starting_equity=EQUITY,
            signal_fn=trend_breakout_signal,
            skip_indicators=True,
        )
        fold_results.append(result)

    summary = summarize(fold_results)
    summary["candles"] = len(raw)
    return summary


def main():
    print(f"\n{'Symbol':<10} {'WR%':<8} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8} {'PF':<8} Candles")
    print("-" * 70)
    for symbol in SYMBOLS:
        try:
            r = evaluate_symbol(symbol)
            print(
                f"{symbol:<10} {r['win_rate']:<8.1f} {r['roi']:<8.2f} "
                f"{r['max_dd']:<8.2f} {r['trades']:<8} {r['pf']:<8.2f} {r['candles']}",
                flush=True,
            )
        except Exception as exc:
            print(f"{symbol:<10} ERROR: {exc}", flush=True)


if __name__ == "__main__":
    main()
