"""Free, no-auth news context for the daily coin digest.

Uses cryptocurrency.cv's free public news API (no API key, no signup) — it
requires a "category" query param rather than an arbitrary coin symbol, so
only BTC/ETH/SOL map directly to a topic category; every other coin falls
back to the "general" market-news feed, keyword-filtered for the coin name
where possible.

Scored with a crypto-relevant keyword lexicon rather than an LLM call — this
keeps the feature at zero ongoing cost and fully deterministic. News is
display/context only: it feeds a small confidence nudge in the live strategy
(see agent/dashboard/coin_digest.py's apply_sentiment_adjustment) and the
daily coin digest, but it never opens a trade on its own, and any failure
here (timeout, rate limit, shape change, outage) must never affect trading —
every code path below degrades to an empty/no-data result instead of raising.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

from agent.config.settings import settings

log = logging.getLogger(__name__)

POSITIVE_WORDS = [
    "partnership", "adoption", "upgrade", "listing", "approval", "bullish",
    "rally", "surge", "integration", "launch", "expands", "expansion",
    "record high", "inflow", "buyback", "backing", "breakthrough", "milestone",
]
NEGATIVE_WORDS = [
    "hack", "exploit", "lawsuit", "ban", "delisting", "crash", "bearish",
    "investigation", "outflow", "dump", "scam", "fraud", "halt", "breach",
    "vulnerability", "liquidation", "charges", "insolvent", "sell-off",
]

# cryptocurrency.cv only supports a fixed topic-category list, not arbitrary
# coin symbols — map the few coins that have a direct category, and use the
# broad "general" feed (keyword-filtered) for everything else.
_DIRECT_CATEGORY = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}


@dataclass
class NewsSentiment:
    score: float                  # -1..1, 0 = neutral/no data
    label: str                    # "positive" | "negative" | "neutral" | "no data"
    headlines: list[str] = field(default_factory=list)


def _coin_code(symbol: str) -> str:
    return symbol.split("/")[0].upper()


def _fetch_category(category: str, limit: int) -> list[dict]:
    resp = requests.get(
        settings.news_api_url,
        params={"category": category},
        timeout=settings.news_timeout_sec,
    )
    resp.raise_for_status()
    body = resp.json()
    articles = body.get("articles")
    if not isinstance(articles, list):
        return []
    return articles[:limit]


def fetch_headlines(symbol: str, limit: int | None = None) -> list[str]:
    """Returns up to `limit` headline strings for the coin, or [] on any
    failure/disable — never raises, so a news outage can never affect
    trading or crash the digest job."""
    if not settings.news_enabled:
        return []
    limit = limit or settings.news_max_headlines
    coin = _coin_code(symbol)

    try:
        category = _DIRECT_CATEGORY.get(coin, "general")
        articles = _fetch_category(category, limit * 4 if category == "general" else limit)

        if category == "general":
            # No per-coin filter on the general feed — keep only headlines
            # that actually mention this coin, falling back to the broad
            # market feed (still useful context) if none do.
            coin_name_hits = [
                a for a in articles
                if coin.lower() in (a.get("title", "") + " " + a.get("description", "")).lower()
            ]
            articles = coin_name_hits or articles

        headlines = []
        for a in articles[:limit]:
            title = a.get("title")
            description = a.get("description")
            if not title:
                continue
            headlines.append(f"{title}. {description}" if description else title)
        return headlines
    except Exception as e:
        log.warning(f"[{symbol}] News fetch failed ({settings.news_provider}): {e}")
        return []


def score_headlines(headlines: list[str]) -> NewsSentiment:
    if not headlines:
        return NewsSentiment(score=0.0, label="no data", headlines=[])

    total = 0
    for title in headlines:
        lower = title.lower()
        total += sum(1 for w in POSITIVE_WORDS if w in lower)
        total -= sum(1 for w in NEGATIVE_WORDS if w in lower)

    score = max(-1.0, min(1.0, (total / max(len(headlines), 1)) / 2))
    if score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"
    return NewsSentiment(score=round(score, 2), label=label, headlines=headlines[:3])


def get_sentiment(symbol: str) -> NewsSentiment:
    try:
        return score_headlines(fetch_headlines(symbol))
    except Exception as e:
        # Belt-and-suspenders: fetch_headlines already catches its own
        # exceptions, but scoring/consumption must never be able to take
        # trading down either.
        log.warning(f"[{symbol}] News sentiment unavailable: {e}")
        return NewsSentiment(score=0.0, label="no data", headlines=[])
