"""Swing market structure — Break of Structure (BOS) / Change of Character
(CHoCH) detection, ported from LuxAlgo's "Smart Money Concepts" Pine Script
indicator (CC BY-NC-SA 4.0, https://creativecommons.org/licenses/by-nc-sa/4.0/,
private-use in this bot — not redistributed).

Only the swing-structure detection logic is ported (leg/pivot detection and
BOS/CHoCH break detection, ~80 lines of the original 848). The order-block,
fair-value-gap, equal-highs/lows, and premium/discount-zone parts of the
original indicator are chart-drawing features for a TradingView chart —
out of scope for a status line/signal read, and not ported here.

Operates on plain OHLC candles (the same 1h data already fetched for every
open position elsewhere in this bot) — no chart rendering, no TradingView
dependency, no network calls.

Terminology (matches the source indicator):
  - A "leg" is which direction price is currently swinging in, detected via
    a rolling-window pivot test (a confirmed swing high starts a bearish
    leg, a confirmed swing low starts a bullish leg).
  - Each leg transition records a new swing-high or swing-low pivot level.
  - BOS ("break of structure"): price closes back through the last swing
    pivot in the direction the trend was already biased — continuation.
  - CHoCH ("change of character"): same break, but against the trend's
    current bias — a reversal signal.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BULLISH = 1
BEARISH = -1

_BULLISH_LEG = 1
_BEARISH_LEG = 0


@dataclass
class StructureBreak:
    kind: str            # "BOS" | "CHoCH"
    direction: int       # BULLISH | BEARISH — the direction of the break
    price: float         # the swing pivot level that was broken
    bar_index: int       # index into the input df where the break occurred
    pivot_bar_index: int  # index of the swing pivot bar itself


@dataclass
class StructureState:
    bias: int | None                   # current trend bias, None if not yet established
    last_break: StructureBreak | None   # most recent BOS/CHoCH, None if none yet
    swing_high: float | None            # current (last recorded) swing-high pivot level
    swing_low: float | None             # current (last recorded) swing-low pivot level


def compute_structure(df: pd.DataFrame, size: int = 50) -> StructureState:
    """Runs swing-structure detection over the full candle history and
    returns the final state (current bias + most recent break, if any).

    `df` must have `high`, `low`, `close` columns, oldest-first. `size` is
    the pivot lookback (matches the source indicator's default swing length
    of 50 bars) — a bar `size` bars back is a confirmed swing pivot once it's
    the highest/lowest point across the following `size` bars.
    """
    n = len(df)
    if n <= size:
        return StructureState(bias=None, last_break=None, swing_high=None, swing_low=None)

    high = df["high"].reset_index(drop=True)
    low = df["low"].reset_index(drop=True)
    close = df["close"].reset_index(drop=True)

    leg = _BEARISH_LEG
    swing_high_level: float | None = None
    swing_high_crossed = True   # no pivot recorded yet — nothing to break
    swing_low_level: float | None = None
    swing_low_crossed = True

    bias: int | None = None
    last_break: StructureBreak | None = None

    for i in range(size, n):
        window_high = high.iloc[i - size + 1 : i + 1].max()
        window_low = low.iloc[i - size + 1 : i + 1].min()
        pivot_high = high.iloc[i - size]
        pivot_low = low.iloc[i - size]

        new_leg = leg
        if pivot_high > window_high:
            new_leg = _BEARISH_LEG
        elif pivot_low < window_low:
            new_leg = _BULLISH_LEG

        if new_leg != leg:
            if new_leg == _BULLISH_LEG:
                # Confirmed swing low at bar (i - size).
                swing_low_level = float(pivot_low)
                swing_low_crossed = False
            else:
                # Confirmed swing high at bar (i - size).
                swing_high_level = float(pivot_high)
                swing_high_crossed = False
            leg = new_leg

        # BOS/CHoCH: price closing back through the last recorded pivot,
        # evaluated every bar (not just on leg transitions), and only once
        # per pivot (the `crossed` flags reset only when a new pivot forms).
        c_now, c_prev = close.iloc[i], close.iloc[i - 1]

        if swing_high_level is not None and not swing_high_crossed and c_prev <= swing_high_level and c_now > swing_high_level:
            kind = "CHoCH" if bias == BEARISH else "BOS"
            bias = BULLISH
            swing_high_crossed = True
            last_break = StructureBreak(kind=kind, direction=BULLISH, price=swing_high_level, bar_index=i, pivot_bar_index=i - size)

        if swing_low_level is not None and not swing_low_crossed and c_prev >= swing_low_level and c_now < swing_low_level:
            kind = "CHoCH" if bias == BULLISH else "BOS"
            bias = BEARISH
            swing_low_crossed = True
            last_break = StructureBreak(kind=kind, direction=BEARISH, price=swing_low_level, bar_index=i, pivot_bar_index=i - size)

    return StructureState(bias=bias, last_break=last_break, swing_high=swing_high_level, swing_low=swing_low_level)
