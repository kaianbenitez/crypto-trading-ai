"""Trading cost helpers used by live gates and backtests."""
from __future__ import annotations


def estimate_round_trip_cost_r(
    entry_price: float,
    stop_loss: float,
    take_profit: float | None = None,
    taker_fee_pct: float = 0.05,
    slippage_pct: float = 0.03,
) -> float:
    """Estimate all-in round-trip cost expressed in initial R.

    The bot enters with market orders and exits with market-triggered SL/TP
    orders, so this uses a taker-style cost on both sides. Slippage is an
    explicit extra estimate, not an exchange fee.
    """
    entry_price = float(entry_price or 0)
    stop_loss = float(stop_loss or 0)
    take_profit = float(take_profit or entry_price or 0)
    risk_per_unit = abs(entry_price - stop_loss)
    if entry_price <= 0 or risk_per_unit <= 0:
        return 0.0

    per_side_cost = (float(taker_fee_pct) + float(slippage_pct)) / 100
    return ((entry_price + take_profit) * per_side_cost) / risk_per_unit

