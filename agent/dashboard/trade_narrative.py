"""Structured, deterministic trade narrative: thesis / concern / plan /
invalidation / past-context / lesson — used by Telegram, the dashboard, and
the journal so all three read the same way.

No LLM involved anywhere in this module — every section is built from data
already stored on the Trade row (indicator_snapshot, entry_reasoning,
params_snapshot, postmortem) plus a lightweight same-symbol lookback query.
This keeps signal generation and execution fully deterministic; this module
only formats what already happened.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timezone

from agent.dashboard.plain_english import friendly_regime, friendly_strategy, simplify_line

# ---------------------------------------------------------------------------
# Reasoning-line classification (matched against the RAW entry_reasoning
# strings, before plain-English translation, since the raw prefixes are
# stable regexes; the matched lines are translated afterwards for display).
# ---------------------------------------------------------------------------

_SKIP_RE = re.compile(r"^Regime: ")

_CONCERN_RE = re.compile(
    r"^(Structure bias (BEARISH|BULLISH) — confidence reduced"
    r"|Price in (PREMIUM|DISCOUNT) zone"
    r"|Memory: .+ failed \d+x recently"
    r"|News sentiment negative)"
)

# Anything not skipped and not a concern is treated as supportive of the thesis.


def _split_reasoning(raw_lines: list[str]) -> tuple[list[str], list[str]]:
    thesis_raw, concern_raw = [], []
    for line in raw_lines:
        if _SKIP_RE.match(line):
            continue
        if _CONCERN_RE.match(line):
            concern_raw.append(line)
        else:
            thesis_raw.append(line)
    return thesis_raw, concern_raw


def _invalidation_line(strategy_name: str, side: str) -> str:
    direction = "above" if side == "long" else "below"
    opposite = "below" if side == "long" else "above"
    if strategy_name == "trend_following":
        return f"Stop-loss hit, or price closes back {opposite} the trend average / MACD flips against the trade."
    if strategy_name == "mean_reversion":
        return "Stop-loss hit, or price keeps pushing further into the extreme instead of reverting."
    return f"Stop-loss hit, or price fails to hold {direction} the entry level."


def _last_same_symbol_context(session, symbol: str, exclude_trade_id: int) -> str | None:
    if session is None:
        return None
    from agent.db.models import Trade

    last = (
        session.query(Trade)
        .filter(Trade.symbol == symbol, Trade.closed_at.isnot(None), Trade.id != exclude_trade_id)
        .order_by(Trade.closed_at.desc())
        .first()
    )
    if not last:
        return None

    coin = symbol.split("/")[0]
    if last.outcome == "win":
        return f"Last {coin} trade won via {(last.exit_reason or 'exit').replace('_', ' ')} — this setup has worked before."
    if last.outcome == "loss":
        return f"Last {coin} trade stopped out — re-entry needs stronger evidence and better timing."
    return None


def _r_multiple(trade) -> float | None:
    if trade.pnl_usdt is None:
        return None
    risk = abs(trade.entry_price - trade.stop_loss) * trade.qty
    if risk <= 0:
        return None
    return trade.pnl_usdt / risk


def _held_duration(trade) -> str | None:
    if not trade.opened_at or not trade.closed_at:
        return None
    opened, closed = trade.opened_at, trade.closed_at
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    if closed.tzinfo is None:
        closed = closed.replace(tzinfo=timezone.utc)
    minutes = (closed - opened).total_seconds() / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


@dataclass
class TradeNarrative:
    symbol: str
    side: str
    strategy_name: str
    regime: str
    confidence: float | None
    ev_r: float | None
    thesis_lines: list[str] = field(default_factory=list)
    concern_line: str | None = None
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    rr: float = 0.0
    risk_pct: float | None = None
    risk_usdt: float | None = None
    invalidation_line: str = ""
    past_context_line: str | None = None
    # closed-trade only
    outcome: str | None = None
    exit_reason: str | None = None
    exit_price: float | None = None
    pnl_usdt: float | None = None
    r_multiple: float | None = None
    held_duration: str | None = None
    lesson_line: str | None = None
    failure_line: str | None = None


def build_narrative(trade, session=None) -> TradeNarrative:
    snapshot = trade.get_indicator_snapshot()
    raw_reasoning = trade.get_entry_reasoning()
    thesis_raw, concern_raw = _split_reasoning(raw_reasoning)

    thesis_lines = [simplify_line(line) for line in thesis_raw[:2]] or [
        f"{friendly_strategy(trade.strategy_name)} setup in a {friendly_regime(trade.regime)} market."
    ]
    concern_line = simplify_line(concern_raw[0]) if concern_raw else None

    entry = trade.entry_price
    stop_loss = trade.stop_loss
    take_profit = trade.take_profit
    rr = abs(take_profit - entry) / max(abs(entry - stop_loss), 1e-9)

    risk_pct = snapshot.get("actual_risk_pct", snapshot.get("planned_risk_pct"))
    risk_usdt = snapshot.get("actual_risk_usdt", snapshot.get("planned_risk_usdt"))

    narrative = TradeNarrative(
        symbol=trade.symbol,
        side=trade.side,
        strategy_name=trade.strategy_name,
        regime=trade.regime,
        confidence=snapshot.get("confidence"),
        ev_r=snapshot.get("mtf_ev"),
        thesis_lines=thesis_lines,
        concern_line=concern_line,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=rr,
        risk_pct=risk_pct,
        risk_usdt=risk_usdt,
        invalidation_line=_invalidation_line(trade.strategy_name, trade.side),
        past_context_line=_last_same_symbol_context(session, trade.symbol, trade.id),
    )

    if trade.closed_at is not None:
        narrative.outcome = trade.outcome
        narrative.exit_reason = trade.exit_reason
        narrative.exit_price = trade.exit_price
        narrative.pnl_usdt = trade.pnl_usdt
        narrative.r_multiple = _r_multiple(trade)
        narrative.held_duration = _held_duration(trade)

        if trade.outcome == "loss":
            if concern_line:
                narrative.failure_line = (
                    f"Price hit the stop before the setup could play out. This looks more like "
                    f"{concern_line.rstrip('.').lower()} risk than a normal pullback."
                )
                narrative.lesson_line = (
                    f"Don't treat a strong thesis as enough on its own when {concern_line.rstrip('.').lower()} — "
                    f"require a stronger edge (higher EV), a better entry, or smaller size in that situation."
                )
            elif trade.exit_reason == "stop_loss":
                narrative.failure_line = "Price hit the stop-loss before moving favorably — the setup didn't play out as expected."
                narrative.lesson_line = "No specific weakness was flagged at entry — treat this as normal strategy variance rather than a pattern to fix."
            else:
                narrative.failure_line = "This trade closed at a loss without a clear stop-loss trigger — worth a manual look."
                narrative.lesson_line = "Review the exit logic for this trade specifically."
        elif trade.outcome == "win":
            narrative.failure_line = None
            if concern_line:
                narrative.lesson_line = (
                    f"Worked out despite {concern_line.rstrip('.').lower()} — still worth requiring stronger "
                    "confirmation next time this concern shows up, since it won't always play out this way."
                )
            else:
                narrative.lesson_line = "The setup played out as expected — reinforces this strategy in this kind of market."
        else:
            narrative.failure_line = "Closed roughly breakeven."
            narrative.lesson_line = "No strong signal either way from this trade."

    return narrative
