from agent.db.models import Trade
from agent.dashboard.trade_narrative import build_narrative


def generate_postmortem(trade: Trade, session=None) -> list[str]:
    """Deterministic postmortem built from the same structured narrative used
    for Telegram/dashboard. Ties the failure/lesson back to whatever concern
    (e.g. premium-zone entry, counter-trend bias) was flagged at entry instead
    of a generic post-hoc explanation, so the lesson is actually actionable."""
    n = build_narrative(trade, session)
    notes = []
    if n.failure_line:
        notes.append(f"{'Why it failed' if trade.outcome == 'loss' else 'Result'}: {n.failure_line}")
    if n.lesson_line:
        notes.append(f"Lesson: {n.lesson_line}")

    r_txt = f"{n.r_multiple:+.1f}R" if n.r_multiple is not None else "—"
    held_txt = n.held_duration or "—"
    notes.append(f"Stats: Exit reason: {trade.exit_reason or '—'} | R: {r_txt} | Held: {held_txt}")
    return notes
