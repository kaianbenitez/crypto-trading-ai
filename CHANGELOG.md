# Changelog

All notable changes to this project are logged here, most recent first.
Format is informal — one entry per meaningful change, not strict Keep a Changelog.

## 2026-07-06

- **Fixed realized PnL understatement on partial fills.** When a TP order filled
  only part of a position, `trade.qty` was reduced to the remaining size (needed
  for correctly sizing the trailing stop / force-close), but the final PnL
  calculation multiplied the exit price delta by that same reduced qty —
  silently dropping all profit/loss already realized on the filled portion.
  Added `Trade.original_qty` (the true full position size, preserved at entry)
  and now use it for both `get_exit_fill`'s expected quantity and the final PnL
  multiplication, so a blended average exit price across all fill legs produces
  the mathematically correct total. Also fixed the dashboard/journal R-multiple
  calculation, which had the same reduced-qty mismatch. New smoke test
  `tests/smoke_pnl_accounting.py`. Note: this only fixes newly-closed trades
  going forward — already-closed historical trades with partial fills keep
  their (understated) recorded PnL, since the true original fill split can't be
  reconstructed retroactively.

- **Risk & strategy hardening pass** (from a full review of the risk/strategy stack):
  - **Recalibrated the EV model.** The old formula treated the confluence score as a
    literal win probability (a neutral market = 50% win rate), which made the EV floor
    almost never binding, and it computed EV in ATR-units while everything downstream
    treated it as R. EV is now true R multiples with a conservative score→probability
    mapping (neutral ≈ 35%), optionally blended with the bot's own realized win rates
    per confluence bucket (Bayesian prior, refreshed every 6h). Expect noticeably fewer
    trades — the floor actually filters now.
  - **Daily-drawdown state survives restarts.** The loss counter and auto kill-switch
    were in-memory only, so every deploy reset them mid-day. Now persisted to the DB
    and restored at startup (same-day only). Also: day rolls over at UTC midnight
    explicitly, and drawdown is measured on net realized PnL by default
    (`DAILY_DRAWDOWN_MODE=net`; `losses_only` keeps the old stricter behavior).
    A Telegram alert now fires when the daily limit trips.
  - **High-volatility chandelier trail actually fires now.** It was keyed off a regime
    label (`HIGH_VOL`) that the live pipeline never produces — dead code. The trailing
    manager now detects volatility spikes directly from the ATR series (current ATR ≥
    1.8× its 30-candle mean) and switches to the wider chandelier trail.
  - **Trailing-stop replacement can no longer strand a position unprotected.** If
    placing the moved stop fails after the old one was cancelled, the old stop is
    re-placed immediately; if that also fails, a Telegram alert fires and the next
    cycle retries.
  - **Same-direction risk cap tightened 1.5% → 1.0%** (below the portfolio cap) — two
    same-direction alt positions are effectively one levered BTC-beta bet.
  - **Confidence-scaled sizing (down only).** Signals below 0.6 confidence risk
    proportionally less, floored at the minimum entry risk. Never sizes up.
  - **Single-condition mean-reversion entries now require volume confirmation** — a
    lone RSI dip or band touch on thin flow no longer trades.
  - **Breakeven check uses the actual entry-time stop distance** instead of
    reconstructing it from current ATR.
  - New smoke test `tests/smoke_risk_and_ev.py` covers all of the above.

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
