# Crypto Trading AI - Claude Code Handoff

Read this first when resuming the project. This file is the current source of truth as of 2026-07-03.

## Current Production/Testnet Status

The bot is deployed and running on the user's IONOS Germany VPS.

- VPS: IONOS Germany, Ubuntu 24.04.4 LTS
- Public dashboard: http://31.70.111.85
- Reverse proxy: Nginx on port 80
- Backend API: FastAPI behind Nginx at `/api/*`, locally on `127.0.0.1:8000`
- Dashboard app: Next.js behind Nginx at `/`, locally on `127.0.0.1:3000`
- Trading agent: systemd service `trading-agent`
- Telegram bot/reports: systemd service `telegram-bot`
- Exchange: Binance USD-M Futures testnet
- Active trading symbols: `BTC/USDT`, `ETH/USDT`, `XRP/USDT`, `SOL/USDT`, `ADA/USDT`, `BNB/USDT`, `DOGE/USDT`, `AVAX/USDT`, `LINK/USDT`, `DOT/USDT`, `POL/USDT`, `LTC/USDT`, `UNI/USDT`, `ATOM/USDT`, `FIL/USDT`
- Current mode: paper/testnet trading, not live money
- Testnet private API verified. Open exposure can exist on testnet; compare Binance positions with DB state before assuming flat exposure.
- Dashboard login was tested successfully
- API `/api/summary` was tested after login and returns bankroll/ROI/PnL/open-position state from the local SQLite DB.

Important: Do not write API keys, API secrets, VPS password, or dashboard plaintext password into this file. Runtime secrets are stored only on the VPS in `/root/trading-ai/.env`.

## Goal

Autonomous crypto trading agent for Binance Futures testnet first, live later only after a minimum 30-day paper trading period. Strategy uses TA, market context, SMC-style confluence, MTF scoring, risk controls, exchange-side SL/TP orders, DB logging, and bounded parameter-only self-tuning after trades close.

No LLM is allowed in the live trading or execution loop.

## Key Decisions

- Capital baseline: `BANKROLL_USDT=1000`
- Current exchange: Binance Futures testnet
- Current symbols: 15-symbol testnet roster listed above
- Timeframe: 1h primary
- Risk defaults:
  - `MAX_RISK_PER_TRADE_PCT=1.5`
  - Treat `1.5%` as the ceiling, not a guaranteed fixed size.
  - Actual risk can be reduced by macro regime sizing, per-coin brain sizing, risk tier, and slot splitting.
  - Normal tier is `1.0%`; with `MAX_CONCURRENT_POSITIONS=2` and `SPLIT_RISK_ACROSS_SLOTS=true`, target risk is about `0.5%` per slot.
  - `MAX_DAILY_DRAWDOWN_PCT=3`
  - `MAX_CONCURRENT_POSITIONS=2`
  - `MAX_PORTFOLIO_RISK_PCT=1.5` caps total open risk.
  - `MAX_SAME_DIRECTION_RISK_PCT=1.5` caps same-direction BTC-beta exposure.
  - `MIN_ENTRY_RISK_PCT=0.25` rejects tiny leftovers after cap downsizing.
  - `MIN_STOP_COST_MULTIPLE=5`
  - `DEFAULT_LEVERAGE=3`
  - `MAX_LEVERAGE=5`
- Paper trading duration: 30 days minimum before live trading
- Target validation: roughly 25 trades, compare live paper win rate/ROI to backtest range
- Self-adaptation: numeric parameter tuning only; never allow the bot to rewrite strategy code

## Current VPS Services

Use these commands over SSH as root:

```bash
systemctl status nginx dashboard webapi trading-agent --no-pager
systemctl status telegram-bot --no-pager
journalctl -u trading-agent -f
journalctl -u telegram-bot -n 100 --no-pager
journalctl -u webapi -n 100 --no-pager
journalctl -u dashboard -n 100 --no-pager
journalctl -u nginx -n 100 --no-pager
```

Expected status:

```text
nginx: active
dashboard: active
webapi: active
trading-agent: active
telegram-bot: active
```

Service files:

```text
/etc/systemd/system/trading-agent.service
/etc/systemd/system/webapi.service
/etc/systemd/system/telegram-bot.service
/etc/systemd/system/dashboard.service
/usr/lib/systemd/system/nginx.service
```

Nginx config:

```text
/etc/nginx/sites-available/trading-ai
/etc/nginx/sites-enabled/trading-ai
```

Nginx routes:

```text
/       -> http://127.0.0.1:3000
/api/   -> http://127.0.0.1:8000
/ws/    -> http://127.0.0.1:8000
```

## Runtime Files On VPS

Project path:

```bash
/root/trading-ai
```

Environment file:

```bash
/root/trading-ai/.env
```

The VPS `.env` contains:

```env
EXCHANGE=binance
BINANCE_API_KEY=<stored on VPS only>
BINANCE_API_SECRET=<stored on VPS only>
BINANCE_TESTNET=true
BANKROLL_USDT=1000
MAX_RISK_PER_TRADE_PCT=1.5
MAX_DAILY_DRAWDOWN_PCT=3
MAX_CONCURRENT_POSITIONS=2
SPLIT_RISK_ACROSS_SLOTS=true
MAX_PORTFOLIO_RISK_PCT=1.5
MAX_SAME_DIRECTION_RISK_PCT=1.5
MIN_ENTRY_RISK_PCT=0.25
MIN_STOP_COST_MULTIPLE=5
DEFAULT_LEVERAGE=3
MAX_LEVERAGE=5
WEBAPI_PASSWORD_HASH=<stored on VPS only>
WEBAPI_SECRET_KEY=<stored on VPS only>
TELEGRAM_BOT_TOKEN=<stored on VPS only>
TELEGRAM_CHAT_ID=<stored on VPS only>
TELEGRAM_ALLOWED_USER_IDS=<optional, stored on VPS only>
```

Do not overwrite `.env` casually. If credentials need rotation, edit it manually and restart services:

```bash
nano /root/trading-ai/.env
systemctl restart webapi trading-agent
```

## Changes Made During Deployment

These changes exist in the local project folder and were also copied to the VPS. They may not be committed/pushed to GitHub yet.

1. `agent/exchange/binance_futures.py`
   - Replaced deprecated `ccxt.binance(...).set_sandbox_mode(True)` path.
   - Uses `ccxt.binanceusdm`.
   - Sets `options.fetchCurrencies=False` to avoid spot/SAPI auth calls.
   - When `BINANCE_TESTNET=true`, directly points USD-M futures endpoints to `https://testnet.binancefuture.com`.
   - Verified private testnet calls work: balance and positions.

2. `agent/orchestrator.py`
   - Uses the 15-symbol candidate roster from `agent.adapt.roster.CANDIDATE_SYMBOLS`.
   - Recovers open DB trades on startup.
   - Recovers Binance Futures conditional/algo SL/TP order IDs on startup.
   - Normalizes Binance futures symbols such as `ADA/USDT:USDT` before comparing open positions.
   - Applies per-coin brain and macro size adjustments before risk sizing.

3. `agent/config/settings.py`
   - Default exchange changed from `bybit` to `binance`.

4. `.env.example`
   - Added `EXCHANGE=binance`.
   - Updated bankroll default to `1000`.
   - Added dashboard auth env keys.

5. `deploy/deploy.sh`
   - Updated for Ubuntu 24.04 / `apt`.
   - Installs Node 22 from NodeSource because Next.js 16 requires Node >=20.9.
   - Builds the Next.js frontend.
   - Installs/enables `dashboard`, `webapi`, and `trading-agent` services.

6. `deploy/dashboard.service`
   - Added systemd service for Next.js production server on port 3000.

6a. `deploy/telegram-bot.service`
   - Added systemd service for Telegram scheduled reports and two-way commands.

7. `web/lib/api.ts`
   - Browser API URL now resolves from current host instead of hardcoded `localhost:8000`.
   - This matters because visitors' browsers cannot call VPS `localhost`.

8. `webapi/main.py`
   - CORS loosened to allow dashboard access from VPS/public origin.
   - Added richer open-position, candle, coin-brain, and adaptive activity endpoints.

9. Nginx installed directly on VPS
   - Added reverse proxy so public dashboard works at `http://31.70.111.85` without exposing `:3000` or `:8000`.

## Git / Deployment Caveat

The VPS was deployed from a local tarball, not from a fresh GitHub clone, because the Codex sandbox could not push to GitHub. The remote GitHub repo may be behind the actual running code.

Before future redeploys, Claude Code should:

```bash
cd "C:\Users\kbeni\Downloads\Crypto Trading AI"
git status
```

Review and commit the deployment changes listed above, then push to GitHub if desired. Do not commit `.env`, database files, logs, or any credentials.

Known local generated artifacts that should not be committed:

```text
.env
trading_agent.db
*.log
node_modules/
.next/
data_cache/
backtest_*_out.txt
```

## Strategy Stack

Every 1h candle close, per symbol:

1. FA / market shock gate
   - ATR ratio > 2.5x baseline blocks shock/event conditions.
   - Fear & Greed, event calendar, and funding-rate gates are TODOs.

2. Regime detection
   - ADX >= 25: trending mode, trend signal.
   - ADX < 25: ranging mode, mean-reversion signal.

3. Market context filter
   - Rolling 120-candle context window.
   - Structure bias filter.
   - Premium/discount range filter.

4. SMC soft filter
   - Order block nearby: confidence boost.
   - Fair value gap: confidence boost.
   - Liquidity sweep: strongest boost.

5. MTF confluence
   - 1h plus higher timeframe context.
   - Blocks opposing MTF bias.
   - Blocks low expected value (`MIN_EDGE_AFTER_COST_R` floor).
   - Extra cost/edge gates (reject-only, never resize): `MAX_ESTIMATED_COST_R`,
     `MIN_NET_EV_AFTER_COST_R`, `MIN_EXPECTED_REWARD_COST_MULTIPLE` — see
     `agent/orchestrator.py::_cost_edge_metrics`/`_cost_edge_gate`. Added
     because thin wins ($3-5 against $3.75-4.50 risked) can net worse than
     they look once round-trip fees/slippage are counted; these require the
     planned reward to actually clear cost by a real margin, not just clear
     a flat EV floor.

6. Risk engine
   - Position sizing from bankroll and risk percent.
   - `MAX_RISK_PER_TRADE_PCT=1.5` is the current ceiling.
   - Effective risk may be lower after macro and per-coin adjustments.
   - Formula: `risk_amount = BANKROLL_USDT * effective_risk_pct / 100`; `qty = risk_amount / abs(entry - stop_loss)`.
   - SL = ATR x 1.5.
   - TP = ATR x 3.0.
   - Daily drawdown kill-switch.
   - Exchange-side reduce-only stop-loss/take-profit orders after entry.
   - Binance Futures conditional/algo orders must be checked via `fapiPrivateGetOpenAlgoOrders`, not only normal open-order endpoints.

7. Post-trade
   - Trade logged to SQLite.
   - Post-mortem generated.
   - Numeric params may be tuned within bounds.
   - Per-coin brain can adjust size/SL/TP/trailing within bounds after enough data.
   - Telegram alerts and scheduled reports are enabled when env vars are configured.

## Dynamic Market Scanner

`agent/adapt/roster.py`, extended (not replaced) — two stages:

1. **Stage 1** (`discover_market_universe`, cheap): one
   `adapter.fetch_all_tickers()` call (Binance `fetch_tickers()` with no
   args, one request for every USDT-M perpetual). Filters, in order:
   - stablecoin bases (`USDC`, `BUSD`, `TUSD`, `FDUSD`, `DAI`, `USDP`, `PYUSD`,
     `USTC`, `EUR`, `GBP`, `GUSD`, `USDD`)
   - leveraged-token markers (`UP`, `DOWN`, `BULL`, `BEAR` in the base)
   - synthetic index/dominance products (`_is_index_product`: an explicit
     denylist — `BTCDOM`, `ETHDOM`, `DEFI`, `ALTS`, `TOTAL`, `ALT` — plus
     anything ending in `DOM`). **Found live in testing**: `BTCDOM/USDT`
     (Binance's BTC-dominance index perpetual) cleared the volume filter
     and got shortlisted despite not being a real coin at all — this
     denylist plus the market-cap filter below both exclude it
     independently, so it's caught even if one filter is disabled/down.
   - `MARKET_SCAN_EXCLUDE_SYMBOLS`
   - market-cap rank (see below)
   - `quoteVolume < MARKET_SCAN_MIN_QUOTE_VOLUME`
   - spread over `MARKET_SCAN_MAX_SPREAD_PCT` (skipped if the ticker has no
     bid/ask)
   - anything that isn't a `.../USDT` perpetual (ccxt symbols like
     `BTC/USDT:USDT` are normalized by stripping the `:USDT` settlement
     suffix)

   Ranks by `volume_score*0.8 + momentum_score*0.2` (volume is the real
   gate; momentum is a tiebreaker, not a reason to trade an illiquid pump).
   Keeps top `MARKET_SCAN_TOP_N`; `MARKET_SCAN_FIXED_MAJORS` are always
   prepended regardless of rank.

   **Market-cap/rank filter** (`get_top_market_cap_symbols`,
   `MARKET_SCAN_REQUIRE_MARKET_CAP_RANK`): a live scan found several
   micro-cap tokens (`GUA`, `BAS`, `EPIC`, `MAGMA`, `AKE`, `ARPA`, `AT`,
   `VELVET`) that technically cleared the $50M volume floor. Cross-checks
   symbol bases against CoinGecko's top `MARKET_SCAN_MIN_MARKET_CAP_RANK`
   coins by market cap (`/coins/markets`, free, no key, one request, cached
   `MARKET_SCAN_MARKET_CAP_REFRESH_HOURS`). If that API call fails, the
   filter is skipped for that cycle (logs a warning) rather than rejecting
   every candidate — degrades to volume-only filtering, never blocks the
   scan entirely.
2. **Stage 2** (unchanged): only `CoinRoster.candidate_pool()`'s output ever
   reaches the full indicator/SMC/MTF/EV/risk-admission stack in
   `orchestrator.py`. The existing daily review (volume recheck, win-rate
   bench/promote, cooldowns) still governs what's *active* right now.

`CoinRoster.refresh_market_scan()` caches the scan for
`MARKET_SCAN_REFRESH_MINUTES` (default 60), is called opportunistically every
orchestrator cycle (cheap no-op if not stale) and force-refreshed once a day
in `daily_review()`. On any failure (adapter doesn't support
`fetch_all_tickers`, network error, empty result) it logs a warning and
serves the last good cache, or `CANDIDATE_SYMBOLS` if there isn't one yet —
this can never raise into the main loop or block trading.

Scan status persists to `RosterState.scan_status` (new column, JSON) so the
separate `webapi` process can read it — the live `CoinRoster` only exists in
`trading-agent`'s memory. Exposed at `GET /api/roster`'s `scan` field.

## News Context (cryptocurrency.cv)

`agent/fundamental/news_sentiment.py` was rewritten off CryptoPanic (free
tier discontinued/paywalled) onto
[cryptocurrency.cv](https://cryptocurrency.cv)'s free, no-auth API
(`GET /api/news?category=...`). Real response shape (confirmed live):
`{"articles": [{"title", "link", "description", "pubDate", "source", ...}], "totalCount", ...}`
— an empty `category` param returns `articles: []`, so a category is always
required. It only supports a fixed category list (`general`, `bitcoin`,
`ethereum`, `solana`, `defi`, `nft`, ... — no arbitrary coin symbols), so:
- BTC → `bitcoin`, ETH → `ethereum`, SOL → `solana` (direct category)
- everything else → `general`, keyword-filtered for the coin name in the
  title/description (falls back to the unfiltered general feed if no
  headline mentions the coin)

Scored with the same keyword lexicon as before (no LLM, zero ongoing cost).
Every failure mode (timeout, HTTP error, malformed/changed JSON shape,
disabled via `NEWS_ENABLED=false`) is caught inside `fetch_headlines`/
`get_sentiment` and returns `[]`/`NewsSentiment(label="no data")` — this can
never raise into the orchestrator or the daily digest job.

News affects the live strategy in exactly one place:
`agent/fundamental/coin_digest.py::apply_sentiment_adjustment`, a ±0.05
confidence nudge already gated behind a fresh (<36h) daily digest read — this
was not changed by the provider swap. **News never opens a trade by itself.**

Dashboard/digest wording: "News unavailable right now — trading continues as
usual" (fetch failed) vs "News context is turned off." (`NEWS_ENABLED=false`)
— replaced the old "not tracked" phrasing, which read as an error state
rather than a normal disabled/no-data state. Status exposed at
`GET /api/news-status`.

## Trade Narrative Format

Open/close Telegram messages, the dashboard open-position card, and the
journal's expanded row are all built from `agent/dashboard/trade_narrative.py`
(`build_narrative(trade, session)`) — a deterministic, **fact-based**
composer, not a fixed template. No LLM in the loop; every line is assembled
from concrete values already on the `Trade` row, so two trades only read the
same when the underlying numbers genuinely match (verified by
`tests/smoke_trade_narrative.py`).

Sections produced:

- **Thesis** — coin/side/strategy-specific framing composed from real fields,
  not boilerplate:
  - `trend_following` → "{COIN} is a momentum-continuation {side}, not a
    value entry."; `mean_reversion` → "{COIN} is a mean-reversion {side} at a
    stretched extreme, not a trend-following play."
  - `range_position` picks the entry-location phrase: long + `>=0.7` → late/
    premium-zone continuation; long + `<=0.3` → pullback-like entry; short +
    `<=0.3` → discount-zone chase warning; short + `>=0.7` → well-located
    short.
  - `mtf_bias` vs `side` → "MTF is aligned with the trade" or "MTF is mixed
    against the higher timeframe."
  - The generic `"Regime: ..."` entry_reasoning line is filtered out (shown
    separately as the strategy/regime label) so thesis text isn't identical
    across trades that only share a regime.
- **Why accepted** — concrete numbers, not adjectives:
  - `mtf_ev` vs `min_required_ev_r` → "thin, barely cleared the floor" when
    the margin is under 25% of the requirement, "cleared comfortably" when
    the margin exceeds the requirement itself.
  - `mtf_score` + `confidence` as a compact fact line.
  - `actual_risk_pct` vs `planned_risk_pct` → explains size reduction, citing
    the recovery/drawdown risk tier or the portfolio/same-direction cap.
  - `atr_ratio` → notes elevated volatility that stayed under the shock-block
    threshold.
  - `smc_boost` → mentioned only when present (order block/FVG/liquidity
    sweep confluence).
- **Weakness** — one line, chosen by priority: an entry-time concern
  (premium/discount-zone, counter-structure bias, a failing memory pattern,
  negative news) if one was flagged; else a thin-EV or elevated-ATR flag if
  applicable; else omitted entirely (not padded with a generic sentence).
- **Plan** — entry / stop-loss / take-profit / R:R, plus risk % and risk USDT
  read from `indicator_snapshot.actual_risk_pct` / `actual_risk_usdt`
  (falls back to the planned values, then to `|entry-stop|*qty`).
- **Invalidation** — strategy-specific ("EMA/MACD flips against the trade"
  for trend_following, "price keeps pushing into the extreme" for
  mean_reversion).
- **Past context** — a lightweight `session.query(Trade)` lookback (last 5
  same-symbol closed trades): if 3+ exist and their combined expectancy is
  negative, flags that explicitly ("size should stay reduced"); otherwise
  reports the single most recent trade's outcome. Says "No useful \<coin\>
  sample yet" rather than inventing context when there's no history.
- **Postmortem (closed only)** — the failure/result line ties directly back
  to the entry-time weakness when one existed (e.g. "this points more to
  premium-zone entry than a normal trend continuation") instead of a generic
  explanation, plus a lesson line and compact stats (`Exit reason | R | Held`).

Telegram format example (`agent/telegram/templates.py`):

```
🟢 LONG | BNB/USDT | trend_following
Conf 0.50 | EV +1.66R | Risk 0.45%

Thesis:
BNB is a momentum-continuation long, not a value entry. MTF is aligned with the trade; entry is late — price is already near the upper end of its recent range.

Why accepted:
EV +1.66R vs required +0.42R — edge cleared the cost floor comfortably. MTF 70, confidence 0.50. Risk was reduced to 0.45% (from 1.50% planned) because the portfolio/same-direction risk cap reduced size (another position is already open).

Weakness:
Premium-zone entry: this is vulnerable if momentum stalls.

Plan:
Entry 6.86 | SL 6.79 | TP 7.01 | R:R 2.0
Invalidation: Stop-loss hit, or price closes back below the trend average / MACD flips against the trade.

Past:
No useful BNB sample yet.
```

```
🔴 CLOSED | AVAX/USDT | LOSS | -7.20 USDT

Why it failed:
Stopped out before reaching meaningful profit. This points more to premium-zone entry than a normal trend continuation.

Lesson:
Don't treat a strong thesis as enough on its own when premium-zone entry is present — require a stronger edge (higher EV), a better entry, or smaller size.

Stats:
Exit reason: stop_loss | R: -1.0R | Held: 12m
```

Same sections are exposed to the frontend via:
- `agent/dashboard/reasoning_engine.py` → `/api/open-positions-detail` (open positions)
- `webapi/main.py` → `/api/trades/{id}/narrative` (journal, fetched on row expand)

Smoke check: `tests/smoke_trade_narrative.py` builds fake trades with different
`range_position`/EV/risk/history combinations directly against the real
`Trade` model (in-memory SQLite) and asserts the resulting thesis/weakness/
why-accepted/past-context text actually differs where it should. Run it with
the VPS venv from the repo root: `venv/bin/python tests/smoke_trade_narrative.py`.

## Backtest Notes

Backtest summary from 2026-07-01, 180d, 1h, walk-forward out-of-sample:

| Symbol | WR% | ROI%/fold | MaxDD% | Trades |
|---|---:|---:|---:|---:|
| XRP/USDT | 44.3 | +2.85 | 3.00 | 17 |
| ETH/USDT | 35.0 | +0.70 | 4.06 | 17 |

Those backtests are historical context only. The running paper/testnet bot now scans the full 15-symbol roster to gather forward data across majors and liquid alts.

Earlier ETH grid-optimized result:

```text
59.6% win rate, about 2% ROI/fold, 3.35% max DD, 28 trades
```

Expected paper performance if historical edge holds:

```text
3-6 trades/week combined
about $15 risk per trade at $1,000 bankroll
actual risk may be lower, e.g. $10.50 when macro size multiplier is 0.70
about 4-6% monthly ROI target, not guaranteed
```

## Local Development

Backend:

```powershell
cd "C:\Users\kbeni\Downloads\Crypto Trading AI"
$env:PYTHONPATH="."
py -m uvicorn webapi.main:app --reload --port 8000
```

Frontend:

```powershell
cd "C:\Users\kbeni\Downloads\Crypto Trading AI\web"
npm run dev
```

Agent locally:

```powershell
cd "C:\Users\kbeni\Downloads\Crypto Trading AI"
$env:PYTHONPATH="."
py -m agent.orchestrator
```

## Useful VPS Commands

Restart web stack:

```bash
systemctl restart nginx dashboard webapi
```

Restart trading agent:

```bash
systemctl restart trading-agent
```

Stop trading agent immediately:

```bash
systemctl stop trading-agent
```

Disable trading agent on reboot:

```bash
systemctl disable trading-agent
```

Enable/start trading agent:

```bash
systemctl enable --now trading-agent
```

Check active ports:

```bash
ss -ltnp | grep -E ':80|:3000|:8000'
```

Test local web stack from VPS:

```bash
curl -I http://127.0.0.1
curl -s http://127.0.0.1/api/summary
```

Note: `/api/summary` should return `401 Unauthorized` unless authenticated.

## Auth Note

`passlib` is broken with bcrypt >=4.x in this project context. `webapi/auth.py` uses `bcrypt` directly with SHA-256 pre-hash. Do not reintroduce `passlib`.

## Hard Safety Rules

- Do not go live before the full 30-day paper trading review.
- Do not switch `BINANCE_TESTNET=false` without explicit user approval.
- Do not treat `1.5%` as mandatory risk; it is the ceiling.
- Keep macro/per-coin risk reducers active.
- Do not add an LLM to signal generation, risk, or execution.
- Do not let adaptation modify code or strategy logic.
- Do not commit secrets.
- Do not expose port 8000 directly unless there is a reason; use Nginx proxy.
- Keep exchange-side SL/TP behavior intact.
- Keep kill-switch behavior intact.

## Immediate Next Steps For Claude Code

1. Run `git status` locally and review all uncommitted deployment changes.
2. Commit and push the VPS deployment fixes to GitHub.
3. Confirm `agent/exchange/binance_futures.py` uses the direct Binance Futures testnet URL patch and Binance algo-order handling.
4. Confirm `agent/orchestrator.py` uses the intended 15-symbol testnet roster.
5. Monitor the first 24 hours of paper trading logs:

```bash
ssh root@31.70.111.85
journalctl -u trading-agent -f
```

6. Watch dashboard at `http://31.70.111.85`.
7. Verify Telegram `/status`, `/positions`, and scheduled reports.
8. After 30 days, review closed trades, win rate, ROI, drawdown, and post-mortems before any live-trading discussion.
