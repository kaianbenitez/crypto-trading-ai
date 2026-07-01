"""Entry point for Phase 1: fetch history, run walk-forward optimization,
print the best param set found and its out-of-sample win-rate/ROI/drawdown.

Usage: python run_backtest.py
"""
import time

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.validate import optimize_walk_forward

SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
LOOKBACK_DAYS = 180
STARTING_EQUITY = 175.0


def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    print(f"Fetching {LOOKBACK_DAYS}d of {TIMEFRAME} {SYMBOL} data...")
    df = fetch_historical_ohlcv(SYMBOL, TIMEFRAME, since_ms)
    print(f"Got {len(df)} candles.")

    print("Running walk-forward grid search (this may take a while)...")
    result = optimize_walk_forward(df, starting_equity=STARTING_EQUITY)

    print("\n=== Best parameter set (out-of-sample, walk-forward) ===")
    for k, v in result["params"].items():
        print(f"  {k}: {v}")

    print("\n=== Performance summary ===")
    for k, v in result["summary"].items():
        print(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")


if __name__ == "__main__":
    main()
