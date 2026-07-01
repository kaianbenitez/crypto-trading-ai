"""Per-symbol trade memory — rule-based reflection engine.

After each closed trade, generates a structured lesson from the outcome and
indicator snapshot. Stores the last 7 lessons per symbol. Before each new
entry, checks recent lessons for repeated failure patterns and adjusts
signal confidence accordingly.

No LLM used. All pattern matching is deterministic and auditable.
To upgrade to LLM later: swap generate_lesson() to call Claude API.
The rest of the system (storage, signal check) stays identical.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from agent.db.models import TradeMemory, get_session

# How many lessons to keep per symbol
MEMORY_WINDOW = 7

# How many days before a lesson expires (stale market conditions)
LESSON_TTL_DAYS = 14

# How many similar lessons needed before blocking/reducing confidence
# (prevents one news spike from poisoning next trade)
MIN_PATTERN_COUNT = 2


# ---------------------------------------------------------------------------
# Lesson generation (rule-based templates)
# ---------------------------------------------------------------------------

def generate_lesson(trade) -> dict:
    """Analyse a closed trade and return a structured lesson dict.

    Fields:
      text        - human-readable summary shown in dashboard
      patterns    - list of tag strings for pattern matching
      regime      - market regime at entry
      outcome     - win / loss / breakeven
      symbol      - coin
    """
    snap = {}
    try:
        snap = json.loads(trade.indicator_snapshot or "{}")
    except Exception:
        pass

    outcome  = trade.outcome or "unknown"
    side     = trade.side or "unknown"
    regime   = trade.regime or snap.get("regime", "unknown")
    exit_why = trade.exit_reason or "unknown"

    rsi       = snap.get("rsi")
    adx       = snap.get("adx")
    atr_ratio = snap.get("atr_ratio")
    sweep     = snap.get("smc_bull_sweep") or snap.get("smc_bear_sweep")
    fvg       = snap.get("smc_fvg_bull") or snap.get("smc_fvg_bear")
    zone      = snap.get("mc_range_position")  # 0.0–1.0, <0.35 discount, >0.65 premium

    patterns = []
    observations = []

    # --- RSI extremes ---
    if rsi is not None:
        if side == "short" and rsi < 32:
            patterns.append("short_oversold_rsi")
            observations.append(f"shorted when RSI was {rsi:.0f} (oversold) — high bounce risk")
        if side == "long" and rsi > 68:
            patterns.append("long_overbought_rsi")
            observations.append(f"longed when RSI was {rsi:.0f} (overbought) — high pullback risk")

    # --- Chased liquidity sweep ---
    if sweep and outcome == "loss":
        patterns.append("chased_sweep")
        observations.append("entered after a liquidity sweep — price had already moved, likely chasing")

    # --- Wrong zone ---
    if zone is not None:
        if side == "long" and zone > 0.65 and outcome == "loss":
            patterns.append("long_in_premium")
            observations.append(f"longed in premium zone ({zone:.0%} of range) — price was expensive")
        if side == "short" and zone < 0.35 and outcome == "loss":
            patterns.append("short_in_discount")
            observations.append(f"shorted in discount zone ({zone:.0%} of range) — price was cheap")

    # --- Weak trend (low ADX) in trend mode ---
    if adx is not None and regime == "trending" and adx < 22 and outcome == "loss":
        patterns.append("weak_trend_entry")
        observations.append(f"entered trend signal with ADX only {adx:.0f} — trend was too weak")

    # --- ATR shock ---
    if atr_ratio is not None and atr_ratio > 2.0 and outcome == "loss":
        patterns.append("high_atr_entry")
        observations.append(f"entered during ATR spike ({atr_ratio:.1f}× baseline) — volatility was extreme")

    # --- FVG without OB confirmation ---
    if fvg and not snap.get("smc_near_bull_ob") and not snap.get("smc_near_bear_ob") and outcome == "loss":
        patterns.append("fvg_without_ob")
        observations.append("FVG present but no order block confirmation — weaker setup")

    # --- Winning patterns worth remembering ---
    if outcome == "win":
        if sweep and exit_why == "take_profit":
            patterns.append("sweep_entry_worked")
            observations.append("liquidity sweep entry hit TP — this setup is valid on this coin")
        if rsi is not None and 40 <= rsi <= 60 and exit_why == "take_profit":
            patterns.append("neutral_rsi_win")
            observations.append(f"entered with neutral RSI ({rsi:.0f}) and hit TP — clean setup")

    # Build human-readable text
    if not observations:
        if outcome == "win":
            text = f"Trade closed as {exit_why}. No specific pattern flagged — standard setup."
        else:
            text = f"Trade closed as {exit_why}. No specific failure pattern detected — may be random noise."
    else:
        prefix = "Win: " if outcome == "win" else "Loss: "
        text = prefix + " | ".join(observations) + f". Exit: {exit_why}."

    return {
        "text":     text,
        "patterns": patterns,
        "regime":   regime,
        "outcome":  outcome,
        "symbol":   trade.symbol,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def save_lesson(trade, session=None) -> None:
    """Generate and persist a lesson for a closed trade. Prunes old lessons."""
    own_session = session is None
    if own_session:
        session = get_session()

    lesson = generate_lesson(trade)

    record = TradeMemory(
        symbol   = trade.symbol,
        trade_id = trade.id,
        text     = lesson["text"],
        patterns = json.dumps(lesson["patterns"]),
        regime   = lesson["regime"],
        outcome  = lesson["outcome"],
    )
    session.add(record)
    session.commit()

    # Keep only the last MEMORY_WINDOW lessons per symbol
    all_lessons = (
        session.query(TradeMemory)
        .filter(TradeMemory.symbol == trade.symbol)
        .order_by(TradeMemory.created_at.desc())
        .all()
    )
    for old in all_lessons[MEMORY_WINDOW:]:
        session.delete(old)
    session.commit()

    if own_session:
        session.close()


def load_lessons(symbol: str, session=None) -> list[TradeMemory]:
    """Load recent non-expired lessons for a symbol."""
    own_session = session is None
    if own_session:
        session = get_session()

    cutoff = datetime.now(timezone.utc) - timedelta(days=LESSON_TTL_DAYS)
    lessons = (
        session.query(TradeMemory)
        .filter(
            TradeMemory.symbol == symbol,
            TradeMemory.created_at >= cutoff,
        )
        .order_by(TradeMemory.created_at.desc())
        .limit(MEMORY_WINDOW)
        .all()
    )

    if own_session:
        session.close()

    return lessons


# ---------------------------------------------------------------------------
# Signal check — apply memory before entry
# ---------------------------------------------------------------------------

def apply_memory(symbol: str, signal, row, session=None) -> tuple[float, list[str]]:
    """Check recent lessons against the current signal setup.

    Returns:
      confidence_delta  - positive or negative float to add to signal.confidence
      notes             - list of human-readable memory notes for the dashboard
    """
    lessons = load_lessons(symbol, session)
    if not lessons:
        return 0.0, []

    side   = signal.side.value  # "long" or "short"
    regime = str(row.get("regime", "unknown"))
    rsi    = row.get("rsi")
    zone   = row.get("mc_range_position")
    sweep  = row.get("smc_bull_sweep") if side == "long" else row.get("smc_bear_sweep")
    atr_ratio = row.get("mc_atr_ratio")

    # Count how many recent lessons match each failure pattern for this setup
    pattern_counts: dict[str, int] = {}
    for lesson in lessons:
        try:
            tags = json.loads(lesson.patterns or "[]")
        except Exception:
            tags = []
        for tag in tags:
            pattern_counts[tag] = pattern_counts.get(tag, 0) + 1

    delta = 0.0
    notes = []

    def _hit(tag: str) -> bool:
        return pattern_counts.get(tag, 0) >= MIN_PATTERN_COUNT

    # --- Penalise repeated failure patterns ---
    if side == "short" and rsi is not None and rsi < 35 and _hit("short_oversold_rsi"):
        delta -= 0.20
        notes.append(f"Memory: shorted oversold RSI failed {pattern_counts['short_oversold_rsi']}x recently — confidence reduced")

    if side == "long" and rsi is not None and rsi > 65 and _hit("long_overbought_rsi"):
        delta -= 0.20
        notes.append(f"Memory: longed overbought RSI failed {pattern_counts['long_overbought_rsi']}x recently — confidence reduced")

    if sweep and _hit("chased_sweep"):
        delta -= 0.15
        notes.append(f"Memory: chasing sweeps failed {pattern_counts['chased_sweep']}x recently — confidence reduced")

    if zone is not None and side == "long" and zone > 0.65 and _hit("long_in_premium"):
        delta -= 0.15
        notes.append(f"Memory: longing in premium zone failed {pattern_counts['long_in_premium']}x recently")

    if zone is not None and side == "short" and zone < 0.35 and _hit("short_in_discount"):
        delta -= 0.15
        notes.append(f"Memory: shorting in discount zone failed {pattern_counts['short_in_discount']}x recently")

    if regime == "trending" and _hit("weak_trend_entry"):
        delta -= 0.10
        notes.append(f"Memory: weak trend entries failed {pattern_counts['weak_trend_entry']}x recently")

    if atr_ratio is not None and atr_ratio > 2.0 and _hit("high_atr_entry"):
        delta -= 0.15
        notes.append(f"Memory: high ATR entries failed {pattern_counts['high_atr_entry']}x recently")

    # --- Boost patterns that have been winning ---
    if sweep and _hit("sweep_entry_worked"):
        delta += 0.10
        notes.append(f"Memory: sweep entries worked {pattern_counts['sweep_entry_worked']}x recently — confidence boosted")

    # Cap delta so memory can't single-handedly approve or kill a trade
    delta = max(-0.40, min(0.20, delta))

    return delta, notes
