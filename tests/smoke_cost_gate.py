"""Smoke script for the cost/edge validation gates in agent/orchestrator.py.
Run directly: `python3 tests/smoke_cost_gate.py`.

Verifies:
- the extra cost/edge gates reject a high-cost/thin-edge candidate that would
  have cleared the pre-existing MIN_EDGE_AFTER_COST_R floor
- a genuinely strong candidate still passes
- cost metrics (gross_r, net_r_after_estimated_cost, cost_as_pct_of_gross_profit,
  estimated_round_trip_cost_usdt) compute sensibly without live exchange fee
  data, using only the existing fee/slippage model + planned ATR multiples
- performance-report cost metrics (avg_net_r_after_estimated_cost,
  tiny_win_count, exit_reason_breakdown) compute from a Trade sample that has
  no exact fill-fee data either — only the stored estimate
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.config.settings import settings  # noqa: E402
from agent.orchestrator import _cost_edge_metrics, _cost_edge_gate  # noqa: E402
from agent.strategy.signal import Side  # noqa: E402
from agent.db.models import Trade, get_session  # noqa: E402
from agent.portfolio.performance import build_performance_metrics  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def main():
    settings.max_estimated_cost_r = 0.20
    settings.min_net_ev_after_cost_r = 0.25
    settings.min_expected_reward_cost_multiple = 5
    settings.taker_fee_pct = 0.05
    settings.slippage_pct = 0.03

    row = {"close": 100.0, "atr": 1.0}
    base_params = {
        "atr_mult_sl": 1.5, "atr_mult_tp": 3.0,
        "bankroll_usdt": 1000.0, "max_risk_per_trade_pct": 1.0,
    }

    # --- 1. A thin/high-cost candidate should be rejected even though its
    # raw EV clears the basic min_required_ev_r floor ---
    thin_cost_r = 0.30  # exceeds MAX_ESTIMATED_COST_R
    thin_metrics = _cost_edge_metrics(row, Side.LONG, base_params, thin_cost_r, mtf_ev=0.5)
    thin_reason = _cost_edge_gate(thin_metrics, thin_cost_r)
    check("High estimated-cost candidate is rejected", thin_reason is not None)
    check("Rejection reason mentions estimated cost", thin_reason is not None and "cost" in thin_reason.lower())

    # --- 2. A candidate with fine cost_r but weak net-of-cost EV should also reject ---
    weak_net_cost_r = 0.05
    weak_net_metrics = _cost_edge_metrics(row, Side.LONG, base_params, weak_net_cost_r, mtf_ev=0.20)
    weak_net_reason = _cost_edge_gate(weak_net_metrics, weak_net_cost_r)
    check("Weak net-EV-after-cost candidate is rejected", weak_net_reason is not None)

    # --- 3. A genuinely strong candidate (low cost, high EV, healthy reward:cost) passes ---
    strong_cost_r = 0.05
    strong_metrics = _cost_edge_metrics(row, Side.LONG, base_params, strong_cost_r, mtf_ev=1.5)
    strong_reason = _cost_edge_gate(strong_metrics, strong_cost_r)
    check("Strong candidate clears all three extra gates", strong_reason is None)

    # --- 4. Metrics compute sensibly without any live fill/fee data — only
    # the params snapshot (atr multiples) and the settings fee/slippage model ---
    check("gross_r derived purely from atr_mult_tp/atr_mult_sl", strong_metrics["gross_r"] == 2.0)
    check("net_r_after_estimated_cost = mtf_ev - cost_r", abs(strong_metrics["net_r_after_estimated_cost"] - 1.45) < 1e-6)
    check("cost_as_pct_of_gross_profit computed", strong_metrics["cost_as_pct_of_gross_profit"] > 0)
    check("estimated_round_trip_cost_usdt computed from bankroll+risk_pct, no live fees needed",
          strong_metrics["estimated_round_trip_cost_usdt"] is not None and strong_metrics["estimated_round_trip_cost_usdt"] > 0)
    check("high_cost_trade flag true for the thin-cost candidate", thin_metrics["high_cost_trade"] is True)
    check("high_cost_trade flag false for the strong candidate", strong_metrics["high_cost_trade"] is False)

    # --- 5. Reward-multiple gate: reward must be >= N x cost ---
    borderline_cost_r = 0.10
    borderline_params = dict(base_params, atr_mult_tp=0.4)  # gross_r = 0.4/1.5 ≈ 0.27, far under 5x cost
    borderline_metrics = _cost_edge_metrics(row, Side.LONG, borderline_params, borderline_cost_r, mtf_ev=1.0)
    borderline_reason = _cost_edge_gate(borderline_metrics, borderline_cost_r)
    check("Reward-too-small-vs-cost candidate rejected", borderline_reason is not None and "reward" in borderline_reason.lower())

    # --- 6. Performance-report cost metrics compute from stored estimates only ---
    session = get_session("sqlite:///:memory:")
    now = datetime.utcnow()
    # entry=100, stop=98 -> risk_per_unit=2; exit_price chosen so r_multiple()
    # matches the intended realized R for each scenario.
    for i, (exit_price, pnl, cost_r_val, exit_reason) in enumerate([
        (100.2, 0.20, 0.15, "take_profit"),        # tiny win: +0.1R, cost_r is a big chunk of it
        (98.0, -5.0, 0.05, "stop_loss"),            # -1.0R loss
        (104.0, 8.0, 0.05, "trailing_take_profit"),  # +2.0R win
        (102.0, 3.0, 0.10, "take_profit"),          # +1.0R win
    ]):
        t = Trade(
            symbol="BTC/USDT", side="long", strategy_name="trend_following", regime="trending",
            entry_price=100.0, exit_price=exit_price, qty=1.0, stop_loss=98.0, take_profit=104.0, leverage=3,
            opened_at=now - timedelta(hours=2), closed_at=now - timedelta(hours=1),
        )
        t.set_entry_reasoning([])
        t.set_indicator_snapshot({"estimated_cost_r": cost_r_val})
        t.set_params_snapshot({})
        t.pnl_usdt = pnl
        t.outcome = "win" if pnl > 0 else "loss"
        t.exit_reason = exit_reason
        session.add(t)
    session.commit()

    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=30)
    check("avg_estimated_cost_r computed without live fees", metrics.avg_estimated_cost_r > 0)
    check("avg_net_r_after_estimated_cost is lower than raw expectancy (cost drag visible)",
          metrics.avg_net_r_after_estimated_cost < metrics.expectancy_r)
    check("tiny_win_count counts the +0.20 pnl trade as a tiny win", metrics.tiny_win_count >= 1)
    check("exit_reason_breakdown has take_profit/stop_loss/trailing_take_profit buckets",
          {"take_profit", "stop_loss", "trailing_take_profit"}.issubset(metrics.exit_reason_breakdown.keys()))
    session.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
