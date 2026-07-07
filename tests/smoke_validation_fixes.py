"""Smoke script for the validation-trustworthiness fixes in
agent/portfolio/performance.py + agent/risk/bankroll.py.
Run directly: `python3 tests/smoke_validation_fixes.py`.

Covers the 10 fixes end to end using data shaped like the reported paper
stats (23 trades, 21 closed, ADA's P&L exceeding total P&L, avg net R after
cost negative, sized on a $5,000 testnet equity while BANKROLL_USDT=1000):

- ROI reflects the effective (per-trade snapshotted) bankroll, not the
  static config, when they differ; R-multiple is unaffected by bankroll
- cost-adjusted gate: raw +expectancy but net-after-cost negative => FAIL
- raw expectancy must exceed measured cost, not just clear a fixed floor
- concentration gate: P&L-excluding-best-coin <= 0 => FAIL (the ADA case)
- calendar gate: < required days => not promotable regardless of trade count
- manual reconciliation trades excluded from clean metrics, reported separately
- per-leg: a proven trend_following leg does NOT promote mean_reversion
- recovery tier no longer trips on a 2-loss streak at the new default
- current reported stats classify as NOT READY (PAPER_COLLECTING_DATA-equivalent)
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.db.models import Trade, get_session  # noqa: E402
from agent.portfolio.performance import (  # noqa: E402
    build_performance_metrics, live_readiness, leg_readiness, r_multiple,
)
from agent.risk.bankroll import choose_risk_tier  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def make_settings(**overrides):
    base = dict(
        max_risk_per_trade_pct=1.5,
        risk_tier_mode="auto",
        risk_base_pct=1.0,
        risk_recovery_pct=0.75,
        risk_drawdown_pct=0.5,
        risk_proven_pct=1.5,
        risk_recovery_drawdown_pct=2.0,
        risk_drawdown_trigger_pct=5.0,
        risk_proven_min_trades=50,
        risk_proven_min_expectancy_r=0.15,
        risk_proven_min_net_r_after_cost=0.10,
        risk_proven_min_profit_factor=1.3,
        risk_proven_max_drawdown_pct=8.0,
        risk_proven_min_symbols=3,
        risk_proven_max_top_coin_pct=50.0,
        risk_proven_min_days=30,
        risk_proven_min_trades_per_leg=30,
        risk_recovery_loss_streak_trigger=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def add_trade(session, *, symbol, side, strategy_name, regime, entry, exit_price, qty, stop_loss,
              take_profit, pnl, exit_reason, bankroll_snapshot=None, opened_hours_ago=2, cost_r=0.0):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    t = Trade(
        symbol=symbol, side=side, strategy_name=strategy_name, regime=regime,
        entry_price=entry, exit_price=exit_price, qty=qty, stop_loss=stop_loss,
        take_profit=take_profit, leverage=3,
        opened_at=now - timedelta(hours=opened_hours_ago), closed_at=now - timedelta(hours=opened_hours_ago - 1),
    )
    t.set_entry_reasoning([])
    snap = {"estimated_cost_r": cost_r}
    if bankroll_snapshot is not None:
        snap["effective_bankroll_usdt"] = bankroll_snapshot
    t.set_indicator_snapshot(snap)
    t.set_params_snapshot({})
    t.pnl_usdt = pnl
    t.outcome = "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven")
    t.exit_reason = exit_reason
    session.add(t)
    return t


def test_bankroll_normalization():
    """Fix 1: per-trade snapshotted bankroll drives ROI%, not the static
    config passed in — and R-multiple (stop-distance based) is unaffected."""
    session = get_session("sqlite:///:memory:")
    # $500 profit on a trade actually sized off $5,000 equity = 10% contribution.
    # Passing config bankroll=$1,000 must NOT turn this into a 50% contribution.
    t = add_trade(session, symbol="ADA/USDT", side="long", strategy_name="trend_following", regime="trending",
                  entry=1.0, exit_price=1.1, qty=5000, stop_loss=0.98, take_profit=1.2, pnl=500.0,
                  exit_reason="take_profit", bankroll_snapshot=5000.0)
    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=30)
    check(f"ROI uses the $5,000 snapshot (~10%), not $1,000 config (~50%) — got {metrics.roi_pct:.1f}%",
          abs(metrics.roi_pct - 10.0) < 0.5)
    check("No missing-bankroll-snapshot trades when snapshot is present", metrics.trades_missing_bankroll_snapshot == 0)
    check(f"R-multiple is bankroll-independent (got {r_multiple(t):.2f})", abs(r_multiple(t) - 5.0) < 1e-9)
    session.close()

    # Legacy trade with no snapshot falls back to the passed-in bankroll and is flagged.
    session2 = get_session("sqlite:///:memory:")
    add_trade(session2, symbol="BTC/USDT", side="long", strategy_name="trend_following", regime="trending",
              entry=100.0, exit_price=101.0, qty=1.0, stop_loss=98.0, take_profit=104.0, pnl=1.0,
              exit_reason="take_profit", bankroll_snapshot=None)
    metrics2 = build_performance_metrics(session2, bankroll_usdt=1000.0, days=30)
    check("Legacy trade without a bankroll snapshot is flagged as a fallback", metrics2.trades_missing_bankroll_snapshot == 1)
    session2.close()


def _seed_reported_stats(session):
    """Shapes a sample after the reported paper stats: ADA is the whole
    account's profit, everything else nets negative, cost-adjusted
    expectancy is negative, one manual-reconcile trade, mostly trend/trending."""
    # ADA: the free ride. +48 total across a couple of wins.
    add_trade(session, symbol="ADA/USDT", side="long", strategy_name="trend_following", regime="trending",
              entry=1.0, exit_price=1.10, qty=400, stop_loss=0.97, take_profit=1.15, pnl=40.0,
              exit_reason="take_profit", bankroll_snapshot=5000.0, cost_r=0.10, opened_hours_ago=200)
    add_trade(session, symbol="ADA/USDT", side="long", strategy_name="trend_following", regime="trending",
              entry=1.0, exit_price=1.02, qty=400, stop_loss=0.97, take_profit=1.15, pnl=8.34,
              exit_reason="take_profit", bankroll_snapshot=5000.0, cost_r=0.10, opened_hours_ago=190)
    # Everything else: net losers, so ex-ADA the account is negative.
    for i, (sym, pnl) in enumerate([
        ("SOL/USDT", -3.0), ("XRP/USDT", -2.5), ("DOGE/USDT", -1.8), ("BNB/USDT", -1.2),
        ("LINK/USDT", -1.5), ("DOT/USDT", -1.0), ("AVAX/USDT", -0.9), ("LTC/USDT", -0.87),
    ]):
        add_trade(session, symbol=sym, side="long", strategy_name="trend_following", regime="trending",
                  entry=10.0, exit_price=9.8, qty=5, stop_loss=9.7, take_profit=10.6, pnl=pnl,
                  exit_reason="stop_loss", bankroll_snapshot=5000.0, cost_r=0.13, opened_hours_ago=180 - i * 5)
    # One manual reconciliation trade — must not pollute clean metrics.
    add_trade(session, symbol="ADA/USDT", side="long", strategy_name="trend_following", regime="trending",
              entry=1.0, exit_price=1.0, qty=100, stop_loss=0.97, take_profit=1.15, pnl=500.0,
              exit_reason="manual_reconcile_duplicate", bankroll_snapshot=5000.0, opened_hours_ago=170)


def test_cost_adjusted_gate_and_reconciliation():
    session = get_session("sqlite:///:memory:")
    _seed_reported_stats(session)
    settings = make_settings()
    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=365, settings=settings)

    check(f"Total clean P&L is small/positive (ADA carrying it) — got {metrics.total_pnl_usdt:.2f}", metrics.total_pnl_usdt > 0)
    check(f"Net R after cost is negative on this sample — got {metrics.avg_net_r_after_estimated_cost:.3f}",
          metrics.avg_net_r_after_estimated_cost < 0)

    readiness = live_readiness(metrics, settings, days_elapsed=5)
    check("cost_adjusted_expectancy gate FAILS (net R after cost < required)",
          not readiness["checks"]["cost_adjusted_expectancy"])
    check("Overall readiness is NOT ready", not readiness["ready"])

    # Reconciliation exclusion (Fix 7): the $500 manual trade must not appear
    # in clean metrics but must be visible separately.
    check("Reconciliation trade excluded from clean total P&L (not inflated by +500)",
          metrics.total_pnl_usdt < 100)
    check("Reconciliation trade counted separately", metrics.reconciliation_count == 1)
    check(f"Reconciliation P&L reported separately (+500) — got {metrics.reconciliation_pnl_usdt}",
          abs(metrics.reconciliation_pnl_usdt - 500.0) < 1e-6)
    check("gross_closed_count includes the reconciliation trade", metrics.gross_closed_count == metrics.closed_count + 1)
    session.close()


def test_concentration_gate():
    """Fix 4: P&L excluding the best coin must stay positive to pass — the
    exact ADA scenario the user reported."""
    session = get_session("sqlite:///:memory:")
    _seed_reported_stats(session)
    settings = make_settings()
    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=365, settings=settings)

    check(f"P&L excluding best coin (ADA) is negative — got {metrics.pnl_excluding_best_coin:.2f}",
          metrics.pnl_excluding_best_coin < 0)
    check("Concentration check FAILS", not metrics.concentration_pass)
    check("Concentration reason mentions excluding the best coin", "best coin" in metrics.concentration_reason)

    readiness = live_readiness(metrics, settings, days_elapsed=5)
    check("concentration gate FAILS in live_readiness", not readiness["checks"]["concentration"])
    check("'concentration' listed among failed checks", "concentration" in readiness["failed"])

    # Sanity: a diversified, ex-best-coin-positive sample PASSES concentration.
    session2 = get_session("sqlite:///:memory:")
    for i, sym in enumerate(["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]):
        add_trade(session2, symbol=sym, side="long", strategy_name="trend_following", regime="trending",
                  entry=100.0, exit_price=102.0, qty=1.0, stop_loss=98.0, take_profit=106.0, pnl=10.0 + i,
                  exit_reason="take_profit", bankroll_snapshot=1000.0, opened_hours_ago=10 - i)
    metrics2 = build_performance_metrics(session2, bankroll_usdt=1000.0, days=30, settings=settings)
    check(f"Diversified sample: ex-best-coin P&L still positive — got {metrics2.pnl_excluding_best_coin:.2f}",
          metrics2.pnl_excluding_best_coin > 0)
    check(f"Diversified sample: top coin share <= 50% — got {metrics2.top_coin_contribution_pct:.1f}%",
          metrics2.top_coin_contribution_pct <= 50.0)
    check("Diversified sample passes concentration", metrics2.concentration_pass)
    session2.close()
    session.close()


def test_calendar_gate():
    """Fix 5: even with plenty of trades, promotion is blocked before the
    minimum calendar days have elapsed."""
    session = get_session("sqlite:///:memory:")
    settings = make_settings(risk_proven_min_trades=5, risk_proven_min_expectancy_r=-10,
                              risk_proven_min_net_r_after_cost=-10, risk_proven_min_profit_factor=0,
                              risk_proven_max_drawdown_pct=100, risk_proven_min_symbols=1,
                              risk_proven_max_top_coin_pct=100)
    for i in range(10):
        add_trade(session, symbol="BTC/USDT", side="long", strategy_name="trend_following", regime="trending",
                  entry=100.0, exit_price=102.0, qty=1.0, stop_loss=98.0, take_profit=106.0, pnl=10.0,
                  exit_reason="take_profit", bankroll_snapshot=1000.0, opened_hours_ago=100 - i)
    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=365, settings=settings)

    ready_no_calendar = live_readiness(metrics, settings)  # days_elapsed omitted -> no calendar gate
    check("Without days_elapsed, calendar gate is skipped (backward compatible)",
          "calendar_time" not in ready_no_calendar["checks"])

    ready_5_days = live_readiness(metrics, settings, days_elapsed=5)
    check("At 5 days elapsed (< 30 required), calendar gate FAILS", not ready_5_days["checks"]["calendar_time"])
    check("Overall not ready at 5 days despite otherwise-loose gates", not ready_5_days["ready"])

    ready_31_days = live_readiness(metrics, settings, days_elapsed=31)
    check("At 31 days elapsed, calendar gate PASSES", ready_31_days["checks"]["calendar_time"])
    session.close()


def test_per_leg_readiness():
    """Fix 6: a proven trend_following/trending leg must not promote
    mean_reversion/ranging, which has its own (thin) sample."""
    session = get_session("sqlite:///:memory:")
    settings = make_settings(risk_proven_min_trades_per_leg=20, risk_proven_min_expectancy_r=0.05,
                              risk_proven_min_net_r_after_cost=-1, risk_proven_min_profit_factor=1.0,
                              risk_proven_max_drawdown_pct=100, risk_proven_min_symbols=1,
                              risk_proven_max_top_coin_pct=100)
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "LINK/USDT"]
    for i in range(25):
        add_trade(session, symbol=symbols[i % len(symbols)], side="long", strategy_name="trend_following", regime="trending",
                  entry=100.0, exit_price=103.0, qty=1.0, stop_loss=98.0, take_profit=106.0, pnl=15.0,
                  exit_reason="take_profit", bankroll_snapshot=1000.0, opened_hours_ago=500 - i)
    for i in range(2):
        add_trade(session, symbol="BTC/USDT", side="long", strategy_name="mean_reversion", regime="ranging",
                  entry=100.0, exit_price=103.0, qty=1.0, stop_loss=98.0, take_profit=106.0, pnl=15.0,
                  exit_reason="take_profit", bankroll_snapshot=1000.0, opened_hours_ago=50 - i)

    legs = leg_readiness(session, bankroll_usdt=1000.0, settings=settings, days=1000)
    check("trend_following/trending leg exists with 25 trades",
          "trend_following/trending" in legs and legs["trend_following/trending"]["metrics"].closed_count == 25)
    check("mean_reversion/ranging leg exists with only 2 trades",
          "mean_reversion/ranging" in legs and legs["mean_reversion/ranging"]["metrics"].closed_count == 2)
    check("trend_following/trending leg is ready (enough samples, good expectancy)",
          legs["trend_following/trending"]["readiness"]["ready"])
    check("mean_reversion/ranging leg is NOT ready (2 trades << 20 required) despite the OTHER leg being proven",
          not legs["mean_reversion/ranging"]["readiness"]["ready"])
    check("mean_reversion/ranging fails specifically on sample_size, not some unrelated gate",
          "sample_size" in legs["mean_reversion/ranging"]["readiness"]["failed"])
    session.close()


def test_recovery_streak_denoised():
    """Fix 8: a 2-loss streak (common variance) no longer trips recovery
    sizing at the new default; 3 does."""
    session = get_session("sqlite:///:memory:")
    settings = make_settings()
    for i, pnl in enumerate([-5.0, -3.0]):  # 2-loss streak
        add_trade(session, symbol="BTC/USDT", side="long", strategy_name="trend_following", regime="trending",
                  entry=100.0, exit_price=97.0, qty=1.0, stop_loss=95.0, take_profit=106.0, pnl=pnl,
                  exit_reason="stop_loss", bankroll_snapshot=1000.0, opened_hours_ago=10 - i)
    metrics_2loss = build_performance_metrics(session, bankroll_usdt=1000.0, days=30, settings=settings)
    tier, _, reason = choose_risk_tier(metrics_2loss, settings, days_elapsed=5)
    check(f"2-loss streak does NOT trigger 'recovery' at the new default (got tier={tier})", tier != "recovery")
    session.close()

    session2 = get_session("sqlite:///:memory:")
    for i, pnl in enumerate([-5.0, -3.0, -2.0]):  # 3-loss streak
        add_trade(session2, symbol="BTC/USDT", side="long", strategy_name="trend_following", regime="trending",
                  entry=100.0, exit_price=97.0, qty=1.0, stop_loss=95.0, take_profit=106.0, pnl=pnl,
                  exit_reason="stop_loss", bankroll_snapshot=1000.0, opened_hours_ago=10 - i)
    metrics_3loss = build_performance_metrics(session2, bankroll_usdt=1000.0, days=30, settings=settings)
    tier2, _, _ = choose_risk_tier(metrics_3loss, settings, days_elapsed=5)
    check(f"3-loss streak DOES trigger 'recovery' — got tier={tier2}", tier2 == "recovery")
    session2.close()


def test_reported_stats_are_not_ready():
    """The headline acceptance case: the reported paper stats (net R after
    cost negative, ADA > total P&L, mostly trend/trending, no long track
    record) classify as not ready under the fixed validation."""
    session = get_session("sqlite:///:memory:")
    _seed_reported_stats(session)
    settings = make_settings()
    metrics = build_performance_metrics(session, bankroll_usdt=1000.0, days=365, settings=settings)
    readiness = live_readiness(metrics, settings, days_elapsed=5)

    check("Current reported-shape stats are classified NOT READY", not readiness["ready"])
    check("Fails on cost-adjusted expectancy", "cost_adjusted_expectancy" in readiness["failed"])
    check("Fails on concentration", "concentration" in readiness["failed"])
    check("Fails on calendar time (well under 30 days)", "calendar_time" in readiness["failed"])
    check("Fails on sample size (closed_count << 50)", "sample_size" in readiness["failed"])
    session.close()


def main():
    test_bankroll_normalization()
    test_cost_adjusted_gate_and_reconciliation()
    test_concentration_gate()
    test_calendar_gate()
    test_per_leg_readiness()
    test_recovery_streak_denoised()
    test_reported_stats_are_not_ready()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
