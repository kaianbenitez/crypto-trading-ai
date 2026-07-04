"""Structured dashboard reasoning for open positions — the same
thesis/concern/invalidation/past-context sections used in the Telegram open
notification, built from agent.dashboard.trade_narrative so both surfaces
stay consistent."""
from __future__ import annotations

from agent.dashboard.trade_narrative import build_narrative


def position_reasoning(trade, current_context: dict | None = None, session=None) -> dict:
    context = current_context or {}
    n = build_narrative(trade, session)

    pnl = context.get("pnl_pct")
    now_lines = []
    if pnl is not None:
        direction = "up" if pnl >= 0 else "down"
        now_lines.append(f"This position is {direction} {abs(pnl):.2f}% since it opened.")

    next_plan = "Letting it play out — the stop-loss and target are already set on the exchange."
    if context.get("trail_active"):
        next_plan = (
            f"The stop-loss is following price up to lock in gains (currently near {context.get('stop_loss')}). "
            "It only ever moves in our favor, never back the other way."
        )

    return {
        "thesis": n.thesis_lines,
        "concern": n.concern_line,
        "invalidation": n.invalidation_line,
        "past_context": n.past_context_line,
        "now": now_lines,
        "next": [next_plan],
    }
