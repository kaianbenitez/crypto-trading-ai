"""Template-based dashboard reasoning for open positions."""
from __future__ import annotations


def position_reasoning(trade, current_context: dict | None = None) -> dict:
    context = current_context or {}
    entry_reasoning = trade.get_entry_reasoning()
    thesis = entry_reasoning[:3] or ["Entry passed the strategy checks at execution."]
    pnl = context.get("pnl_pct")
    regime = context.get("regime", trade.regime)
    now = f"Current regime: {regime}."
    if pnl is not None:
        now += f" Position is {pnl:+.2f}% from entry."
    next_plan = "Hold while price respects SL/TP plan; tighten only through trailing rules."
    if context.get("trail_active"):
        next_plan = f"Trailing active near {context.get('stop_loss')}; avoid loosening the stop."
    return {
        "thesis": thesis,
        "now": [now],
        "next": [next_plan],
    }
