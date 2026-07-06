"""Smoke script for realized-PnL accounting across partial fills.
Run directly: `python3 tests/smoke_pnl_accounting.py`.

Real bug this guards against: a partial TP fill reduces `trade.qty` to the
remaining size (needed so trailing-stop/force-close orders are sized
correctly), but the final PnL calc used to multiply the exit price delta by
that same reduced `trade.qty` — silently dropping all PnL already realized
on the filled portion. Fix: `original_qty` preserves the true full size,
and both the final PnL calc and get_exit_fill's expected_qty use it.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.exchange.binance_futures import BinanceFuturesAdapter  # noqa: E402
from agent.dashboard.trade_narrative import _r_multiple  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def test_full_qty_pnl_matches_sum_of_legs():
    """The core bug: PnL over the full original size must equal the sum of
    each fill leg's individual PnL, not just the final leg's."""
    entry_price = 100.0
    direction = 1  # long

    # Leg 1: partial TP fills 6 units at 110 (locked-in profit).
    # Leg 2: remaining 4 units later stop out at 95 (a loss).
    original_qty = 10.0
    leg1_qty, leg1_price = 6.0, 110.0
    leg2_qty, leg2_price = 4.0, 95.0

    true_total_pnl = (leg1_price - entry_price) * direction * leg1_qty + (leg2_price - entry_price) * direction * leg2_qty

    # Blended average exit price, weighted by each leg's qty (what
    # get_exit_fill computes from real account trades).
    avg_exit_price = (leg1_qty * leg1_price + leg2_qty * leg2_price) / original_qty

    # Fixed formula: raw_pnl over the FULL original qty.
    fixed_pnl = (avg_exit_price - entry_price) * direction * original_qty
    check(f"Fixed formula matches true blended PnL ({fixed_pnl:.2f} == {true_total_pnl:.2f})", abs(fixed_pnl - true_total_pnl) < 1e-9)

    # The bug: using the REDUCED qty (post partial-fill reconciliation) with
    # only the final leg's price silently drops leg 1's realized profit.
    buggy_pnl = (leg2_price - entry_price) * direction * leg2_qty  # reduced qty, final price only
    check(f"Buggy formula understates true PnL ({buggy_pnl:.2f} != {true_total_pnl:.2f})", abs(buggy_pnl - true_total_pnl) > 1e-9)
    check("Buggy formula specifically drops leg 1's +60 profit", abs((true_total_pnl - buggy_pnl) - 60.0) < 1e-9)


class FakeCcxtClient:
    def __init__(self, trades):
        self._trades = trades

    def fetch_my_trades(self, symbol, since=None, limit=50):
        return self._trades


def test_get_exit_fill_aggregates_all_legs_when_given_full_qty():
    """get_exit_fill must be called with the FULL original qty as
    expected_qty, or it stops accumulating fills too early and only
    captures the first leg instead of the whole exit."""
    from datetime import datetime, timezone

    trades = [
        {"side": "sell", "amount": 6.0, "price": 110.0, "order": "tp-order"},
        {"side": "sell", "amount": 4.0, "price": 95.0, "order": "sl-order"},
    ]
    adapter = BinanceFuturesAdapter.__new__(BinanceFuturesAdapter)
    adapter._client = FakeCcxtClient(trades)

    opened_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    full_result = adapter.get_exit_fill("BTC/USDT", "long", opened_at, expected_qty=10.0)
    check("Full expected_qty aggregates both legs", full_result is not None and abs(full_result["qty"] - 10.0) < 1e-9)
    expected_avg = (6.0 * 110.0 + 4.0 * 95.0) / 10.0
    check(f"Aggregated price is the qty-weighted average ({full_result['price']:.2f} == {expected_avg:.2f})", abs(full_result["price"] - expected_avg) < 1e-6)

    # Demonstrates the bug scenario: passing the REDUCED qty (as trade.qty
    # would be post partial-fill reconciliation) truncates to only leg 1.
    truncated_result = adapter.get_exit_fill("BTC/USDT", "long", opened_at, expected_qty=4.0)
    check("Reduced expected_qty truncates to the wrong leg (leg 1 only, not leg 2)", truncated_result is not None and abs(truncated_result["price"] - 110.0) < 1e-6)


def test_r_multiple_uses_original_qty():
    trade = SimpleNamespace(
        entry_price=100.0, stop_loss=98.0, side="long",
        qty=4.0,             # reduced by a partial fill
        original_qty=10.0,   # true full size
        pnl_usdt=40.0,       # realized over the full size after the fix
    )
    r = _r_multiple(trade)
    # risk over full size = (100-98)*10 = 20; R = 40/20 = 2.0
    check(f"R-multiple uses original_qty as the risk denominator (got {r})", r is not None and abs(r - 2.0) < 1e-9)

    # No original_qty attribute at all — legacy trade predating the column.
    trade_no_original = SimpleNamespace(entry_price=100.0, stop_loss=98.0, side="long", qty=10.0, pnl_usdt=20.0)
    r2 = _r_multiple(trade_no_original)
    check("Falls back to qty when original_qty is absent (legacy trades)", r2 is not None and abs(r2 - 1.0) < 1e-9)


def main():
    test_full_qty_pnl_matches_sum_of_legs()
    test_get_exit_fill_aggregates_all_legs_when_given_full_qty()
    test_r_multiple_uses_original_qty()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
