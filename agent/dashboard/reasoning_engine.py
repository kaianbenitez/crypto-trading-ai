"""Template-based dashboard reasoning for open positions, written in plain
English for people with little to no trading background."""
from __future__ import annotations

from agent.dashboard.plain_english import friendly_regime, simplify_lines


def position_reasoning(trade, current_context: dict | None = None) -> dict:
    context = current_context or {}
    entry_reasoning = trade.get_entry_reasoning()
    # Every entry always starts with a generic "Regime: ..." line — it's
    # already shown separately as the strategy/regime badge, so the thesis
    # should lead with the actual signal-specific reasons instead, or every
    # trade's thesis would read identically.
    specific_reasoning = [line for line in entry_reasoning if not line.startswith("Regime:")]
    thesis = simplify_lines(specific_reasoning[:3]) or simplify_lines(entry_reasoning[:1]) or ["This trade passed our entry checks when it opened."]
    pnl = context.get("pnl_pct")
    regime = context.get("regime", trade.regime)
    now = f"Market right now: {friendly_regime(regime)}."
    if pnl is not None:
        direction = "up" if pnl >= 0 else "down"
        now += f" This position is {direction} {abs(pnl):.2f}% since it opened."
    next_plan = "Letting it play out — the safety stop and profit target are already set on the exchange."
    if context.get("trail_active"):
        next_plan = (
            f"The safety stop is following the price up to lock in gains (currently near {context.get('stop_loss')}). "
            "It only ever moves in our favor, never back the other way."
        )
    return {
        "thesis": thesis,
        "now": [now],
        "next": [next_plan],
    }
