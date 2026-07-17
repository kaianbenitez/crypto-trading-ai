"""Fact-based, deterministic trade narrative: thesis / why-accepted / weakness
/ invalidation / past-context / lesson — used by Telegram, the dashboard, and
the journal so all three read the same way.

No LLM involved anywhere in this module. Every section is composed from
concrete values already stored on the Trade row (indicator_snapshot,
entry_reasoning, params_snapshot) plus a lightweight same-symbol lookback
query, so two trades only read the same when their underlying numbers
actually are the same. This keeps signal generation and execution fully
deterministic — this module only explains what already happened.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timezone

from agent.dashboard.plain_english import simplify_line

# ---------------------------------------------------------------------------
# Reasoning-line classification (matched against the RAW entry_reasoning
# strings, before plain-English translation, since the raw prefixes are
# stable regexes; matched lines are translated afterwards for display).
# ---------------------------------------------------------------------------

_SKIP_RE = re.compile(r"^Regime: ")

_WEAKNESS_RE = re.compile(
    r"^(Structure bias (BEARISH|BULLISH) — confidence reduced"
    r"|Price in (PREMIUM|DISCOUNT) zone"
    r"|Memory: .+ failed \d+x recently"
    r"|News sentiment negative)"
)

_SMC_RE = re.compile(r"^(Near (bullish|bearish) Order Block|(Bullish|Bearish) FVG present|(Bullish|Bearish) liquidity sweep)")

STRATEGY_LABEL = {
    "trend_following": "trend-following",
    "mean_reversion": "mean-reversion",
    "volatility_filter": "volatility standdown",
}


def _strategy_label(name: str) -> str:
    return STRATEGY_LABEL.get(name, (name or "").replace("_", " ") or "unlabeled")


def _split_reasoning(raw_lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Returns (thesis_raw, weakness_raw, smc_raw)."""
    thesis_raw, weakness_raw, smc_raw = [], [], []
    for line in raw_lines:
        if _SKIP_RE.match(line):
            continue
        if _WEAKNESS_RE.match(line):
            weakness_raw.append(line)
        elif _SMC_RE.match(line):
            smc_raw.append(line)
        else:
            thesis_raw.append(line)
    return thesis_raw, weakness_raw, smc_raw


def _coin(symbol: str) -> str:
    return symbol.split("/")[0]


# ---------------------------------------------------------------------------
# Thesis: coin/side/strategy/location specific, not a fixed template
# ---------------------------------------------------------------------------

def _range_location_phrase(side: str, range_position: float | None) -> str | None:
    if range_position is None:
        return None
    if side == "long":
        if range_position >= 0.7:
            return "entry is late — price is already near the upper end of its recent range"
        if range_position <= 0.3:
            return "entry sits in a pullback-like spot near the lower end of its recent range"
        return "entry sits roughly in the middle of its recent range"
    else:
        if range_position <= 0.3:
            return "this is a discount-zone short — chasing weakness after the drop already happened"
        if range_position >= 0.7:
            return "entry is well-located, shorting from a stretched high"
        return "entry sits roughly in the middle of its recent range"


def _thesis_lines(trade, snapshot: dict, thesis_raw: list[str]) -> list[str]:
    coin = _coin(trade.symbol)
    strategy_label = _strategy_label(trade.strategy_name)
    side_word = "long" if trade.side == "long" else "short"

    if trade.strategy_name == "trend_following":
        framing = f"{coin} is a momentum-continuation {side_word}, not a value entry."
    elif trade.strategy_name == "mean_reversion":
        framing = f"{coin} is a mean-reversion {side_word} at a stretched extreme, not a trend-following play."
    else:
        framing = f"{coin} is a {strategy_label} {side_word}."

    parts = [framing]

    location = _range_location_phrase(trade.side, snapshot.get("range_position"))
    mtf_bias = snapshot.get("mtf_bias")
    aligned = None
    if mtf_bias:
        side_bias = "bullish" if trade.side == "long" else "bearish"
        aligned = "MTF is aligned with the trade" if str(mtf_bias).lower() == side_bias else "MTF is mixed against the higher timeframe"

    tail_bits = [b for b in (aligned, location) if b]
    if tail_bits:
        sentence = "; ".join(tail_bits)
        parts.append(sentence[0].upper() + sentence[1:] + ".")
    elif thesis_raw:
        parts.append(simplify_line(thesis_raw[0]))

    return parts[:2]


# ---------------------------------------------------------------------------
# Why accepted: concrete numbers, not adjectives
# ---------------------------------------------------------------------------

def _why_accepted_lines(snapshot: dict) -> list[str]:
    lines = []

    ev = snapshot.get("mtf_ev")
    min_ev = snapshot.get("min_required_ev_r")
    if ev is not None and min_ev is not None:
        margin = ev - min_ev
        if min_ev > 0 and margin / max(min_ev, 1e-9) < 0.25:
            qualifier = "edge is thin, barely cleared the floor"
        elif margin > min_ev:
            qualifier = "edge cleared the cost floor comfortably"
        else:
            qualifier = "edge cleared the cost floor"
        lines.append(f"EV {ev:+.2f}R vs required {min_ev:+.2f}R — {qualifier}.")
    elif ev is not None:
        lines.append(f"EV {ev:+.2f}R.")

    mtf_score = snapshot.get("mtf_score")
    confidence = snapshot.get("confidence")
    score_bits = []
    if mtf_score is not None:
        score_bits.append(f"MTF {mtf_score:.0f}")
    if confidence is not None:
        score_bits.append(f"confidence {confidence:.2f}")
    if score_bits:
        lines.append(", ".join(score_bits) + ".")

    actual_risk = snapshot.get("actual_risk_pct")
    planned_risk = snapshot.get("planned_risk_pct")
    if actual_risk is not None and planned_risk is not None and actual_risk < planned_risk * 0.95:
        tier = snapshot.get("risk_tier")
        if tier in ("recovery", "drawdown"):
            reason = f"the {tier} risk tier is active after recent performance"
        else:
            reason = "the portfolio/same-direction risk cap reduced size (another position is already open)"
        lines.append(f"Risk was reduced to {actual_risk:.2f}% (from {planned_risk:.2f}% planned) because {reason}.")

    atr_ratio = snapshot.get("atr_ratio")
    if atr_ratio is not None and atr_ratio >= 1.5:
        lines.append(f"Volatility is elevated (ATR {atr_ratio:.1f}x baseline) but stayed under the shock-block threshold.")
    elif atr_ratio is not None:
        lines.append("No volatility-shock block triggered.")

    smc_boost = snapshot.get("smc_boost")
    if smc_boost:
        lines.append(f"Extra confluence from order-block/FVG/liquidity-sweep signals added {smc_boost:.2f} to confidence.")

    mfe = snapshot.get("mfe_r")
    mae = snapshot.get("mae_r")
    if mfe is not None or mae is not None:
        mfe_txt = f"{float(mfe):.2f}R" if mfe is not None else "—"
        mae_txt = f"{float(mae):.2f}R" if mae is not None else "—"
        lines.append(f"MFE {mfe_txt} / MAE {mae_txt}.")

    return lines[:3]


# ---------------------------------------------------------------------------
# Weakness: pick the single most relevant concern
# ---------------------------------------------------------------------------

def _weakness_line(trade, snapshot: dict, weakness_raw: list[str]) -> str | None:
    if weakness_raw:
        # Classify on the RAW line (stable prefixes), not the translated text —
        # plain_english's translations intentionally drop words like "premium"/
        # "discount", so matching against them here would never fire.
        raw = weakness_raw[0]
        if "PREMIUM zone" in raw:
            return "Premium-zone entry: this is vulnerable if momentum stalls."
        if "DISCOUNT zone" in raw:
            return "Discount-zone short: vulnerable to a bounce if selling pressure fades."
        if raw.startswith("Structure bias"):
            return "Counter-structure concern: the setup is valid, but the bigger-picture trend disagrees."
        return simplify_line(raw)

    ev = snapshot.get("mtf_ev")
    min_ev = snapshot.get("min_required_ev_r")
    if ev is not None and min_ev is not None and min_ev > 0 and (ev - min_ev) / min_ev < 0.15:
        return "Thin edge: EV barely cleared the cost-aware floor, so there's little room for slippage."

    atr_ratio = snapshot.get("atr_ratio")
    if atr_ratio is not None and atr_ratio >= 1.8:
        return f"Elevated volatility (ATR {atr_ratio:.1f}x baseline) means moves can be bigger and faster than usual."

    return None


def _invalidation_line(strategy_name: str, side: str) -> str:
    opposite = "below" if side == "long" else "above"
    if strategy_name == "trend_following":
        return f"Stop-loss hit, or price closes back {opposite} the trend average / MACD flips against the trade."
    if strategy_name == "mean_reversion":
        return "Stop-loss hit, or price keeps pushing further into the extreme instead of reverting."
    return "Stop-loss hit, or the setup fails to hold its entry level."


# ---------------------------------------------------------------------------
# Past context: real same-symbol sample, not filler
# ---------------------------------------------------------------------------

def _past_context_line(session, symbol: str, exclude_trade_id: int) -> str:
    coin = _coin(symbol)
    if session is None:
        return f"No useful {coin} sample yet."
    from agent.db.models import Trade

    recent = (
        session.query(Trade)
        .filter(Trade.symbol == symbol, Trade.closed_at.isnot(None), Trade.id != exclude_trade_id)
        .order_by(Trade.closed_at.desc())
        .limit(5)
        .all()
    )
    if not recent:
        return f"No useful {coin} sample yet."

    last = recent[0]
    if len(recent) >= 3:
        expectancy = sum(t.pnl_usdt or 0 for t in recent) / len(recent)
        if expectancy < 0:
            return f"Recent {coin} expectancy is negative over the last {len(recent)} trades — size should stay reduced."

    if last.outcome == "win":
        return f"Last {coin} trade won via {(last.exit_reason or 'exit').replace('_', ' ')} — this setup has worked before, but that's one sample."
    if last.outcome == "loss":
        return f"Last {coin} trade stopped out — re-entry required stronger evidence and better timing."
    return f"Last {coin} trade closed roughly breakeven."


def _r_multiple(trade) -> float | None:
    if trade.pnl_usdt is None:
        return None
    # original_qty (full position size) so this matches pnl_usdt, which is
    # computed over the full size — trade.qty alone is reduced by partial
    # fills and would understate the risk denominator.
    full_qty = float(getattr(trade, "original_qty", None) or trade.qty)
    risk = abs(trade.entry_price - trade.stop_loss) * full_qty
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
    why_accepted_lines: list[str] = field(default_factory=list)
    weakness_line: str | None = None
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    rr: float = 0.0
    risk_pct: float | None = None
    risk_usdt: float | None = None
    invalidation_line: str = ""
    past_context_line: str = ""
    # closed-trade only
    outcome: str | None = None
    exit_reason: str | None = None
    exit_price: float | None = None
    pnl_usdt: float | None = None
    r_multiple: float | None = None
    held_duration: str | None = None
    lesson_line: str | None = None
    failure_line: str | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    mfe_price: float | None = None
    mae_price: float | None = None

    # Backward-compatible alias — earlier code/UI referred to this section as
    # "concern"; keep the attribute name usable both ways.
    @property
    def concern_line(self) -> str | None:
        return self.weakness_line


def build_narrative(trade, session=None) -> TradeNarrative:
    snapshot = trade.get_indicator_snapshot()
    raw_reasoning = trade.get_entry_reasoning()
    thesis_raw, weakness_raw, _smc_raw = _split_reasoning(raw_reasoning)

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
        thesis_lines=_thesis_lines(trade, snapshot, thesis_raw),
        why_accepted_lines=_why_accepted_lines(snapshot),
        weakness_line=_weakness_line(trade, snapshot, weakness_raw),
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr=rr,
        risk_pct=risk_pct,
        risk_usdt=risk_usdt,
        invalidation_line=_invalidation_line(trade.strategy_name, trade.side),
        past_context_line=_past_context_line(session, trade.symbol, trade.id),
    )

    if trade.closed_at is not None:
        narrative.outcome = trade.outcome
        narrative.exit_reason = trade.exit_reason
        narrative.exit_price = trade.exit_price
        narrative.pnl_usdt = trade.pnl_usdt
        narrative.r_multiple = _r_multiple(trade)
        narrative.held_duration = _held_duration(trade)
        narrative.mfe_r = snapshot.get("mfe_r")
        narrative.mae_r = snapshot.get("mae_r")
        narrative.mfe_price = snapshot.get("mfe_price")
        narrative.mae_price = snapshot.get("mae_price")

        weakness = narrative.weakness_line
        if trade.outcome == "loss":
            if weakness:
                narrative.failure_line = (
                    f"Stopped out before reaching meaningful profit. This points more to "
                    f"{weakness.split(':', 1)[0].strip().lower()} than a normal trend continuation."
                )
                narrative.lesson_line = (
                    f"Don't treat a strong thesis as enough on its own when {weakness.split(':', 1)[0].strip().lower()} "
                    f"is present — require a stronger edge (higher EV), a better entry, or smaller size."
                )
            elif trade.exit_reason in ("stop_loss", "trailing_stop"):
                narrative.failure_line = "Stopped out before the setup could play out — no specific weakness was flagged at entry."
                narrative.lesson_line = "Treat this as normal strategy variance rather than a pattern to fix."
            else:
                narrative.failure_line = "Closed at a loss without a clear stop-loss trigger — worth a manual look."
                narrative.lesson_line = "Review the exit logic for this trade specifically."
        elif trade.outcome == "win":
            narrative.failure_line = "Trend continuation worked; price followed the thesis and reached target before invalidation."
            if weakness:
                narrative.lesson_line = (
                    f"Worked out despite {weakness.split(':', 1)[0].strip().lower()} — still worth requiring stronger "
                    "confirmation next time this shows up, since it won't always play out this way."
                )
            else:
                narrative.lesson_line = "The setup played out as expected — reinforces this strategy in this kind of market."
        else:
            mfe = trade.get_indicator_snapshot().get("mfe_r")
            mae = trade.get_indicator_snapshot().get("mae_r")
            if mfe is not None or mae is not None:
                mfe_txt = f"{float(mfe):.2f}R" if mfe is not None else "—"
                mae_txt = f"{float(mae):.2f}R" if mae is not None else "—"
                narrative.failure_line = f"Closed roughly breakeven after reaching MFE {mfe_txt} and MAE {mae_txt}."
                narrative.lesson_line = "The trade moved enough to matter, but not enough to justify the final result. Review entry timing and exit management together."
            else:
                narrative.failure_line = "Closed roughly breakeven."
                narrative.lesson_line = "No strong signal either way from this trade."

    return narrative
