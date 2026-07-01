"""Grid-search walk-forward backtest with SMC + Market Context filters.

Symbols: ETH/USDT, XRP/USDT (strongest candidates from prior runs)
TF: 1h, 180-day lookback, 4 walk-forward folds, out-of-sample scoring.

Compares optimized baseline (plain TA) vs optimized SMC+Context so the
param tuning is equal on both sides — fair apples-to-apples comparison.
"""
import time
import itertools

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.engine import run_backtest, BacktestResult
from agent.backtest.validate import walk_forward_split, score, BASE_PARAMS
from agent.strategy.indicators import add_indicators
from agent.fundamental.market_context import add_market_context
from agent.strategy.smc import add_smc

SYMBOLS       = ["ETH/USDT", "XRP/USDT"]
TIMEFRAME     = "1h"
LOOKBACK_DAYS = 180
EQUITY        = 1000.0

# Reduced grid vs the 2187-combo full grid — still 486 combos but runs ~4x faster
GRID = {
    "ema_fast":             [9, 12],
    "ema_slow":             [21, 26],
    "rsi_oversold":         [25, 30],
    "rsi_overbought":       [65, 70],
    "adx_trend_threshold":  [20, 25],
    "atr_mult_sl":          [1.2, 1.5, 2.0],
    "atr_mult_tp":          [2.0, 3.0, 4.0],
}

SMC_PARAMS = dict(context_window_candles=120, max_atr_ratio=2.5)


def run_fold(test_df, params, use_context: bool) -> BacktestResult:
    df = add_indicators(test_df, params)
    if use_context:
        df = add_market_context(df, params)
        df = add_smc(df, params)
    return run_backtest(df, params, starting_equity=EQUITY, skip_indicators=True)


def optimize(df_raw, use_context: bool) -> dict:
    keys   = list(GRID.keys())
    combos = list(itertools.product(*GRID.values()))
    folds  = list(walk_forward_split(df_raw, n_splits=4))

    if not folds:
        raise ValueError("not enough data for walk-forward splits")

    best_score   = -float("inf")
    best_summary = None

    for combo in combos:
        params = dict(BASE_PARAMS)
        params.update(dict(zip(keys, combo)))
        params.update(SMC_PARAMS)

        fold_scores  = []
        fold_results = []
        for _, test_df in folds:
            result = run_fold(test_df, params, use_context)
            fold_scores.append(score(result))
            fold_results.append(result)

        avg = sum(fold_scores) / len(fold_scores)
        if avg > best_score:
            best_score = avg
            n = len(fold_results)
            best_summary = {
                "win_rate": sum(r.win_rate         for r in fold_results) / n * 100,
                "roi":      sum(r.roi_pct          for r in fold_results) / n,
                "max_dd":   sum(r.max_drawdown_pct for r in fold_results) / n,
                "trades":   sum(len(r.trades)      for r in fold_results),
                "score":    best_score,
            }

    return best_summary


def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)

    print(f"\n{'Symbol':<10} {'Mode':<14} {'WinRate%':<10} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8} {'Score'}")
    print("-" * 70)

    for symbol in SYMBOLS:
        print(f"\nFetching {symbol}...", flush=True)
        try:
            df_raw = fetch_historical_ohlcv(symbol, TIMEFRAME, since_ms)
            print(f"  Candles: {len(df_raw)}", flush=True)
        except Exception as e:
            print(f"  Fetch failed: {e}")
            continue

        for label, use_ctx in [("Baseline", False), ("SMC+Context", True)]:
            print(f"  Optimizing {label} ({len(list(itertools.product(*GRID.values())))} combos × 4 folds)...", flush=True)
            try:
                r = optimize(df_raw, use_ctx)
                print(
                    f"{symbol:<10} {label:<14} "
                    f"{r['win_rate']:<10.1f} {r['roi']:<8.2f} "
                    f"{r['max_dd']:<8.2f} {r['trades']:<8} {r['score']:.2f}",
                    flush=True,
                )
            except Exception as e:
                print(f"{symbol:<10} {label:<14} ERROR: {e}", flush=True)

    print("\nDone.")


if __name__ == "__main__":
    main()
