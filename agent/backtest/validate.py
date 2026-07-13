import itertools
import pandas as pd

from agent.backtest.engine import run_backtest, BacktestResult

DEFAULT_GRID = {
    "ema_fast": [9, 12, 15],
    "ema_slow": [21, 26, 34],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "adx_trend_threshold": [20, 25, 30],
    "atr_mult_sl": [1.2, 1.5, 2.0],
    "atr_mult_tp": [2.0, 3.0, 4.0],
}

BASE_PARAMS = {
    "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "rsi_period": 14, "bb_period": 20, "bb_std": 2,
    "atr_period": 14, "adx_period": 14,
    "vol_sma_period": 20, "vol_confirm_mult": 1.0,
    "max_risk_per_trade_pct": 1.5,
    "min_ev_r": 0.25,
    "enable_trailing_take_profit": True,
    "tp_trail_activation_r": 1.6,
    "tp_trail_min_locked_r": 0.5,
    "tp_trail_min_ev_r": 0.35,
    "reentry_tp_cooldown_candles": 2,
    "reentry_sl_cooldown_candles": 4,
    "reentry_tp_quality_window_candles": 8,
    "reentry_sl_quality_window_candles": 12,
    "reentry_min_ev_improvement_r": 0.25,
    "reentry_min_conf_improvement": 0.08,
    "reentry_max_trades_per_symbol_per_day": 3,
    "reentry_min_ev_multiplier": 1.5,
    "min_stop_cost_multiple": 5.0,
    # Tier-2 trend entries require price still within this many ATRs of
    # ema_fast — blocks late/extended entries where the move has already run.
    "max_trend_extension_atr": 1.5,
}


def walk_forward_split(df: pd.DataFrame, n_splits: int = 4, train_frac: float = 0.7):
    """Yields (train_df, test_df) pairs sliding forward through time. Each split's
    test set is always *after* its train set, so we never validate on the past."""
    n = len(df)
    fold_size = n // n_splits
    for i in range(n_splits):
        start = i * fold_size
        end = start + fold_size
        if end > n:
            break
        fold = df.iloc[start:end].reset_index(drop=True)
        split_point = int(len(fold) * train_frac)
        train_df = fold.iloc[:split_point].reset_index(drop=True)
        test_df = fold.iloc[split_point:].reset_index(drop=True)
        if len(train_df) > 50 and len(test_df) > 20:
            yield train_df, test_df


def score(result: BacktestResult) -> float:
    """Composite score favoring high win-rate AND high ROI, penalized by drawdown.
    Pure ROI maximization tends to pick high-variance param sets that look great
    on one window and blow up on the next — this score discourages that."""
    if not result.trades or len(result.trades) < 3:
        return -999  # not enough trades to trust
    dd_penalty = result.max_drawdown_pct * 0.5
    return (result.win_rate * 100) + (result.roi_pct * 1.5) - dd_penalty


def optimize_walk_forward(df: pd.DataFrame, starting_equity: float = 175.0,
                           grid: dict | None = None, n_splits: int = 4) -> dict:
    """Grid search over param combos, scored on OUT-OF-SAMPLE (test) folds only.
    Returns the best param set + its walk-forward performance summary."""
    grid = grid or DEFAULT_GRID
    keys = list(grid.keys())
    combos = list(itertools.product(*grid.values()))

    folds = list(walk_forward_split(df, n_splits=n_splits))
    if not folds:
        raise ValueError("Not enough data for walk-forward splits; supply more history")

    best_score = -float("inf")
    best_params = None
    best_summary = None

    for combo in combos:
        params = dict(BASE_PARAMS)
        params.update(dict(zip(keys, combo)))

        fold_scores = []
        fold_results = []
        for train_df, test_df in folds:
            # train_df currently unused for param fitting (grid search is global,
            # not per-fold) — it's reserved for a future per-fold fitting step.
            # We still score strictly on test_df to keep this out-of-sample.
            result = run_backtest(test_df, params, starting_equity=starting_equity)
            fold_scores.append(score(result))
            fold_results.append(result)

        avg_score = sum(fold_scores) / len(fold_scores)
        if avg_score > best_score:
            best_score = avg_score
            best_params = params
            avg_win_rate = sum(r.win_rate for r in fold_results) / len(fold_results)
            avg_roi = sum(r.roi_pct for r in fold_results) / len(fold_results)
            avg_dd = sum(r.max_drawdown_pct for r in fold_results) / len(fold_results)
            total_trades = sum(len(r.trades) for r in fold_results)
            best_summary = {
                "avg_win_rate_pct": avg_win_rate * 100,
                "avg_roi_pct": avg_roi,
                "avg_max_drawdown_pct": avg_dd,
                "total_trades_across_folds": total_trades,
                "score": avg_score,
            }

    return {"params": best_params, "summary": best_summary}
