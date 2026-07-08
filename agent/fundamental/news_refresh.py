"""Rolling, budget-aware news-sentiment refresh — replaces the once-daily
digest fetch as the source of sentiment freshness. Marketaux's free tier is
100 requests/day; this splits usage into two lanes so it stays well under
that while covering the roster continuously rather than in one daily burst:

  - Open positions: refreshed individually, one call per symbol, never
    batched with other coins — a real catalyst for a live trade should never
    get crowded out by a bigger coin's news volume (the free tier caps every
    response at ~3 articles total, not per-symbol).
  - Active roster: refreshed in small batches (a few coins per call),
    cycling through the whole roster over several hours instead of hitting
    every symbol once a day at a fixed hour.

Writes straight into the existing CoinDigest table (the same one
agent.fundamental.coin_digest.apply_sentiment_adjustment() reads from), so
the live confidence nudge gets fresher, broader data for free — no changes
needed to that consumer. Every function here degrades silently on failure;
a news outage must never affect trading or crash the caller's loop.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.fundamental.news_sentiment import NewsSentiment, fetch_articles_multi, get_sentiment, score_headlines

log = logging.getLogger(__name__)


def _upsert_sentiment(session, symbol: str, sentiment: NewsSentiment) -> None:
    from agent.db.models import CoinDigest

    row = (
        session.query(CoinDigest)
        .filter(CoinDigest.symbol == symbol)
        .order_by(CoinDigest.created_at.desc())
        .first()
    )
    if row is not None:
        row.sentiment_score = sentiment.score
        row.sentiment_label = sentiment.label
        row.set_headlines(sentiment.headlines)
        row.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        row = CoinDigest(
            symbol=symbol,
            price_low_24h=None, price_high_24h=None, price_change_pct_24h=None,
            regime="unknown", watching_side=None, watch_low=None, watch_high=None,
            sentiment_score=sentiment.score, sentiment_label=sentiment.label,
            summary="",
        )
        row.set_headlines(sentiment.headlines)
        session.add(row)
    session.commit()


def refresh_position_news(session, symbols: list[str]) -> None:
    """One individual call per open-position symbol."""
    for symbol in symbols:
        try:
            sentiment = get_sentiment(symbol)
            _upsert_sentiment(session, symbol, sentiment)
        except Exception as e:
            log.warning(f"[{symbol}] Position news refresh failed: {e}")


def refresh_roster_batch(session, roster_symbols: list[str], batch_index: int, batch_size: int) -> int:
    """Refreshes one small batch of the roster per call, cycling forward
    over successive calls so the whole roster gets covered over time instead
    of all at once. Returns the batch_index to pass in next time."""
    if not roster_symbols or batch_size <= 0:
        return 0

    n_batches = max(1, -(-len(roster_symbols) // batch_size))  # ceil division
    idx = batch_index % n_batches
    start = idx * batch_size
    batch = roster_symbols[start:start + batch_size]
    next_idx = (idx + 1) % n_batches
    if not batch:
        return next_idx

    articles = fetch_articles_multi(batch)
    for symbol in batch:
        try:
            sentiment = score_headlines(articles, symbol)
            _upsert_sentiment(session, symbol, sentiment)
        except Exception as e:
            log.warning(f"[{symbol}] Roster news scoring failed: {e}")

    return next_idx
