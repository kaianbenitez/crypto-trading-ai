"""Fast comparison (no grid search — fixed default params) of day-trading
strategy candidates across the priority symbol set, on 15m and 1h timeframes,
walk-forward out-of-sample, fees+slippage included.

Focus set per user: BTC/ETH (core), XRP/SOL/ADA (2nd tier).
"""
import time

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.engine import run_backtest
from agent.backtest.validate import walk_forward_split, score, BASE_PARAMS
from agent.strategy.orb import prep_orb, orb_signal
from agent.strategy.vwap_reversion import prep_vwap, vwap_reversion_signal
from agent.strategy.supertrend import prep_supertrend, supertrend_signal
from agent.strategy.bb_squeeze import prep_bb_squeeze, bb_squeeze_signal

SYMBOLS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "ADA/USDT"]
TIMEFRAMES = ["15m", "1h"]
LOOKBACK_DAYS = 60
STARTING_EQUITY = 175.0

STRATEGIES = {
    "Ensemble": (None, None, {}),  # None signal_fn -> default trend/mean-reversion ensemble
    "ORB": (prep_orb, orb_signal, {}),
    "VWAP_reversion": (prep_vwap, vwap_reversion_signal, {}),
    "Supertrend": (prep_supertrend, supertrend_signal, {}),
    "BB_squeeze": (prep_bb_squeeze, bb_squeeze_signal, {}),
}


def evaluate(name, prep_fn, signal_fn, extra_params, raw_df):
    params = dict(BASE_PARAMS)
    params.update(extra_params)

    fold_results = []
    for train_df, test_df in walk_forward_split(raw_df, n_splits=4):
        if prep_fn is not None:
            prepped = prep_fn(test_df, params)
            result = run_backtest(prepped, params, starting_equity=STARTING_EQUITY,
                                   signal_fn=signal_fn, skip_indicators=True)
        else:
            result = run_backtest(test_df, params, starting_equity=STARTING_EQUITY)
        fold_results.append(result)

    if not fold_results:
        raise ValueError("no folds")

    avg_win_rate = sum(r.win_rate for r in fold_results) / len(fold_results) * 100
    avg_roi = sum(r.roi_pct for r in fold_results) / len(fold_results)
    avg_dd = sum(r.max_drawdown_pct for r in fold_results) / len(fold_results)
    total_trades = sum(len(r.trades) for r in fold_results)
    return {
        "name": name, "win_rate_pct": avg_win_rate, "roi_pct": avg_roi,
        "max_drawdown_pct": avg_dd, "trades": total_trades,
    }


def main():
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    all_rows = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"\n=== {symbol} {tf} ===", flush=True)
            try:
                raw_df = fetch_historical_ohlcv(symbol, tf, since_ms)
                print(f"Candles: {len(raw_df)}", flush=True)
            except Exception as e:
                print(f"Fetch failed: {e}", flush=True)
                continue

            for strat_name, (prep_fn, signal_fn, extra_params) in STRATEGIES.items():
                try:
                    r = evaluate(strat_name, prep_fn, signal_fn, extra_params, raw_df)
                    r["symbol"] = symbol
                    r["timeframe"] = tf
                    all_rows.append(r)
                    print(f"  {strat_name:<16} WR={r['win_rate_pct']:.1f}% ROI={r['roi_pct']:.2f}% "
                          f"DD={r['max_drawdown_pct']:.2f}% trades={r['trades']}", flush=True)
                except Exception as e:
                    print(f"  {strat_name:<16} FAILED: {e}", flush=True)

    print("\n=== Full Comparison ===")
    print(f"{'Symbol':<10} {'TF':<6} {'Strategy':<16} {'WinRate%':<10} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8}")
    for r in all_rows:
        print(f"{r['symbol']:<10} {r['timeframe']:<6} {r['name']:<16} "
              f"{r['win_rate_pct']:<10.2f} {r['roi_pct']:<8.2f} {r['max_drawdown_pct']:<8.2f} {r['trades']:<8}")


if __name__ == "__main__":
    main()
