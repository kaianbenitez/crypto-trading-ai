"""Reconcile closed DB trades against Binance account fills.

Use after exchange-side SL/TP closes a position but the orchestrator recorded
the latest candle close instead of the actual fill price.

Dry run:
  PYTHONPATH=. python reconcile_trade_fills.py

Apply:
  PYTHONPATH=. python reconcile_trade_fills.py --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from agent.db.models import Trade, get_session
from agent.exchange.binance_futures import BinanceFuturesAdapter


def classify(side: str, entry: float, exit_price: float) -> tuple[float, str, str]:
    direction = 1 if side == "long" else -1
    move = (exit_price - entry) * direction
    outcome = "win" if move > 0 else "loss" if move < 0 else "breakeven"
    exit_reason = "take_profit" if move > 0 else "stop_loss" if move < 0 else "breakeven"
    return move, outcome, exit_reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write reconciled prices/PnL to DB")
    args = parser.parse_args()

    session = get_session()
    adapter = BinanceFuturesAdapter()
    trades = (
        session.query(Trade)
        .filter(Trade.closed_at.isnot(None))
        .order_by(Trade.closed_at.desc())
        .all()
    )

    changed = 0
    for trade in trades:
        fill = adapter.get_exit_fill(trade.symbol, trade.side, trade.opened_at, trade.qty)
        if not fill:
            print(f"{trade.id} {trade.symbol}: no exchange fill found")
            continue

        exit_price = float(fill["price"])
        move, outcome, exit_reason = classify(trade.side, trade.entry_price, exit_price)
        pnl = move * trade.qty
        delta = abs((trade.exit_price or 0) - exit_price)

        print(
            f"{trade.id} {trade.symbol} {trade.side}: "
            f"db_exit={trade.exit_price} fill_exit={exit_price:.6f} "
            f"db_pnl={trade.pnl_usdt} fill_pnl={pnl:.2f} {outcome}"
        )

        if args.apply and delta > 0:
            trade.exit_price = exit_price
            trade.pnl_usdt = pnl
            trade.outcome = outcome
            trade.exit_reason = exit_reason
            trade.closed_at = trade.closed_at or datetime.now(timezone.utc)
            changed += 1

    if args.apply:
        session.commit()
        print(f"Updated {changed} trade(s)")
    else:
        print("Dry run only. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
