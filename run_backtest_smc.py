"""Backtest: SMC + Market Context + TA ensemble vs plain TA ensemble.

Symbols: BTC/USDT, ETH/USDT, XRP/USDT, SOL/USDT
TF: 1h, 180-day lookback, walk-forward out-of-sample (4 folds).
No grid search — fixed default params, fast run.

Prints side-by-side comparison so you can see exactly what the new
context/SMC filters add (or remove) vs the baseline.
"""
import time

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.engine import run_backtest
from agent.backtest.validate import walk_forward_split, score, BASE_PARAMS
from agent.strategy.indicators import add_indicators
from agent.fundamental.market_context import add_market_context
from agent.strategy.smc import add_smc

SYMBOLS       = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"]
TIMEFRAME     = "1h"
LOOKBACK_DAYS = 180
EQUITY        = 175.0

PARAMS = dict(BASE_PARAMS, context_window_candles=120, max_atr_ratio=2.0)


def evaluate(df_raw, use_context: bool) -> dict:
    fold_results = []
    for _, test_df in walk_forward_split(df_raw, n_splits=4):
        df = add_indicators(test_df, PARAMS)
        if use_context:
            df = add_market_context(df, PARAMS)
            df = add_smc(df, PARAMS)
        result = run_backtest(df, PARAMS, starting_equity=EQUITY, skip_indicators=True)
        fold_results.append(result)

    if not fold_results:
        raise ValueError("no folds")

    n = len(fold_results)
    return {
        "win_rate":  sum(r.win_rate          for r in fold_results) / n * 100,
        "roi":       sum(r.roi_pct           for r in fold_results) / n,
        "max_dd":    sum(r.max_drawdown_pct  for r in fold_results) / n,
        "trades":    sum(len(r.trades)       for r in fold_results),
    }


def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)

    print(f"\n{'Symbol':<10} {'Mode':<12} {'WinRate%':<10} {'ROI%':<8} {'MaxDD%':<8} {'Trades'}")
    print("-" * 58)

    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...", flush=True)
        try:
            df_raw = fetch_historical_ohlcv(symbol, TIMEFRAME, since_ms)
        except Exception as e:
            print(f"  {symbol} fetch failed: {e}")
            continue

        for label, use_ctx in [("Baseline", False), ("SMC+Context", True)]:
            try:
                r = evaluate(df_raw, use_ctx)
                print(
                    f"{symbol:<10} {label:<12} "
                    f"{r['win_rate']:<10.1f} {r['roi']:<8.2f} "
                    f"{r['max_dd']:<8.2f} {r['trades']}",
                    flush=True,
                )
            except Exception as e:
                print(f"{symbol:<10} {label:<12} ERROR: {e}", flush=True)

        print()


if __name__ == "__main__":
    main()
