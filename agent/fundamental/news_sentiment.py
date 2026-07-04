"""Free, no-LLM news sentiment for the daily coin digest.

Uses CryptoPanic's free API (optional API key) for per-coin headlines, scored
with a crypto-relevant keyword lexicon rather than an LLM call — this keeps
the feature at zero ongoing cost. If no API key is configured, sentiment
gracefully reports "no data" rather than failing the digest.
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


@dataclass
class NewsSentiment:
    score: float                  # -1..1, 0 = neutral/no data
    label: str                    # "positive" | "negative" | "neutral" | "no data"
    headlines: list[str] = field(default_factory=list)


def _coin_code(symbol: str) -> str:
    return symbol.split("/")[0].upper()


def fetch_headlines(symbol: str, limit: int = 8) -> list[str]:
    if not settings.cryptopanic_api_key:
        return []
    try:
        resp = requests.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={
                "auth_token": settings.cryptopanic_api_key,
                "currencies": _coin_code(symbol),
                "public": "true",
                "kind": "news",
            },
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [r.get("title", "") for r in results[:limit] if r.get("title")]
    except Exception as e:
        log.warning(f"[{symbol}] News fetch failed: {e}")
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
    return score_headlines(fetch_headlines(symbol))
