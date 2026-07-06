# Changelog

All notable changes to this project are logged here, most recent first.
Format is informal — one entry per meaningful change, not strict Keep a Changelog.

## 2026-07-07

- **Redesigned the dashboard's visual language** — a genuine visual overhaul, not
  a rebuild. All 8 tabs (Dashboard, Journal, Coin Watch, Risk, Adaptive, Live Log,
  Settings, Changelog) plus Login now share one system instead of hand-rolled
  inline styles per page:
  - **Component consolidation first**: extracted `Card`, `Badge`, `Button`,
    `StatCard`, `Skeleton` into `web/app/components/ui/`, replacing 4 separate
    copy-pasted `Card` implementations and inline button/badge styling across
    every page.
  - **Design tokens** in `globals.css`: named gradient tokens
    (`--gradient-primary/profit/loss/caution`), a fixed type scale
    (`--text-2xs` through `--text-3xl`), a spacing scale (`--space-1..8`), a
    two-tier radius scale (8px controls / 14px cards / pill badges), motion
    tokens (`--ease-out-expo/quart`, `--dur-fast/base/slow`), an elevation
    scale, and a semantic z-index scale — no more ad hoc 6-20px choices or
    one-off inline gradients per component.
  - **Motion**: hover lift + shadow glow on cards, `:active` press-down on
    buttons, smooth color/border transitions — all via CSS
    `transform`/`opacity`/`box-shadow`/`background` transitions, never
    layout properties. Every animated element respects
    `prefers-reduced-motion` (collapses to instant).
  - **Icons**: installed `@phosphor-icons/react` (no prior icon library) and
    replaced hand-rolled unicode/emoji icons throughout — sidebar nav,
    kill-switch controls, sentiment indicators, status dots, external links.
  - **Responsiveness audit**: fixed two pages (`Live Log`'s gate-stat rows and
    feed rows) that had fixed-width columns which would have broken under
    640px; verified stat grids collapse to single-column and the sidebar
    drawer behavior extends correctly on every page, not just Dashboard.
  - **Accessibility fix**: `--muted` (#4a5570) measured ~2.4:1 against
    `--surface`/`--surface2` — a pre-existing WCAG AA failure (needs 4.5:1)
    affecting secondary/meta text on every page. Lightened to `#8b94a8`
    (~5.6-6:1), verified via manual sRGB relative-luminance calculation.
  - Semantic color meaning preserved exactly (green=profit, red=loss,
    amber=caution/halted, blue=primary/neutral); no API/route/auth changes.
  - Verified via `tsc --noEmit`, `eslint`, a clean `next build` (all 9 routes
    prerender successfully), and live browser screenshots at desktop/tablet
    (768px)/mobile (375px) widths plus a live sidebar-drawer interaction test.

## 2026-07-07

- **Added decision-log observability (no strategy/signal changes).** The agent
  already built a per-cycle `signal_summary` (why each coin did/didn't trade)
  but only logged it to journalctl. Now that same content is persisted and
  exposed over the API so the dashboard can show *why the bot looks idle*:
  - Two new additive tables — `signal_gate_events` (one row per candidate
    rejected at a gate: `no_signal`/`mtf`/`memory`/`cost_edge`/`reentry`/
    `risk_cap`/`leg_disabled`) and `agent_activity_log` (every decision note).
    Both are pruned to a rolling window (activity: 7d/5k rows; gates: 30d).
  - `GET /api/gate-stats?window=24h|7d|30d` — rejection counts per gate,
    ranked, so thresholds can be tuned from data instead of guesswork.
    **No thresholds were changed** — this round is observability only.
  - `GET /api/activity-log?limit=&since=` — the decision feed, newest first.
  - New "Live Log" tab in the dashboard: a why-idle summary strip (top
    rejection reasons over 24h/7d/30d) plus an auto-refreshing, filterable
    (by symbol and level) feed of the agent's per-cycle decisions.
  - The entry/exit path is byte-for-byte unchanged: the 10 rejection sites
    just route their existing log line through one `record()` sink that also
    captures a structured row; writes/pruning happen once per cycle, wrapped
    in try/except so a DB hiccup can never disturb trading.
  - New smoke test `tests/smoke_activity_log.py`.

## 2026-07-06

- **Made the dashboard mobile-responsive (iPhone 13 and similar).** The sidebar
  was a fixed 200px column with no responsive handling at all, so on a phone
  it ate over half the screen width permanently. Added:
  - A shared `.app-shell`/`.page-main` responsive shell (breakpoint 860px,
    matching the existing journal breakpoint) applied across all 7 pages.
  - Sidebar now collapses into a top bar + slide-in drawer on narrow
    viewports (hamburger toggle, backdrop-click/Escape-to-close, body-scroll
    lock while open, closes automatically on navigation).
  - `viewport-fit=cover` + `env(safe-area-inset-*)` padding for the iPhone
    notch/home-indicator safe areas.
  - Nav links and the kill-switch controls (halt/resume/confirm — the most
    safety-critical control per PRODUCT.md) bumped to 44px minimum touch
    targets.
  - Login page: added horizontal edge padding and bumped input/button touch
    targets for narrow screens.
  Note: Turbopack dev server reliably OOMs in this sandbox (confirmed
  repeatedly across sessions), so this was verified via `tsc --noEmit` +
  `eslint` + manual structural review rather than a live browser render —
  please sanity-check on your actual iPhone 13 after deploying.

- **Fixed dashboard/journal "Realized P&L" summing only the last N trades.**
  The main dashboard fetched only the last 15 trades (`api.trades(15)`) and
  summed `pnl_usdt` across whichever of those were closed, instead of the
  true all-time total — so once there were more than ~15 closed trades, the
  stat card silently diverged from reality (in one case showing negative
  while the actual all-time total was positive). The Journal page had the
  same bug at a 100-trade cap. Backend's `/api/summary` already computed the
  correct total-trades/win-rate over *all* closed trades but never returned
  the raw PnL dollar figure — added `total_pnl_usdt` to that response and
  pointed both pages at it instead of re-summing a capped trade fetch.

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
