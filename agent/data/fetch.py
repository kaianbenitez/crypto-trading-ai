import os
import pandas as pd
import ccxt


def fetch_historical_ohlcv(symbol: str, timeframe: str, since_ms: int, limit_per_call: int = 1000,
                            cache_dir: str = "data_cache") -> pd.DataFrame:
    """Pulls historical OHLCV from Binance public API (no key needed for market data)
    and caches to CSV so repeated backtests don't re-hit the API."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{symbol.replace('/', '_')}_{timeframe}_{since_ms}.csv")
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path)

    exchange = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True, "timeout": 15000})
    all_rows = []
    cursor = since_ms
    stagnant_cursor_count = 0
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit_per_call)
        if not batch:
            break
        all_rows.extend(batch)
        new_cursor = batch[-1][0] + 1
        if new_cursor == cursor:
            stagnant_cursor_count += 1
            if stagnant_cursor_count > 3:
                break  # exchange returning the same window repeatedly; bail instead of looping forever
        else:
            stagnant_cursor_count = 0
        cursor = new_cursor
        if len(batch) < limit_per_call:
            break

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df.to_csv(cache_path, index=False)
    return df
