"""Macro regime awareness — size-only risk adjustment.

Checks two signals:
  1. Fear & Greed Index (alternative.me API — free, no key needed)
  2. BTC funding rate (exchange API — crowded long/short detection)

Returns a MacroState that the orchestrator uses to reduce position sizes
during extreme conditions. Direction (long/short blocking) is fully
delegated to MTF confluence and market structure filters.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Fear & Greed thresholds
EXTREME_FEAR_THRESHOLD  = 20   # index 0-100, below = extreme fear
EXTREME_GREED_THRESHOLD = 80   # above = extreme greed

# Funding rate thresholds (annualised %)
FUNDING_CROWDED_LONG  =  0.10  # >+10% annualised = crowded longs
FUNDING_CROWDED_SHORT = -0.10  # <-10% annualised = crowded shorts

# Position size multipliers per regime
SIZE_MULTIPLIERS = {
    "normal":        1.00,
    "extreme_fear":  0.60,   # reduce size — capitulation possible but also reversal
    "extreme_greed": 0.50,   # reduce size — euphoria = blow-off top risk
    "crowded_long":  0.70,   # longs crowded — reduce size
    "crowded_short": 0.70,   # shorts crowded — reduce size
    "risk_off":      0.40,   # extreme sentiment + crowded funding — minimal size
}


@dataclass
class MacroState:
    fear_greed:        int   = 50      # 0-100
    funding_rate_pct:  float = 0.0     # annualised %
    regime:            str   = "normal"
    size_multiplier:   float = 1.0
    notes:             list  = field(default_factory=list)


def fetch_fear_greed() -> int | None:
    """Fetch Fear & Greed index from alternative.me. Returns 0-100 or None."""
    try:
        import requests
        r = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=8,
        )
        data = r.json()
        return int(data["data"][0]["value"])
    except Exception as e:
        log.warning(f"Fear & Greed fetch failed: {e}")
        return None


def fetch_funding_rate(adapter, symbol: str = "BTC/USDT") -> float | None:
    """Fetch latest funding rate for BTC from the exchange. Returns annualised %."""
    try:
        # ccxt standard: fetch_funding_rate
        fr = adapter._client.fetch_funding_rate(symbol)
        rate = float(fr.get("fundingRate") or 0)
        # Funding is per 8h — annualise: × 3 × 365
        return rate * 3 * 365 * 100
    except Exception as e:
        log.warning(f"Funding rate fetch failed: {e}")
        return None


def assess_macro(adapter=None) -> MacroState:
    """Build current MacroState from all available sources."""
    state = MacroState()
    notes = []

    # Fear & Greed
    fg = fetch_fear_greed()
    if fg is not None:
        state.fear_greed = fg
        if fg <= EXTREME_FEAR_THRESHOLD:
            notes.append(f"Extreme Fear ({fg}) — reducing size only (direction left to MTF/structure)")
            state.regime = "extreme_fear"
        elif fg >= EXTREME_GREED_THRESHOLD:
            notes.append(f"Extreme Greed ({fg}) — reducing size only (direction left to MTF/structure)")
            state.regime = "extreme_greed"

    # Funding rate — size reduction only, no directional blocks
    if adapter:
        fr = fetch_funding_rate(adapter)
        if fr is not None:
            state.funding_rate_pct = fr
            if fr > FUNDING_CROWDED_LONG * 100:
                notes.append(f"Crowded longs (funding {fr:+.1f}% pa) — reducing size")
                if state.regime == "normal":
                    state.regime = "crowded_long"
            elif fr < FUNDING_CROWDED_SHORT * 100:
                notes.append(f"Crowded shorts (funding {fr:+.1f}% pa) — reducing size")
                if state.regime == "normal":
                    state.regime = "crowded_short"

    # Combined caution: extreme sentiment AND crowded funding
    if state.regime in ("extreme_fear", "extreme_greed") and abs(state.funding_rate_pct) > abs(FUNDING_CROWDED_LONG * 100):
        state.regime = "risk_off"
        notes.append("Risk-off: extreme sentiment + crowded funding — minimal size")

    state.size_multiplier = SIZE_MULTIPLIERS.get(state.regime, 1.0)
    state.notes = notes

    if notes:
        log.info(f"Macro: {state.regime} | size_mult={state.size_multiplier:.2f} | " + " | ".join(notes))

    return state
