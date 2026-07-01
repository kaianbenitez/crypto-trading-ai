"""MTF confluence backtest — compares three modes side by side:

  Baseline       plain TA ensemble (EMA/MACD/RSI/BB/ADX), optimized params
  SMC+Context    + rolling market context + SMC filters
  MTF+SMC        + multi-timeframe confluence score + EV filter (full stack)

Symbols: ETH/USDT, XRP/USDT, SOL/USDT, ADA/USDT, BTC/USDT
TF: 1h primary, resampled 4h + 1d for MTF scoring
Lookback: 180 days, 4 walk-forward folds, out-of-sample scoring only.
Fixed optimized params from prior run (no grid search — fast).
"""
import time
import itertools

import pandas as pd

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.engine import run_backtest, BacktestResult
from agent.backtest.validate import walk_forward_split, score, BASE_PARAMS
from agent.strategy.indicators import add_indicators
from agent.fundamental.market_context import add_market_context
from agent.strategy.smc import add_smc
from agent.strategy.mtf_scorer import compute_confluence, resample_ohlcv, TF_WEIGHTS
from agent.strategy.ensemble import generate_signal
from agent.strategy.signal import Side

SYMBOLS       = ["ETH/USDT", "XRP/USDT", "SOL/USDT", "ADA/USDT", "BTC/USDT"]
TIMEFRAME     = "1h"
LOOKBACK_DAYS = 180
EQUITY        = 1000.0

PARAMS = dict(
    BASE_PARAMS,
    context_window_candles=120,
    max_atr_ratio=2.5,
    atr_mult_sl=1.5,
    atr_mult_tp=3.0,
    ema_fast=9,
    ema_slow=21,
    rsi_oversold=30,
    rsi_overbought=65,
    adx_trend_threshold=25,
)

MTF_MIN_EV = 0.10  # minimum EV in R to allow entry


# ---------------------------------------------------------------------------
# MTF-aware signal function (wraps generate_signal + MTF gate)
# ---------------------------------------------------------------------------

def make_mtf_signal_fn(full_df: pd.DataFrame, params: dict):
    """Returns a signal_fn that has access to the full df for MTF resampling."""

    def mtf_signal_fn(row: pd.Series, prev: pd.Series, p: dict) -> object:
        signal = generate_signal(row, prev, p)

        if not signal.is_actionable or signal.confidence <= 0:
            return signal

        # Build resampled TFs from the full df up to current row timestamp
        ts = int(row.get("timestamp", 0))
        hist = full_df[full_df["timestamp"] <= ts] if ts > 0 else full_df

        tf_dfs = {"1h": hist}
        for tf in ("4h", "1d"):
            resampled = resample_ohlcv(hist, tf)
            if len(resampled) >= 10:
                tf_dfs[tf] = resampled

        mtf = compute_confluence(tf_dfs, p, signal_side=signal.side.value)

        signal.indicator_snapshot["mtf_score"]      = round(mtf["weighted_score"], 1)
        signal.indicator_snapshot["mtf_bias"]       = mtf["overall_bias"]
        signal.indicator_snapshot["mtf_ev"]         = round(mtf.get("ev") or 0, 2)
        signal.indicator_snapshot["mtf_confluence"] = round(mtf["confluence_pct"], 1)

        if not mtf["approved"]:
            from agent.strategy.signal import Signal
            return Signal(
                Side.NONE, 0.0,
                reasoning=[f"MTF blocked: {mtf['block_reason']}"],
                strategy_name="mtf_filter",
            )

        signal.confidence = min(signal.confidence + 0.10, 1.0)
        signal.reasoning.insert(0,
            f"MTF score={mtf['weighted_score']:.1f} ({mtf['overall_bias']}) "
            f"EV={mtf.get('ev', 0):.2f}R"
        )
        return signal

    return mtf_signal_fn


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def prep(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = add_indicators(df, params)
    df = add_market_context(df, params)
    df = add_smc(df, params)
    return df.dropna().reset_index(drop=True)


def evaluate(df_raw: pd.DataFrame, mode: str) -> dict:
    fold_results: list[BacktestResult] = []

    for _, test_df in walk_forward_split(df_raw, n_splits=4):
        if mode == "Baseline":
            df = add_indicators(test_df, PARAMS)
            result = run_backtest(df, PARAMS, starting_equity=EQUITY, skip_indicators=True)

        elif mode == "SMC+Context":
            df = prep(test_df, PARAMS)
            result = run_backtest(df, PARAMS, starting_equity=EQUITY, skip_indicators=True)

        elif mode == "MTF+SMC":
            # prep adds mc_* and smc_* columns so generate_signal uses them
            df = prep(test_df, PARAMS)
            # attach timestamp column for MTF slicing
            if "timestamp" not in df.columns and "timestamp" in test_df.columns:
                df["timestamp"] = test_df["timestamp"].values[:len(df)]

            signal_fn = make_mtf_signal_fn(df, PARAMS)
            result = run_backtest(
                df, PARAMS, starting_equity=EQUITY,
                signal_fn=signal_fn, skip_indicators=True,
            )

        fold_results.append(result)

    if not fold_results:
        raise ValueError("no folds")

    n = len(fold_results)
    return {
        "win_rate": sum(r.win_rate         for r in fold_results) / n * 100,
        "roi":      sum(r.roi_pct          for r in fold_results) / n,
        "max_dd":   sum(r.max_drawdown_pct for r in fold_results) / n,
        "trades":   sum(len(r.trades)      for r in fold_results),
        "pf":       sum(r.profit_factor    for r in fold_results) / n,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    modes    = ["Baseline", "SMC+Context", "MTF+SMC"]

    print(f"\n{'Symbol':<10} {'Mode':<14} {'WR%':<8} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8} {'PF'}")
    print("-" * 65)

    for symbol in SYMBOLS:
        print(f"\nFetching {symbol}...", flush=True)
        try:
            df_raw = fetch_historical_ohlcv(symbol, TIMEFRAME, since_ms)
            print(f"  {len(df_raw)} candles", flush=True)
        except Exception as e:
            print(f"  Fetch failed: {e}")
            continue

        for mode in modes:
            try:
                r = evaluate(df_raw, mode)
                print(
                    f"{symbol:<10} {mode:<14} "
                    f"{r['win_rate']:<8.1f} {r['roi']:<8.2f} "
                    f"{r['max_dd']:<8.2f} {r['trades']:<8} {r['pf']:.2f}",
                    flush=True,
                )
            except Exception as e:
                print(f"{symbol:<10} {mode:<14} ERROR: {e}", flush=True)

    print("\nDone.")


if __name__ == "__main__":
    main()
