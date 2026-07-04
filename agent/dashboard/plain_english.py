"""Rewrites technical strategy/postmortem reasoning into beginner-friendly text.

This module never touches the strategy logic or the raw reasoning strings used
internally (logs, tuner, memory) — it only translates text at the point it is
shown to a human, in Telegram messages and the dashboard/journal.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Friendly labels for enums shown across TG + dashboard
# ---------------------------------------------------------------------------

REGIME_FRIENDLY = {
    "trending": "trending steadily in one direction",
    "ranging": "moving sideways, no clear direction",
    "high_vol": "unusually choppy/volatile",
    "unknown": "unclear",
}

EXIT_REASON_FRIENDLY = {
    "take_profit": "hit its profit target 🎯",
    "trailing_take_profit": "let the winner run, then locked in profit 🏁",
    "stop_loss": "hit its safety stop 🛑",
    "manual_reconcile_duplicate": "closed manually to fix a duplicate position",
}

STRATEGY_FRIENDLY = {
    "trend_following": "trend-following",
    "mean_reversion": "bounce (mean-reversion)",
    "volatility_filter": "stood aside (volatility filter)",
}

TRAIL_MODE_FRIENDLY = {
    "atr": "based on how much the coin has been swinging recently",
}


def friendly_regime(regime: str | None) -> str:
    key = (regime or "").lower()
    return REGIME_FRIENDLY.get(key, regime or "unclear")


def friendly_exit_reason(reason: str | None) -> str:
    key = (reason or "").lower()
    return EXIT_REASON_FRIENDLY.get(key, (reason or "-").replace("_", " "))


def friendly_strategy(name: str | None) -> str:
    key = (name or "").lower()
    return STRATEGY_FRIENDLY.get(key, (name or "-").replace("_", " "))


def friendly_trail_mode(mode: str | None) -> str:
    key = (mode or "").lower()
    return TRAIL_MODE_FRIENDLY.get(key, (mode or "-").replace("_", " "))


# ---------------------------------------------------------------------------
# Pattern-based rewrites for known reasoning line shapes
# ---------------------------------------------------------------------------

def _f(x) -> str:
    try:
        return f"{float(x):.1f}"
    except (TypeError, ValueError):
        return str(x)


_PATTERNS: list[tuple[re.Pattern, callable]] = []


def _rule(pattern: str):
    def register(fn):
        _PATTERNS.append((re.compile(pattern), fn))
        return fn
    return register


@_rule(r"^Regime: (\w+) \(ADX=([\d.]+)\)$")
def _regime_line(m):
    regime, adx = m.group(1), _f(m.group(2))
    return f"Market read: {friendly_regime(regime)} (trend-strength score {adx} — above 20 usually means a real trend)."


@_rule(r"^ATR ratio ([\d.]+)× baseline — shock/event in progress, standing aside$")
def _atr_shock(m):
    return f"Price just moved about {m.group(1)}x faster than usual — sitting this one out until it calms down."


@_rule(r"^EMA fast crossed above EMA slow \(bullish crossover\)$")
def _ema_cross_up(m):
    return "The short-term price average just crossed above the longer-term one — a classic early 'uptrend starting' signal."


@_rule(r"^EMA fast crossed below EMA slow \(bearish crossover\)$")
def _ema_cross_down(m):
    return "The short-term price average just crossed below the longer-term one — a classic early 'downtrend starting' signal."


@_rule(r"^MACD above signal line, confirming upward momentum$")
def _macd_up(m):
    return "A momentum gauge (MACD) agrees price is gaining upward speed."


@_rule(r"^MACD below signal line, confirming downward momentum$")
def _macd_down(m):
    return "A momentum gauge (MACD) agrees price is gaining downward speed."


@_rule(r"^Volume above SMA, confirming move is not low-conviction$")
def _volume_ok(m):
    return "More people than usual are trading right now, so this move has real backing."


@_rule(r"^EMA fast above EMA slow — bullish trend intact$")
def _ema_bull_intact(m):
    return "Price is still riding above its recent average — the uptrend is holding."


@_rule(r"^EMA fast below EMA slow — bearish trend intact$")
def _ema_bear_intact(m):
    return "Price is still riding below its recent average — the downtrend is holding."


@_rule(r"^ADX ([\d.]+) confirms directional trend$")
def _adx_confirms(m):
    return f"Trend-strength score is {_f(m.group(1))} — strong enough to trust the direction."


@_rule(r"^No trend signal: (.*)$")
def _no_trend(m):
    return f"No clear trend to trade yet ({_simplify_fragment(m.group(1))})."


@_rule(r"^RSI \(([\d.]+)\) oversold \+ price at lower BB — strong mean-reversion setup$")
def _mr_strong_long(m):
    return f"Price dropped further than usual and looks stretched down (score {_f(m.group(1))}/100, low = stretched) while sitting near the bottom of its typical range — setups like this often bounce."


@_rule(r"^RSI \(([\d.]+)\) overbought \+ price at upper BB — strong mean-reversion setup$")
def _mr_strong_short(m):
    return f"Price rose further than usual and looks stretched up (score {_f(m.group(1))}/100, high = stretched) while sitting near the top of its typical range — setups like this often pull back."


@_rule(r"^RSI \(([\d.]+)\) oversold — moderate mean-reversion setup$")
def _mr_mod_long_rsi(m):
    return f"Price looks a bit stretched to the downside (score {_f(m.group(1))}/100) — might bounce, moderate confidence."


@_rule(r"^Price at lower Bollinger Band — moderate mean-reversion setup$")
def _mr_mod_long_bb(m):
    return "Price is at the bottom edge of its typical trading range — might bounce, moderate confidence."


@_rule(r"^RSI \(([\d.]+)\) overbought — moderate mean-reversion setup$")
def _mr_mod_short_rsi(m):
    return f"Price looks a bit stretched to the upside (score {_f(m.group(1))}/100) — might pull back, moderate confidence."


@_rule(r"^Price at upper Bollinger Band — moderate mean-reversion setup$")
def _mr_mod_short_bb(m):
    return "Price is at the top edge of its typical trading range — might pull back, moderate confidence."


@_rule(r"^No RSI extreme \(RSI=([\d.]+)\) or BB touch$")
def _mr_none(m):
    return f"Price isn't stretched in either direction right now (score {_f(m.group(1))}/100) — no bounce setup."


@_rule(r"^Structure bias BEARISH — confidence reduced \(counter-trend\)$")
def _bias_bear(m):
    return "The bigger-picture trend still looks bearish, so this buy goes against the grain — confidence lowered."


@_rule(r"^Structure bias BULLISH — confidence reduced \(counter-trend\)$")
def _bias_bull(m):
    return "The bigger-picture trend still looks bullish, so this sell goes against the grain — confidence lowered."


@_rule(r"^Price in PREMIUM zone \(([\d.]+)\) — unfavourable for longs$")
def _premium(m):
    return "Price is trading near the expensive end of its recent range — not ideal timing to buy."


@_rule(r"^Price in DISCOUNT zone \(([\d.]+)\) — unfavourable for shorts$")
def _discount(m):
    return "Price is trading near the cheap end of its recent range — not ideal timing to sell."


@_rule(r"^Near bullish Order Block — institutional support level$")
def _ob_bull(m):
    return "Price is near a zone where big buyers stepped in before — often acts like a floor."


@_rule(r"^Near bearish Order Block — institutional resistance level$")
def _ob_bear(m):
    return "Price is near a zone where big sellers stepped in before — often acts like a ceiling."


@_rule(r"^Bullish FVG present in recent range$")
def _fvg_bull(m):
    return "There's an unfilled price gap nearby that tends to favor more upside."


@_rule(r"^Bearish FVG present in recent range$")
def _fvg_bear(m):
    return "There's an unfilled price gap nearby that tends to favor more downside."


@_rule(r"^Bullish liquidity sweep — sell-side grabbed, reversal likely$")
def _sweep_bull(m):
    return "Price briefly dipped to trigger other traders' stop-losses before reversing up — a common 'shake-out' pattern."


@_rule(r"^Bearish liquidity sweep — buy-side grabbed, reversal likely$")
def _sweep_bear(m):
    return "Price briefly spiked to trigger other traders' stop-losses before reversing down — a common 'shake-out' pattern."


@_rule(r"^Strategy '(.+)' in '(.+)' regime, exited via (\w+), outcome=(\w+)\.$")
def _postmortem_header(m):
    strategy, regime, exit_reason, outcome = m.groups()
    return (
        f"This was a {friendly_strategy(strategy)} trade in a market that was {friendly_regime(regime)}. "
        f"It closed because it {friendly_exit_reason(exit_reason)} — result: {outcome}."
    )


@_rule(r"^Stop-loss was hit before price moved favorably.*$")
def _pm_sl_generic(m):
    return ("Price hit the safety exit before things could turn around. Either the safety margin "
            "was a bit tight for how much this coin was moving, or the setup just didn't play out.")


@_rule(r"^ADX was only ([\d.]+) at entry.*$")
def _pm_adx_borderline(m):
    return f"The trend wasn't very strong when we entered (score {_f(m.group(1))}, vs the usual 30+ bar for a solid trend) — may have been a borderline call."


@_rule(r"^Volume confirmation was weak/absent.*$")
def _pm_volume_weak(m):
    return "Not many people were actually trading at the time, even though the setup looked right on paper."


@_rule(r"^Loss occurred without a clear stop-loss trigger reason logged.*$")
def _pm_unclear_loss(m):
    return "This trade lost money for a reason that isn't clearly logged — worth a closer look."


@_rule(r"^Entry conditions were validated by price action.*$")
def _pm_win(m):
    return "The setup played out as expected — a good sign this approach works in this kind of market."


@_rule(r"^Entry reasoning was: (.*)$")
def _pm_entry_recap(m):
    parts = [p.strip() for p in m.group(1).split(";") if p.strip()]
    simplified = [_simplify_fragment(p) for p in parts]
    return "Why we entered: " + "; ".join(simplified) + "."


@_rule(r"^shorted when RSI was ([\d.]+) \(oversold\) — high bounce risk$")
def _mem_short_oversold(m):
    return "Past trades that shorted an already 'stretched down' coin often got caught in a bounce."


@_rule(r"^longed when RSI was ([\d.]+) \(overbought\) — high pullback risk$")
def _mem_long_overbought(m):
    return "Past trades that bought an already 'stretched up' coin often got caught in a pullback."


@_rule(r"^longed in premium zone \(.+\) — price was expensive$")
def _mem_long_premium(m):
    return "Past trades that bought near the expensive end of the range often didn't work out."


@_rule(r"^shorted in discount zone \(.+\) — price was cheap$")
def _mem_short_discount(m):
    return "Past trades that sold near the cheap end of the range often didn't work out."


@_rule(r"^entered trend signal with ADX only ([\d.]+) — trend was too weak$")
def _mem_weak_trend(m):
    return "Past trades entered when the trend wasn't very strong tended to fail."


@_rule(r"^entered during ATR spike \([\d.]+× baseline\) — volatility was extreme$")
def _mem_atr_spike(m):
    return "Past trades entered during extreme volatility spikes tended to fail."


@_rule(r"^entered with neutral RSI \([\d.]+\) and hit TP — clean setup$")
def _mem_clean_setup(m):
    return "This type of clean, no-extremes setup has worked well before."


@_rule(r"^Memory: (.+) failed (\d+)x recently — confidence reduced$")
def _mem_pattern_failed(m):
    return f"The system noticed a similar setup failed {m.group(2)} times recently, so it's being more cautious here."


@_rule(r"^Memory: (.+) worked (\d+)x recently — confidence boosted$")
def _mem_pattern_worked(m):
    return f"The system noticed a similar setup worked {m.group(2)} times recently, so confidence was boosted."


@_rule(r"^News sentiment positive — small confidence boost$")
def _news_positive(m):
    return "Recent news coverage for this coin reads positive — small confidence boost."


@_rule(r"^News sentiment negative — confidence reduced$")
def _news_negative(m):
    return "Recent news coverage for this coin reads negative — confidence reduced."


# ---------------------------------------------------------------------------
# Fallback glossary for anything not covered by a pattern above
# ---------------------------------------------------------------------------

_GLOSSARY = [
    (re.compile(r"\bADX\b(?! \()"), "ADX (trend-strength score)"),
    (re.compile(r"\bRSI\b(?! \()"), "RSI (overbought/oversold gauge)"),
    (re.compile(r"\bEMA\b"), "EMA (moving average)"),
    (re.compile(r"\bMACD\b(?! \()"), "MACD (momentum gauge)"),
    (re.compile(r"\bATR\b(?! \()"), "ATR (volatility gauge)"),
    (re.compile(r"\bBB\b"), "BB (Bollinger Band, a typical price range)"),
    (re.compile(r"\bSMC\b"), "SMC (smart-money price-structure signals)"),
    (re.compile(r"\bFVG\b(?! \()"), "FVG (unfilled price gap)"),
    (re.compile(r"\bOB\b"), "OB (order block, a zone big traders acted from)"),
    (re.compile(r"\bSL\b"), "SL (stop-loss, the safety exit)"),
    (re.compile(r"\bTP\b"), "TP (take-profit, the target exit)"),
    (re.compile(r"\bR:R\b"), "R:R (reward-to-risk ratio)"),
]


def _simplify_fragment(text: str) -> str:
    """Best-effort single-fragment cleanup used inside composite messages."""
    text = text.strip()
    for pattern, fn in _PATTERNS:
        m = pattern.match(text)
        if m:
            return fn(m)
    return _annotate_jargon(text)


def _annotate_jargon(text: str) -> str:
    out = text
    for pattern, replacement in _GLOSSARY:
        out = pattern.sub(replacement, out, count=1)
    return out


def simplify_line(text: str) -> str:
    if not text:
        return text
    for pattern, fn in _PATTERNS:
        m = pattern.match(text.strip())
        if m:
            return fn(m)
    return _annotate_jargon(text)


def simplify_lines(lines: list[str] | None) -> list[str]:
    if not lines:
        return []
    return [simplify_line(line) for line in lines]
