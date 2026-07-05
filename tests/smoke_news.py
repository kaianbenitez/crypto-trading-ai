"""Smoke script for agent/fundamental/news_sentiment.py (cryptocurrency.cv).
Run directly: `python3 tests/smoke_news.py`.

Verifies that no failure mode here can ever affect trading: network errors,
timeouts, malformed/unexpected response shapes, and the feature being
disabled all degrade to an empty/"no data" result instead of raising.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from agent.config.settings import settings  # noqa: E402
from agent.fundamental import news_sentiment  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


class _FakeResponse:
    def __init__(self, json_body=None, status_code=200, raise_for_status_exc=None):
        self._json_body = json_body
        self.status_code = status_code
        self._raise_for_status_exc = raise_for_status_exc

    def raise_for_status(self):
        if self._raise_for_status_exc:
            raise self._raise_for_status_exc

    def json(self):
        if self._json_body is None:
            raise ValueError("no JSON body")
        return self._json_body


def main():
    settings.news_enabled = True
    settings.news_timeout_sec = 8
    settings.news_max_headlines = 5

    original_get = requests.get

    # --- 1. Network/timeout failure must not raise, must return [] ---
    def _raise_timeout(*a, **kw):
        raise requests.exceptions.Timeout("simulated timeout")
    requests.get = _raise_timeout
    try:
        headlines = news_sentiment.fetch_headlines("BTC/USDT")
        check("Timeout degrades to empty headline list, no raise", headlines == [])
        sentiment = news_sentiment.get_sentiment("BTC/USDT")
        check("get_sentiment degrades to 'no data' on timeout", sentiment.label == "no data")
    finally:
        requests.get = original_get

    # --- 2. HTTP error (rate limit / 5xx) must not raise ---
    def _http_error(*a, **kw):
        return _FakeResponse(raise_for_status_exc=requests.exceptions.HTTPError("429"))
    requests.get = _http_error
    try:
        headlines = news_sentiment.fetch_headlines("ETH/USDT")
        check("HTTP error degrades to empty list, no raise", headlines == [])
    finally:
        requests.get = original_get

    # --- 3. Unexpected/changed response shape must not raise ---
    def _weird_shape(*a, **kw):
        return _FakeResponse(json_body={"totally": "different shape", "no articles key": True})
    requests.get = _weird_shape
    try:
        headlines = news_sentiment.fetch_headlines("SOL/USDT")
        check("Unexpected response shape degrades to empty list, no raise", headlines == [])
    finally:
        requests.get = original_get

    # --- 4. Non-JSON body must not raise ---
    def _bad_json(*a, **kw):
        return _FakeResponse(json_body=None)  # .json() raises ValueError
    requests.get = _bad_json
    try:
        headlines = news_sentiment.fetch_headlines("ADA/USDT")
        check("Non-JSON response degrades to empty list, no raise", headlines == [])
    finally:
        requests.get = original_get

    # --- 5. Disabled feature short-circuits without any network call ---
    settings.news_enabled = False
    call_count = {"n": 0}

    def _should_not_be_called(*a, **kw):
        call_count["n"] += 1
        return _FakeResponse(json_body={"articles": []})
    requests.get = _should_not_be_called
    try:
        headlines = news_sentiment.fetch_headlines("BTC/USDT")
        check("Disabled news makes zero network calls", call_count["n"] == 0)
        check("Disabled news returns empty list", headlines == [])
    finally:
        requests.get = original_get
        settings.news_enabled = True

    # --- 6. A well-formed response with a real coin mention scores non-trivially ---
    def _good_response(*a, **kw):
        params = kw.get("params", {})
        if params.get("category") == "bitcoin":
            return _FakeResponse(json_body={"articles": [
                {"title": "Bitcoin adoption surges after major bank partnership", "description": "Institutional inflow accelerates"},
                {"title": "Bitcoin exchange hack drains millions, investigation launched", "description": "Security breach confirmed"},
            ]})
        return _FakeResponse(json_body={"articles": []})
    requests.get = _good_response
    try:
        sentiment = news_sentiment.get_sentiment("BTC/USDT")
        check("Well-formed response produces a real headline set", len(sentiment.headlines) > 0)
        check("Sentiment label is one of the known values", sentiment.label in ("positive", "negative", "neutral", "no data"))
    finally:
        requests.get = original_get

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
