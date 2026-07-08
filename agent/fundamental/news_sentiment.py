"""Free-tier news context for the daily coin digest (and, later, per-position
status checks).

Uses marketaux.com's news API — free tier is 100 requests/day, no credit
card required. Crypto entities are queried with a "CC:" symbol prefix (e.g.
"CC:BTC"), which marketaux resolves against its own entity graph, so every
coin gets a real, correctly-matched query — no BTC/ETH/SOL-only limitation
like the prior provider had.

marketaux returns a real per-article sentiment score (from its own model),
so we use that directly instead of a hand-rolled keyword lexicon.

News is display/context only: it feeds a small confidence nudge in the live
strategy (see agent/dashboard/coin_digest.py's apply_sentiment_adjustment)
and the daily coin digest, but it never opens a trade on its own, and any
failure here (timeout, rate limit, shape change, outage, missing key) must
never affect trading — every code path below degrades to an empty/no-data
result instead of raising.

Prior provider (cryptocurrency.cv) went dark — HTTP 402 "DEPLOYMENT_DISABLED"
— confirmed 2026-07; migrated to marketaux the same day.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

from agent.config.settings import settings

log = logging.getLogger(__name__)


@dataclass
class NewsSentiment:
    score: float                  # -1..1, 0 = neutral/no data
    label: str                    # "positive" | "negative" | "neutral" | "no data"
    headlines: list[str] = field(default_factory=list)


def _coin_code(symbol: str) -> str:
    return symbol.split("/")[0].upper()


def _fetch_articles(coin: str, limit: int) -> list[dict]:
    if not settings.marketaux_api_key:
        log.warning("MARKETAUX_API_KEY not set — news disabled until configured")
        return []
    resp = requests.get(
        settings.news_api_url,
        params={
            "symbols": f"CC:{coin}",
            "entity_types": "cryptocurrency",
            "language": "en",
            "sort": "published_desc",
            "limit": limit,
            "api_token": settings.marketaux_api_key,
        },
        timeout=settings.news_timeout_sec,
    )
    resp.raise_for_status()
    body = resp.json()
    articles = body.get("data")
    return articles if isinstance(articles, list) else []


def fetch_articles(symbol: str, limit: int | None = None) -> list[dict]:
    """Returns up to `limit` raw article dicts (title/description/entities/
    sentiment) for the coin, or [] on any failure/disable — never raises, so
    a news outage can never affect trading or crash the digest job."""
    if not settings.news_enabled:
        return []
    limit = limit or settings.news_max_headlines
    coin = _coin_code(symbol)
    try:
        return _fetch_articles(coin, limit)
    except Exception as e:
        log.warning(f"[{symbol}] News fetch failed ({settings.news_provider}): {e}")
        return []


def fetch_headlines(symbol: str, limit: int | None = None) -> list[str]:
    """Headline strings only — kept for any caller that just wants text."""
    headlines = []
    for a in fetch_articles(symbol, limit):
        title = a.get("title")
        description = a.get("description")
        if not title:
            continue
        headlines.append(f"{title}. {description}" if description else title)
    return headlines


def score_headlines(articles: list[dict], symbol: str) -> NewsSentiment:
    if not articles:
        return NewsSentiment(score=0.0, label="no data", headlines=[])

    coin = _coin_code(symbol)
    scores = []
    headlines = []
    for a in articles:
        title = a.get("title")
        if not title:
            continue
        description = a.get("description")
        headlines.append(f"{title}. {description}" if description else title)
        # Use the sentiment marketaux attached to *this coin's* entity match,
        # not a whole-article average — an article can be bullish on one coin
        # and bearish on another it also mentions.
        for entity in a.get("entities") or []:
            if str(entity.get("symbol", "")).upper() == f"CC:{coin}":
                s = entity.get("sentiment_score")
                if isinstance(s, (int, float)):
                    scores.append(float(s))
                break

    if not scores:
        return NewsSentiment(score=0.0, label="no data", headlines=headlines[:3])

    score = max(-1.0, min(1.0, sum(scores) / len(scores)))
    if score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"
    return NewsSentiment(score=round(score, 2), label=label, headlines=headlines[:3])


def get_sentiment(symbol: str) -> NewsSentiment:
    try:
        return score_headlines(fetch_articles(symbol), symbol)
    except Exception as e:
        # Belt-and-suspenders: fetch_articles already catches its own
        # exceptions, but scoring/consumption must never be able to take
        # trading down either.
        log.warning(f"[{symbol}] News sentiment unavailable: {e}")
        return NewsSentiment(score=0.0, label="no data", headlines=[])
