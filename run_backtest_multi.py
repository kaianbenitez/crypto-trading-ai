"""Runs the walk-forward optimizer across multiple symbols and prints a
comparison table. Use this before deciding which symbols are worth trading
live with this strategy.
"""
import time

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.validate import optimize_walk_forward

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
    "LINK/USDT", "DOT/USDT", "LTC/USDT", "ARB/USDT",
]
TIMEFRAME = "1h"
LOOKBACK_DAYS = 180
STARTING_EQUITY = 175.0


def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    rows = []

    for symbol in SYMBOLS:
        print(f"\n--- {symbol} ---", flush=True)
        try:
            df = fetch_historical_ohlcv(symbol, TIMEFRAME, since_ms)
            print(f"Candles: {len(df)}", flush=True)
            result = optimize_walk_forward(df, starting_equity=STARTING_EQUITY)
            s = result["summary"]
            rows.append({"symbol": symbol, **s})
            print(s, flush=True)
        except Exception as e:
            print(f"Failed for {symbol}: {e}", flush=True)
            rows.append({"symbol": symbol, "error": str(e)})

    print("\n=== Comparison ===")
    print(f"{'Symbol':<10} {'WinRate%':<10} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8}")
    for r in rows:
        if "error" in r:
            print(f"{r['symbol']:<10} ERROR: {r['error']}")
        else:
            print(f"{r['symbol']:<10} {r['avg_win_rate_pct']:<10.2f} {r['avg_roi_pct']:<8.2f} "
                  f"{r['avg_max_drawdown_pct']:<8.2f} {r['total_trades_across_folds']:<8}")


if __name__ == "__main__":
    main()
