# Changelog

All notable changes to this project are logged here, most recent first.
Format is informal — one entry per meaningful change, not strict Keep a Changelog.

## 2026-07-06

- **Tighten market-cap rank floor 200 -> 150.** Live testing showed `VELVET/USDT` and a
  Chinese-named low-quality token still cleared the top-200 threshold. Tightened
  `MARKET_SCAN_MIN_MARKET_CAP_RANK` to 150 to exclude more marginal coins.

## 2026-07-05

- **CoinGecko market-cap/rank filter + BTCDOM index-product denylist.** Live VPS testing
  showed `BTCDOM/USDT` (a synthetic BTC-dominance index perpetual, not a real coin) and
  several obscure micro-caps (`GUA`, `BAS`, `EPIC`, `MAGMA`, `AKE`, `ARPA`, `AT`, `VELVET`)
  clearing the scanner's volume filter and getting shortlisted. Added a market-cap/rank
  cross-check against CoinGecko's free API (`MARKET_SCAN_REQUIRE_MARKET_CAP_RANK`,
  `MARKET_SCAN_MIN_MARKET_CAP_RANK`), degrading gracefully to volume-only filtering if the
  API is unavailable, plus an explicit `_is_index_product` denylist as a defense-in-depth
  backup that works even without market-cap data.
- **Dynamic two-stage market scanner, cost/edge validation gates, free news via
  cryptocurrency.cv.** Major backend upgrade:
  - Two-stage scanner: cheap bulk ticker scan across the exchange, full
    indicator/SMC/MTF/EV/risk stack only on the shortlisted top N.
  - Cost/edge validation gates (`MAX_ESTIMATED_COST_R`, `MIN_NET_EV_AFTER_COST_R`,
    `MIN_EXPECTED_REWARD_COST_MULTIPLE`) layered on the existing EV floor so small wins
    can't hide fee/slippage drag. Reject-only, never resizes positions.
  - Free, no-auth news context via cryptocurrency.cv (replacing CryptoPanic). Display/
    sentiment-nudge only — never opens trades directly.
  - Deterministic, fact-based trade narrative system (thesis/why-accepted/weakness/
    invalidation/past-context) shared across Telegram, dashboard, and journal.

## 2026-07-01 to 2026-07-04

- Extended Binance transient-error retry (`-4131 PERCENT_PRICE`, `502/503/504`) to
  stop-loss/take-profit/close orders, not just entry orders — a failed SL placement
  already triggers emergency-close, so this closes a real risk gap.
- Added marketable-limit fallback for entry orders when the market order hits a
  transient rejection.
- Rewrote trade narrative to be fact-based instead of templated (fixed a bug where
  weakness classification ran on already-jargon-translated text and silently matched
  nothing).
- Dashboard: fixed thesis repeating the same generic line on every trade, unshaded
  stat cards, jargon cleanup, linked closed trades to their journal entry.
