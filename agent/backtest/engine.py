from dataclasses import dataclass, field

import pandas as pd

from agent.strategy.indicators import add_indicators
from agent.strategy.ensemble import generate_signal as default_signal_fn
from agent.strategy.signal import Side
from agent.risk.engine import RiskEngine


@dataclass
class SimpleSettings:
    bankroll_usdt: float
    max_risk_per_trade_pct: float = 1.5
    max_daily_drawdown_pct: float = 5
    max_concurrent_positions: int = 1
    max_portfolio_risk_pct: float = 0.0
    max_same_direction_risk_pct: float = 0.0
    min_entry_risk_pct: float = 0.25
    min_stop_cost_multiple: float = 5.0
    taker_fee_pct: float = 0.05
    slippage_pct: float = 0.03
    default_leverage: int = 3
    max_leverage: int = 5
    daily_drawdown_mode: str = "net"
    confidence_risk_scaling: bool = True
    confidence_full_risk_at: float = 0.6


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    final_equity: float = 0.0
    starting_equity: float = 0.0
    reentry_blocks: int = 0
    runner_activations: int = 0

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades)

    @property
    def roi_pct(self) -> float:
        if self.starting_equity == 0:
            return 0.0
        return (self.final_equity - self.starting_equity) / self.starting_equity * 100

    @property
    def max_drawdown_pct(self) -> float:
        if not self.trades:
            return 0.0
        equity = self.starting_equity
        peak = equity
        max_dd = 0.0
        for t in self.trades:
            equity += t["pnl"]
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    @property
    def profit_factor(self) -> float:
        gross_win = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        return gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0

    @property
    def expectancy_r(self) -> float:
        rs = [t.get("r_multiple", 0.0) for t in self.trades]
        return sum(rs) / len(rs) if rs else 0.0


# Binance Futures taker fee is ~0.05%/side as of 2024 (varies by VIP tier).
# Both entries and exits here are simulated as market orders (taker), so fee
# applies twice per round-trip. Slippage is a conservative flat estimate for
# a thin-liquidity scenario on a small account; real fills may be better or
# worse depending on order size relative to book depth.
DEFAULT_TAKER_FEE_PCT = 0.05
DEFAULT_SLIPPAGE_PCT = 0.03


def run_backtest(df: pd.DataFrame, params: dict, starting_equity: float = 175.0,
                  taker_fee_pct: float = DEFAULT_TAKER_FEE_PCT,
                  slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
                  signal_fn=None, skip_indicators: bool = False) -> BacktestResult:
    """Bar-by-bar simulation: one position at a time, entries from signal_fn
    (defaults to the regime-gated trend/mean-reversion ensemble), exits on
    SL/TP touch (intrabar via high/low), no live order book — this is a
    simplification appropriate for parameter screening, not a fill-perfect
    simulator. Walk-forward validation (see validate.py) is what guards against
    overfitting to this simplification. Fees + slippage are applied as a flat
    pct cost on both entry and exit notional, since both are modeled as market
    (taker) orders. Pass skip_indicators=True if the caller already added the
    columns its custom signal_fn needs (e.g. ORB/VWAP/Supertrend-specific cols)."""
    signal_fn = signal_fn or default_signal_fn
    if not skip_indicators:
        df = add_indicators(df, params)
    df = df.dropna().reset_index(drop=True)

    settings = SimpleSettings(bankroll_usdt=starting_equity,
                               max_risk_per_trade_pct=params.get("max_risk_per_trade_pct", 1.5),
                               max_concurrent_positions=1)
    risk = RiskEngine(settings, params)

    cost_pct = (taker_fee_pct + slippage_pct) / 100  # combined per-side drag

    equity = starting_equity
    result = BacktestResult(starting_equity=starting_equity)

    position = None  # dict with side, entry, sl, tp, qty
    last_close = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if position is not None:
            initial_r = abs(position["entry"] - position["initial_sl"])
            direction = 1 if position["side"] == Side.LONG else -1

            if position.get("runner"):
                atr = float(row.get("atr") or 0)
                trail_mult = float(params.get("trail_atr_mult", 2.2))
                if atr > 0:
                    if position["side"] == Side.LONG:
                        position["sl"] = max(position["sl"], float(row["high"]) - atr * trail_mult)
                    else:
                        position["sl"] = min(position["sl"], float(row["low"]) + atr * trail_mult)

            hit_sl = (position["side"] == Side.LONG and row["low"] <= position["sl"]) or \
                     (position["side"] == Side.SHORT and row["high"] >= position["sl"])
            hit_tp = (position["side"] == Side.LONG and row["high"] >= position["tp"]) or \
                     (position["side"] == Side.SHORT and row["low"] <= position["tp"])

            if (
                hit_tp and not hit_sl and not position.get("runner")
                and params.get("enable_trailing_take_profit", False)
                and str(position["strategy"]).startswith("trend")
            ):
                activation_r = float(params.get("tp_trail_activation_r", 1.6))
                tp_r = abs(position["tp"] - position["entry"]) / max(initial_r, 1e-9)
                if tp_r >= activation_r:
                    lock_r = float(params.get("tp_trail_min_locked_r", 0.5))
                    if position["side"] == Side.LONG:
                        position["sl"] = max(position["sl"], position["entry"] + initial_r * lock_r)
                    else:
                        position["sl"] = min(position["sl"], position["entry"] - initial_r * lock_r)
                    position["runner"] = True
                    result.runner_activations += 1
                    hit_tp = False

            if hit_sl or hit_tp:
                exit_price = position["sl"] if hit_sl else position["tp"]
                pnl = (exit_price - position["entry"]) * direction * position["qty"]
                entry_notional = position["entry"] * position["qty"]
                exit_notional = exit_price * position["qty"]
                round_trip_cost = (entry_notional + exit_notional) * cost_pct
                pnl -= round_trip_cost
                equity += pnl
                r_multiple = ((exit_price - position["entry"]) * direction) / max(initial_r, 1e-9)
                result.trades.append({
                    "side": position["side"].value, "entry": position["entry"], "exit": exit_price,
                    "pnl": pnl,
                    "r_multiple": r_multiple,
                    "exit_reason": "stop_loss" if hit_sl else ("trailing_take_profit" if position.get("runner") else "take_profit"),
                    "strategy": position["strategy"], "regime": position["regime"],
                    "fees_and_slippage": round_trip_cost,
                    "reentry": bool(position.get("reentry")),
                })
                risk.record_trade_result(pnl)
                risk.mark_position_closed("BACKTEST")
                last_close = {
                    "index": i,
                    "side": position["side"],
                    "exit_reason": "stop_loss" if hit_sl else "take_profit",
                    "confidence": position.get("confidence", 0.0),
                }
                position = None

        if position is None and not risk.kill_switch_active:
            signal = signal_fn(row, prev, params)
            if signal.is_actionable and signal.confidence > 0:
                is_reentry = False
                if last_close:
                    elapsed = i - int(last_close["index"])
                    exit_reason = str(last_close["exit_reason"])
                    if exit_reason == "take_profit":
                        cooldown = int(params.get("reentry_tp_cooldown_candles", 2))
                        quality_window = int(params.get("reentry_tp_quality_window_candles", 8))
                    else:
                        cooldown = int(params.get("reentry_sl_cooldown_candles", 4))
                        quality_window = int(params.get("reentry_sl_quality_window_candles", 12))
                    if elapsed < cooldown:
                        result.reentry_blocks += 1
                        continue
                    if signal.side == last_close["side"] and elapsed < quality_window:
                        needed_conf = float(last_close.get("confidence") or 0) + float(params.get("reentry_min_conf_improvement", 0.08))
                        if signal.confidence < needed_conf:
                            result.reentry_blocks += 1
                            continue
                        is_reentry = True

                risk.set_bankroll(equity)
                plan = risk.plan_trade("BACKTEST", signal.side, row["close"], row["atr"])
                if plan.approved and plan.qty > 0:
                    position = {
                        "side": signal.side, "entry": row["close"], "sl": plan.stop_loss,
                        "initial_sl": plan.stop_loss, "tp": plan.take_profit, "qty": plan.qty,
                        "strategy": signal.strategy_name, "regime": signal.indicator_snapshot.get("regime"),
                        "confidence": signal.confidence, "reentry": is_reentry, "runner": False,
                    }
                    risk.mark_position_opened(
                        "BACKTEST",
                        side=signal.side,
                        risk_pct=plan.risk_pct,
                        risk_amount_usdt=plan.risk_amount_usdt,
                    )

    result.final_equity = equity
    return result
