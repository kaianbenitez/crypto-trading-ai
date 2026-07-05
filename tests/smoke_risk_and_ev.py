"""Smoke script for the recalibrated EV model and risk-engine hardening.
Run directly: `python3 tests/smoke_risk_and_ev.py`.

Verifies:
- EV is expressed in true R and neutral confluence no longer clears the floor
- realized-outcome calibration blends into the win probability
- confidence-scaled sizing reduces (never increases) risk
- daily drawdown: net mode, UTC day roll, export/restore across "restarts"
- breakeven uses the actual initial stop when provided
- mean reversion single-condition tier requires volume confirmation
- trailing manager restores the old stop when placing the new one fails
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from agent.risk.engine import RiskEngine  # noqa: E402
from agent.risk.trailing_stop_manager import TrailingStopManager  # noqa: E402
from agent.strategy.signal import Side  # noqa: E402
from agent.strategy.mean_reversion import mean_reversion_signal  # noqa: E402
from agent.strategy import mtf_scorer  # noqa: E402
from agent.backtest.engine import SimpleSettings  # noqa: E402
from agent.config.settings import settings as live_settings  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def make_settings(**overrides):
    base = dict(
        bankroll_usdt=1000.0,
        max_risk_per_trade_pct=1.0,
        max_daily_drawdown_pct=3.0,
        max_concurrent_positions=2,
        max_portfolio_risk_pct=1.5,
        max_same_direction_risk_pct=1.0,
        min_entry_risk_pct=0.25,
        min_stop_cost_multiple=0.0,
        taker_fee_pct=0.05,
        slippage_pct=0.03,
        default_leverage=3,
        max_leverage=5,
        daily_drawdown_mode="net",
        confidence_risk_scaling=True,
        confidence_full_risk_at=0.6,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_simple_settings_matches_orchestrator_construction():
    """Regression guard: the orchestrator builds SimpleSettings by forwarding
    every field straight off the live Settings object. If SimpleSettings is
    ever missing a kwarg the orchestrator passes, this call crashes at
    startup on every boot (real incident: daily_drawdown_mode /
    confidence_risk_scaling / confidence_full_risk_at were added to Settings
    and the live construction call but not to SimpleSettings itself)."""
    try:
        SimpleSettings(
            bankroll_usdt=live_settings.bankroll_usdt,
            max_risk_per_trade_pct=live_settings.max_risk_per_trade_pct,
            max_daily_drawdown_pct=live_settings.max_daily_drawdown_pct,
            max_concurrent_positions=live_settings.max_concurrent_positions,
            max_portfolio_risk_pct=live_settings.max_portfolio_risk_pct,
            max_same_direction_risk_pct=live_settings.max_same_direction_risk_pct,
            min_entry_risk_pct=live_settings.min_entry_risk_pct,
            min_stop_cost_multiple=live_settings.min_stop_cost_multiple,
            taker_fee_pct=live_settings.taker_fee_pct,
            slippage_pct=live_settings.slippage_pct,
            default_leverage=live_settings.default_leverage,
            max_leverage=live_settings.max_leverage,
            daily_drawdown_mode=live_settings.daily_drawdown_mode,
            confidence_risk_scaling=live_settings.confidence_risk_scaling,
            confidence_full_risk_at=live_settings.confidence_full_risk_at,
        )
        ok = True
    except TypeError:
        ok = False
    check("SimpleSettings accepts every kwarg the orchestrator forwards from Settings", ok)


def test_ev_model():
    # Neutral confluence must NOT clear the EV floor anymore.
    p_neutral = mtf_scorer.win_prob(50.0)
    rr = 3.0 / 1.5
    ev_neutral = p_neutral * rr - (1 - p_neutral)
    check(f"Neutral score 50 -> win prob {p_neutral:.2f} (conservative)", p_neutral < 0.40)
    check(f"Neutral EV {ev_neutral:+.2f}R is below the 0.25R floor", ev_neutral < 0.25)

    p_strong = mtf_scorer.win_prob(75.0)
    ev_strong = p_strong * rr - (1 - p_strong)
    check(f"Strong score 75 -> EV {ev_strong:+.2f}R clears the floor", ev_strong >= 0.25)
    check("Win prob is monotonic in score", mtf_scorer.win_prob(70) > mtf_scorer.win_prob(55) > mtf_scorer.win_prob(40))

    # Calibration blending: a bucket with a terrible realized record drags p down.
    calib = {"buckets": {70: {"n": 50, "wins": 5}}, "total": 50}
    p_raw = mtf_scorer.win_prob(72.0)
    p_cal = mtf_scorer.win_prob(72.0, calib)
    check(f"Bad realized record (5/50 wins) drags win prob down ({p_raw:.2f} -> {p_cal:.2f})", p_cal < p_raw)
    # And a small sample only nudges it.
    calib_small = {"buckets": {70: {"n": 3, "wins": 0}}, "total": 3}
    p_small = mtf_scorer.win_prob(72.0, calib_small)
    check("Thin sample (3 trades) only nudges the prior", abs(p_small - p_raw) < abs(p_cal - p_raw))


def test_confidence_scaling():
    risk = RiskEngine(make_settings())
    full = risk.plan_trade("BTC/USDT", Side.LONG, 100.0, 1.0, confidence=0.7)
    low = risk.plan_trade("ETH/USDT", Side.LONG, 100.0, 1.0, confidence=0.3)
    check("Full risk at confidence >= 0.6", abs(full.risk_pct - 1.0) < 1e-9)
    check(f"Half confidence -> reduced risk ({low.risk_pct:.2f}% < 1.0%)", low.risk_pct < 1.0)
    check("Scaled risk floored at min entry risk", low.risk_pct >= 0.25)
    no_conf = risk.plan_trade("SOL/USDT", Side.SHORT, 100.0, 1.0)
    check("No confidence given -> unscaled", abs(no_conf.risk_pct - 1.0) < 1e-9)


def test_daily_drawdown():
    # Net mode: a green day absorbs a loss without tripping the switch.
    risk = RiskEngine(make_settings())
    risk.record_trade_result(+50.0)
    risk.record_trade_result(-40.0)
    check("Net mode: -40 after +50 does not trip 3% kill on $1000", not risk.kill_switch_active)
    risk.record_trade_result(-45.0)  # net now -35, still above -30 limit
    check("Net mode: net -35 >= $30 limit trips the switch", risk.kill_switch_active)

    # losses_only mode: gross losses trip it even when net positive.
    strict = RiskEngine(make_settings(daily_drawdown_mode="losses_only"))
    strict.record_trade_result(+100.0)
    strict.record_trade_result(-35.0)
    check("losses_only: gross -35 trips despite net +65", strict.kill_switch_active)

    # Export/restore across a simulated restart.
    day = risk.export_day_state()
    fresh = RiskEngine(make_settings())
    check("Fresh engine starts un-killed", not fresh.kill_switch_active)
    fresh.restore_day_state(day)
    check("Restored engine keeps today's kill switch", fresh.kill_switch_active)
    stale = dict(day, daily_date="2020-01-01")
    fresh2 = RiskEngine(make_settings())
    fresh2.restore_day_state(stale)
    check("Stale (old-day) state is ignored", not fresh2.kill_switch_active)


def test_breakeven_initial_stop():
    risk = RiskEngine(make_settings())
    # Entry 100, actual initial stop 98 (2 wide). Current ATR says stop should
    # be 1.5 wide — without initial_stop, BE would arm too early at 101.5.
    armed_actual = risk.check_breakeven(Side.LONG, 100.0, 101.6, atr=1.0, initial_stop=98.0)
    check("BE not armed at +1.6 when true risk is 2.0", armed_actual is None)
    armed_now = risk.check_breakeven(Side.LONG, 100.0, 102.1, atr=1.0, initial_stop=98.0)
    check("BE armed once profit >= actual initial risk", armed_now is not None)


def test_mean_reversion_vol_gate():
    # RSI oversold but price NOT at the lower band -> single-condition setup.
    base = {"rsi": 30.0, "close": 10.0, "bb_lower": 9.0, "bb_upper": 12.0}
    prev = pd.Series(base)
    no_vol = pd.Series({**base, "vol_confirmed": False})
    with_vol = pd.Series({**base, "vol_confirmed": True})
    sig_no_vol = mean_reversion_signal(no_vol, prev, {})
    sig_vol = mean_reversion_signal(with_vol, prev, {})
    check("Single-condition MR without volume is skipped", sig_no_vol.side == Side.NONE)
    check("Single-condition MR with volume still fires", sig_vol.side == Side.LONG)


class FailThenRestoreAdapter:
    """place_stop_loss fails on the first (trail) call, succeeds on restore."""

    def __init__(self):
        self.calls = []

    def cancel_order(self, symbol, order_id):
        self.calls.append(("cancel", order_id))

    def place_stop_loss(self, symbol, side, qty, price):
        self.calls.append(("place", price))
        if len([c for c in self.calls if c[0] == "place"]) == 1:
            raise ConnectionError("simulated exchange failure")
        return SimpleNamespace(order_id="restored-123")


def test_trailing_restore():
    adapter = FailThenRestoreAdapter()
    mgr = TrailingStopManager(adapter, session=None, tg_fn=None)
    trade = SimpleNamespace(
        id=1, symbol="BTC/USDT", side="long", entry_price=100.0,
        stop_loss=98.0, qty=1.0, strategy_name="trend_following", regime="trending",
    )
    state = SimpleNamespace(sl_order_id="old-order")
    rows = [{"open": 100, "high": 106, "low": 99, "close": 106, "volume": 10, "atr": 1.0, "timestamp": i} for i in range(40)]
    df = pd.DataFrame(rows)
    result = mgr.maybe_update(trade, state, df, params={"trail_activation_r": 1.0, "trail_atr_mult": 2.2})
    check("Trail move reports not-moved after placement failure", not result.moved)
    check("Old stop restored on the exchange", ("place", 98.0) in adapter.calls)
    check("State points at the restore order", state.sl_order_id == "restored-123")
    check("DB stop_loss not advanced past reality", trade.stop_loss == 98.0)


def main():
    test_simple_settings_matches_orchestrator_construction()
    test_ev_model()
    test_confidence_scaling()
    test_daily_drawdown()
    test_breakeven_initial_stop()
    test_mean_reversion_vol_gate()
    test_trailing_restore()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
