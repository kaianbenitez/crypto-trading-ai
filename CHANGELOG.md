# Changelog

All notable changes to this project are logged here, most recent first.
Format is informal — one entry per meaningful change, not strict Keep a Changelog.

## 2026-07-09

- **Fixed the dynamic scanner shortlisting testnet-volume artifacts.** On
  Binance testnet, ticker volume is inflated/artificial (confirmed live: SUN
  showed $97M testnet volume vs $3.9M real mainnet volume — a 25x inflation;
  AERO, GRASS, MORPHO, and PENDLE were 40-80x inflated; even BTC/USDT itself
  showed only $25M on testnet, below the $50M floor). Candidates are still
  enumerated from the exchange the bot actually trades on (nothing shortlisted
  that testnet can't execute), but the *quality numbers* now come from
  Binance's real mainnet public tickers:
  - `MARKET_SCAN_USE_MAINNET_LIQUIDITY` (default true) — when on Binance
    testnet, quote volume/bid-ask spread/24h % change for filtering and
    ranking are sourced from Binance's MAINNET public tickers (no API keys,
    read-only, never touches order placement). A symbol with no mainnet
    counterpart is rejected outright (`bad_data`) rather than trusted on
    testnet-only numbers. Falls back to the adapter's own tickers (logged
    clearly) if the mainnet fetch fails. No-op on live trading or non-Binance.
  - `MARKET_SCAN_MAX_ABS_24H_CHANGE_PCT` (default 35%) — rejects abnormal
    event-driven movers before ranking (`abnormal_move`), independent of
    liquidity: confirmed LAB (-53%) and TAC (+69%) both clear the $50M mainnet
    volume floor but are correctly rejected as abnormal moves.
  - `MARKET_SCAN_EXCLUDE_SINGLE_LETTER_BASES` (default false, documented) —
    optional filter for single-letter bases like `M/USDT`.
  - `scan_status`/`/api/roster` now report `liquidity_source`
    (`mainnet_public` | `adapter`) and `selected_detail` (per-candidate
    quote_volume/pct_change/spread_pct/score) alongside the existing
    rejection-reason counts.
  - Live validation run (real testnet + real mainnet tickers, 627 scanned):
    all 7 previously-concerning symbols (SUN, AERO, GRASS, MORPHO, PENDLE,
    LAB, TAC) now correctly rejected; 32 genuinely liquid symbols selected.
  - New `tests/smoke_market_scan_mainnet_liquidity.py` (26 checks).
  - No change to position sizing, max positions, strategy signals, or
    execution exchange/testnet behavior — scanner candidate-quality only.

## 2026-07-08

- **Fixed the 30-day validation so its numbers are trustworthy (10 fixes).** An
  evaluation of `live_readiness`/`choose_risk_tier` found the two most important
  gates were the wrong shape — raw expectancy instead of cost-adjusted, and coin
  *count* instead of coin *concentration* — plus the reported paper stats were
  sized off ~$5,000 testnet equity while validated against the $1,000
  `BANKROLL_USDT` config, silently overstating ROI ~5x. Reporting/validation-only
  changes — no change to how trades are opened, closed, or sized:
  - **Bankroll consistency**: ROI%/drawdown% now normalize each trade against
    its own *snapshotted* `effective_bankroll_usdt` (already recorded at entry),
    not one static config number. R-multiple is confirmed bankroll-independent.
    A startup warning fires when configured bankroll and live equity diverge
    past `BANKROLL_DIVERGENCE_WARN_PCT` (default 20%).
  - **Cost-adjusted expectancy is now the primary gate** (`RISK_PROVEN_MIN_NET_R_AFTER_COST`,
    default +0.10R) — promotion fails if net-after-cost is weak even when raw
    P&L/expectancy is positive. Raw expectancy must also now exceed the
    measured average cost R, not just clear a fixed floor.
  - **Concentration gate replaces the coin-count check**: P&L-excluding-best-coin,
    excluding-top-2-coins, excluding-best-trade, top-coin contribution %, and
    top-3-trades contribution %, each with a pass/fail reason
    (`RISK_PROVEN_MAX_TOP_COIN_PCT`, default 50%). Fails correctly on a single
    coin whose P&L exceeds the account's total.
  - **Calendar-time gate** (`RISK_PROVEN_MIN_DAYS`, default 30) — N trades in one
    lucky week can no longer promote. Anchored to a persisted
    `validation_started_at` (new `AgentState` column), so both a rolling 30-day
    window and a fixed window since that date are reported side by side and
    "proven" status can't silently decay just because trading slowed.
  - **Per-leg readiness** (`RISK_PROVEN_MIN_TRADES_PER_LEG`, default 30) — each
    (strategy, regime) combo validated separately; a proven trend_following
    track record can no longer promote mean_reversion sizing.
  - **Manual/reconcile/duplicate exit trades excluded** from clean validation
    metrics, reported separately (gross vs clean vs reconciliation).
  - **De-noised the recovery-tier trigger**: consecutive-loss threshold raised
    from a hardcoded 2 to `RISK_RECOVERY_LOSS_STREAK_TRIGGER` (default 3) — 2
    losses in a row is ~20% likely for a 55%+ win-rate system on pure variance,
    and the size cut was distorting the very stats being validated.
  - `/api/validation` and `/api/risk-status` now also expose
    `bankroll_divergence_pct`, `metrics_fixed_window`, `readiness_fixed_window`,
    and `validation` (days elapsed/remaining, per-leg readiness summary) —
    additive fields only, nothing removed.
  - New `tests/smoke_validation_fixes.py` (34 checks): bankroll normalization,
    cost-adjusted gate, concentration gate, calendar gate, per-leg isolation,
    recovery de-noising, reconciliation exclusion, and the headline check —
    **the actual reported paper stats classify as NOT READY**, failing
    `sample_size`, `expectancy`, `expectancy_above_cost`, `cost_adjusted_expectancy`,
    `concentration`, and `calendar_time`.

## 2026-07-07 (later)

- **Added a configurable strategy-profile system to reduce double-counting.** The
  full stack layered SMC, news, memory, and adaptive-weight confidence boosts on
  top of a base signal already trend-confirmed by EMA+MACD+ADX and again by MTF —
  so in a trending market the same condition got counted several times, inflating
  confidence and encouraging late entries. Profiles gate which modules may affect
  a decision, without deleting any code:
  - `baseline_simple` (**new default**): base signal + MTF filter + cost/risk
    gates decide. SMC / news / memory / adaptive-weights / coin-brain still run
    and log their read but **cannot** change confidence, EV, sizing, or block/
    approve a trade.
  - `full_agentic`: previous behavior (everything decision-active).
  - `smc_observe` / `memory_observe`: baseline with extra ablation logging.
  - New `STRATEGY_PROFILE` env var; set to `full_agentic` to restore the old
    behavior (backtests read it from params too, so simple vs full can be
    compared later).
  - Every evaluated setup now records a `confidence_breakdown` (base confidence,
    each module's *observed* vs *applied* contribution, final confidence, and the
    decision-active/observe-only module lists) plus a double-counting diagnostic
    that flags when 4+ signals agree but collapse to ≤2 independent reads.
  - Market-context penalty (premium/discount timing) stays decision-active in
    every profile — it only ever *reduces* confidence, so it implements the
    "avoid late/premium entries" rule without contributing to upward stacking.
  - New `/api/strategy-profile` endpoint + a Settings-page card showing the
    active profile and its decides-trades vs observes-only modules.
  - New smoke test `tests/smoke_strategy_profile.py` (27 checks) proving SMC/
    news/memory are observed-but-not-applied under baseline, re-applied under
    full, that news can't manufacture a trade, and that the redundancy flag fires
    correctly.

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
