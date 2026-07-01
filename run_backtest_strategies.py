"""Backtests the 5 day-trading strategy candidates (ORB, VWAP mean-reversion,
Supertrend, BB squeeze breakout, funding-rate fade) on lower timeframes,
walk-forward out-of-sample, fees+slippage included, and prints a comparison
table against each other and against the original 1h trend/mean-reversion
ensemble already validated on ETH.
"""
import time

from agent.data.fetch import fetch_historical_ohlcv
from agent.backtest.engine import run_backtest
from agent.backtest.validate import walk_forward_split, score, BASE_PARAMS
from agent.strategy.orb import prep_orb, orb_signal
from agent.strategy.vwap_reversion import prep_vwap, vwap_reversion_signal
from agent.strategy.supertrend import prep_supertrend, supertrend_signal
from agent.strategy.bb_squeeze import prep_bb_squeeze, bb_squeeze_signal
from agent.strategy.funding_rate import fetch_funding_history, backtest_funding_fade

SYMBOL = "ETH/USDT"
TIMEFRAME = "15m"
LOOKBACK_DAYS = 60
STARTING_EQUITY = 175.0

STRATEGIES = {
    "ORB": (prep_orb, orb_signal, {}),
    "VWAP_reversion": (prep_vwap, vwap_reversion_signal, {}),
    "Supertrend": (prep_supertrend, supertrend_signal, {}),
    "BB_squeeze": (prep_bb_squeeze, bb_squeeze_signal, {}),
}


def evaluate_strategy(name, prep_fn, signal_fn, extra_params, raw_df):
    params = dict(BASE_PARAMS)
    params.update(extra_params)

    fold_scores, fold_results = [], []
    for train_df, test_df in walk_forward_split(raw_df, n_splits=4):
        prepped = prep_fn(test_df, params)
        result = run_backtest(prepped, params, starting_equity=STARTING_EQUITY,
                               signal_fn=signal_fn, skip_indicators=True)
        fold_scores.append(score(result))
        fold_results.append(result)

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
    print(f"Fetching {LOOKBACK_DAYS}d of {TIMEFRAME} {SYMBOL}...")
    raw_df = fetch_historical_ohlcv(SYMBOL, TIMEFRAME, since_ms)
    print(f"Candles: {len(raw_df)}")

    rows = []
    for name, (prep_fn, signal_fn, extra_params) in STRATEGIES.items():
        print(f"\n--- {name} ---")
        try:
            r = evaluate_strategy(name, prep_fn, signal_fn, extra_params, raw_df)
            rows.append(r)
            print(r)
        except Exception as e:
            print(f"Failed: {e}")
            rows.append({"name": name, "error": str(e)})

    print("\n--- Funding_rate_fade ---")
    try:
        funding_df = fetch_funding_history(SYMBOL, since_ms)
        funding_params = dict(BASE_PARAMS, funding_threshold=0.00005)  # ~75th percentile of observed rates
        funding_result = backtest_funding_fade(funding_df, raw_df, funding_params, starting_equity=STARTING_EQUITY)
        rows.append({
            "name": "Funding_rate_fade",
            "win_rate_pct": funding_result["win_rate_pct"],
            "roi_pct": funding_result["roi_pct"],
            "max_drawdown_pct": None,
            "trades": funding_result["total_trades"],
        })
        print(funding_result["total_trades"], funding_result["win_rate_pct"], funding_result["roi_pct"])
    except Exception as e:
        print(f"Failed: {e}")
        rows.append({"name": "Funding_rate_fade", "error": str(e)})

    print("\n=== Comparison (15m, 60d, out-of-sample where applicable) ===")
    print(f"{'Strategy':<20} {'WinRate%':<10} {'ROI%':<8} {'MaxDD%':<8} {'Trades':<8}")
    for r in rows:
        if "error" in r:
            print(f"{r['name']:<20} ERROR: {r['error']}")
        else:
            dd = f"{r['max_drawdown_pct']:.2f}" if r["max_drawdown_pct"] is not None else "n/a"
            print(f"{r['name']:<20} {r['win_rate_pct']:<10.2f} {r['roi_pct']:<8.2f} {dd:<8} {r['trades']:<8}")


if __name__ == "__main__":
    main()
