"""Funding-rate extreme fade. Futures-specific edge: when funding is very
positive, longs are crowded and paying shorts heavily — fade by going short,
collecting funding while betting on mean reversion. Mirror for very negative
funding. This doesn't fit the per-candle OHLCV engine (funding settles every
8h on Binance), so it gets its own standalone backtest loop.
"""
import ccxt
import pandas as pd


def fetch_funding_history(symbol: str, since_ms: int, limit: int = 1000) -> pd.DataFrame:
    exchange = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True, "timeout": 15000})
    raw = exchange.fetch_funding_rate_history(symbol, since=since_ms, limit=limit)
    df = pd.DataFrame(raw)[["timestamp", "fundingRate"]]
    df = df.rename(columns={"fundingRate": "funding_rate"})
    return df


def backtest_funding_fade(funding_df: pd.DataFrame, price_df: pd.DataFrame, params: dict,
                           starting_equity: float = 175.0,
                           taker_fee_pct: float = 0.05, slippage_pct: float = 0.03) -> dict:
    """For each funding event, if |funding_rate| exceeds threshold, open a
    contrarian position sized at fixed risk %, hold until the next funding
    event, then close. PnL = price move (against the crowd direction) +
    funding received/paid - fees/slippage."""
    threshold = params.get("funding_threshold", 0.0005)  # 0.05% per 8h is already elevated
    risk_pct = params.get("max_risk_per_trade_pct", 1.5)
    leverage = params.get("leverage", 3)
    cost_pct = (taker_fee_pct + slippage_pct) / 100

    price_df = price_df.sort_values("timestamp").reset_index(drop=True)
    equity = starting_equity
    trades = []

    for i in range(len(funding_df) - 1):
        rate = funding_df.iloc[i]["funding_rate"]
        if abs(rate) < threshold:
            continue

        t_start = funding_df.iloc[i]["timestamp"]
        t_end = funding_df.iloc[i + 1]["timestamp"]

        window = price_df[(price_df["timestamp"] >= t_start) & (price_df["timestamp"] <= t_end)]
        if len(window) < 2:
            continue

        entry_price = window.iloc[0]["close"]
        exit_price = window.iloc[-1]["close"]

        # positive funding -> longs pay shorts -> fade by shorting (direction = -1)
        direction = -1 if rate > 0 else 1
        price_return_pct = ((exit_price - entry_price) / entry_price) * direction

        risk_amount = starting_equity * (risk_pct / 100)
        notional = risk_amount * leverage
        price_pnl = notional * price_return_pct
        funding_pnl = notional * abs(rate) * (1 if direction == -1 and rate > 0 else (1 if direction == 1 and rate < 0 else -1))
        round_trip_cost = notional * 2 * cost_pct

        pnl = price_pnl + funding_pnl - round_trip_cost
        equity += pnl

        trades.append({
            "funding_rate": rate, "direction": "short" if direction == -1 else "long",
            "entry": entry_price, "exit": exit_price, "pnl": pnl,
        })

    wins = [t for t in trades if t["pnl"] > 0]
    return {
        "total_trades": len(trades),
        "win_rate_pct": (len(wins) / len(trades) * 100) if trades else 0.0,
        "final_equity": equity,
        "roi_pct": ((equity - starting_equity) / starting_equity * 100) if starting_equity else 0.0,
        "trades": trades,
    }
