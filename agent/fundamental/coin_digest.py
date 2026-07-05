"""Daily plain-English digest per coin — price action, what the agent is
watching for, and free news sentiment. Reuses the live indicator stack and the
plain_english translator so wording matches what's shown in Telegram/dashboard,
and makes no LLM calls (zero ongoing cost)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from agent.backtest.validate import BASE_PARAMS
from agent.config.settings import settings
from agent.dashboard.plain_english import friendly_regime, simplify_line
from agent.fundamental.market_context import add_market_context
from agent.fundamental.news_sentiment import get_sentiment
from agent.strategy.ensemble import generate_signal
from agent.strategy.indicators import add_indicators
from agent.strategy.smc import add_smc


@dataclass
class CoinDigestResult:
    symbol: str
    price_low_24h: float | None
    price_high_24h: float | None
    price_change_pct_24h: float | None
    regime: str
    watching_side: str | None
    watch_low: float | None
    watch_high: float | None
    sentiment_score: float
    sentiment_label: str
    headlines: list[str] = field(default_factory=list)
    summary: str = ""


def _prepare(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = add_indicators(df, params)
    df = add_market_context(df, params)
    df = add_smc(df, params)
    return df.dropna().reset_index(drop=True)


def build_coin_digest(symbol: str, adapter, params: dict | None = None) -> CoinDigestResult:
    params = params or dict(BASE_PARAMS, context_window_candles=120, max_atr_ratio=2.5)

    candles = adapter.fetch_ohlcv(symbol, "1h", limit=200)
    df = pd.DataFrame([{
        "open": c.open, "high": c.high, "low": c.low,
        "close": c.close, "volume": c.volume, "timestamp": c.timestamp,
    } for c in candles]).sort_values("timestamp").reset_index(drop=True)

    last_24h = df.tail(24)
    price_low = float(last_24h["low"].min()) if not last_24h.empty else None
    price_high = float(last_24h["high"].max()) if not last_24h.empty else None
    price_change_pct = None
    if len(last_24h) >= 2:
        start_price = float(last_24h["open"].iloc[0])
        end_price = float(last_24h["close"].iloc[-1])
        if start_price:
            price_change_pct = (end_price - start_price) / start_price * 100

    prepared = _prepare(df, params)
    watching_side = None
    watch_low = watch_high = None
    regime = "unknown"
    read_note = "Not enough data yet to form a read on this coin."

    if len(prepared) >= 2:
        row, prev = prepared.iloc[-1], prepared.iloc[-2]
        signal = generate_signal(row, prev, params)
        regime = str(signal.indicator_snapshot.get("regime", "unknown"))
        read_note = simplify_line(signal.reasoning[0]) if signal.reasoning else "No clear setup right now."

        if signal.is_actionable and signal.confidence > 0:
            watching_side = signal.side.value
            atr = float(row.get("atr") or 0)
            close = float(row.get("close") or 0)
            if atr > 0 and close > 0:
                sl_mult = float(params.get("atr_mult_sl", 1.5))
                if watching_side == "long":
                    watch_low, watch_high = close - atr * sl_mult, close
                else:
                    watch_low, watch_high = close, close + atr * sl_mult

    sentiment = get_sentiment(symbol)
    coin = symbol.split("/")[0]

    parts = []
    if price_low is not None and price_high is not None:
        change_txt = f"{price_change_pct:+.1f}%" if price_change_pct is not None else "roughly flat"
        parts.append(
            f"Over the last 24h, {coin} traded between {price_low:.4f} and {price_high:.4f} ({change_txt})."
        )
    parts.append(f"Market read: {friendly_regime(regime)}. {read_note}")
    if watching_side and watch_low is not None and watch_high is not None:
        parts.append(
            f"If a trade opens here, we'd be looking to go {watching_side} somewhere between "
            f"{watch_low:.4f} and {watch_high:.4f}."
        )
    else:
        parts.append("No active setup right now — just watching.")
    if not settings.news_enabled:
        parts.append("News context is turned off.")
    elif sentiment.label == "no data":
        parts.append("News unavailable right now — trading continues as usual.")
    else:
        parts.append(f"News sentiment: {sentiment.label} ({len(sentiment.headlines)} recent headline(s)).")
        if sentiment.headlines:
            parts.append("Recent: " + " | ".join(sentiment.headlines))

    return CoinDigestResult(
        symbol=symbol,
        price_low_24h=price_low,
        price_high_24h=price_high,
        price_change_pct_24h=price_change_pct,
        regime=regime,
        watching_side=watching_side,
        watch_low=watch_low,
        watch_high=watch_high,
        sentiment_score=sentiment.score,
        sentiment_label=sentiment.label,
        headlines=sentiment.headlines,
        summary=" ".join(parts),
    )


def build_all_digests(symbols: list[str], adapter) -> list[CoinDigestResult]:
    results = []
    for symbol in symbols:
        try:
            results.append(build_coin_digest(symbol, adapter))
        except Exception:
            continue
    return results


def apply_sentiment_adjustment(symbol: str, signal, session) -> float:
    """Nudge confidence using the most recent daily sentiment read, if still
    fresh. Kept soft, like the existing memory/weight adjustments — sentiment
    never blocks a trade, it only tilts confidence a little."""
    from datetime import datetime, timedelta, timezone

    from agent.db.models import CoinDigest

    row = (
        session.query(CoinDigest)
        .filter(CoinDigest.symbol == symbol)
        .order_by(CoinDigest.created_at.desc())
        .first()
    )
    if not row or row.sentiment_label in (None, "no data", "neutral"):
        return 0.0

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=36)
    if row.created_at is not None and row.created_at < cutoff:
        return 0.0

    aligned = (
        (signal.side.value == "long" and row.sentiment_label == "positive")
        or (signal.side.value == "short" and row.sentiment_label == "negative")
    )
    opposed = (
        (signal.side.value == "long" and row.sentiment_label == "negative")
        or (signal.side.value == "short" and row.sentiment_label == "positive")
    )
    if aligned:
        signal.reasoning.append(f"News sentiment {row.sentiment_label} — small confidence boost")
        return 0.05
    if opposed:
        signal.reasoning.append(f"News sentiment {row.sentiment_label} — confidence reduced")
        return -0.05
    return 0.0


def save_digest(session, result: CoinDigestResult) -> None:
    from agent.db.models import CoinDigest

    row = CoinDigest(
        symbol=result.symbol,
        price_low_24h=result.price_low_24h,
        price_high_24h=result.price_high_24h,
        price_change_pct_24h=result.price_change_pct_24h,
        regime=result.regime,
        watching_side=result.watching_side,
        watch_low=result.watch_low,
        watch_high=result.watch_high,
        sentiment_score=result.sentiment_score,
        sentiment_label=result.sentiment_label,
        summary=result.summary,
    )
    row.set_headlines(result.headlines)
    session.add(row)
    session.commit()
