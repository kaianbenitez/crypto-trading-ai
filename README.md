# Crypto Trading AI

Autonomous Binance Futures trading agent with a live dashboard, Telegram alerts,
and adaptive per-coin risk controls. The deployed instance is currently intended
for Binance Futures testnet validation before any live-money use.

## Current Mode

- Exchange: Binance USD-M Futures
- Mode: testnet
- Timeframe: 1h candles
- Bankroll source: `BANKROLL_USDT`
- Default bankroll: `1000` USDT
- Risk ceiling: `MAX_RISK_PER_TRADE_PCT=1.5`
- Default max concurrent positions: `2`
- Default admission: split active risk across slots, then enforce portfolio/same-direction caps
- Active deployment: VPS/systemd

## What It Does

- Scans a dynamic multi-coin roster (see "Dynamic Market Scanner" below) —
  falls back to a fixed 15-coin list (BTC, ETH, XRP, SOL, ADA, BNB, DOGE,
  AVAX, LINK, DOT, POL, LTC, UNI, ATOM, FIL) if the scanner is disabled or
  fails.
- Classifies market regime and routes setups by strategy leg.
- Uses SMC/context filters, trend/mean-reversion logic, and MTF confluence.
- Sizes trades from configured bankroll and stop distance.
- Places reduce-only exchange-side stop-loss and take-profit protection.
- Tracks Binance Futures conditional/algo SL/TP orders correctly.
- Sends Telegram open/close/trailing/report notifications.
- Supports Telegram two-way commands for status, positions, PnL, and reports.
- Shows dashboard metrics, open positions, recent trades, journal, and agent state.
- Stores trade reasoning, indicators, params, postmortems, and adaptive state.

## Risk Sizing

The bot sizes each trade from bankroll, risk percent, and stop distance:

```text
risk_amount = BANKROLL_USDT * (risk_pct / 100)
qty = risk_amount / abs(entry_price - stop_loss)
```

Then it checks notional capacity:

```text
notional = qty * entry_price
must be <= BANKROLL_USDT * leverage
```

`risk_pct` starts from `MAX_RISK_PER_TRADE_PCT`, then can be reduced or adjusted by:

- macro regime size multiplier
- per-coin brain size multiplier
- tuned strategy params
- active risk tier
- slot splitting when `SPLIT_RISK_ACROSS_SLOTS=true`
- portfolio and same-direction risk caps

Example: with `BANKROLL_USDT=1000`, normal tier risk `1.0%`, and
`MAX_CONCURRENT_POSITIONS=2`, the bot targets about `0.5%` per slot.
That is about `5 USDT` risk per trade, with total open risk capped by
`MAX_PORTFOLIO_RISK_PCT` and same-direction BTC-beta exposure capped by
`MAX_SAME_DIRECTION_RISK_PCT`.

## Cost/Edge Gates (fee-aware admission)

Position sizing above answers "how much to risk." These gates separately
answer "is the expected reward worth the round-trip cost at all" — added
because thin wins (a few dollars against several dollars of risk) can net
worse than they look once fees/slippage are counted:

- `MIN_EDGE_AFTER_COST_R` (existing) — raw EV must clear
  `cost_r + MIN_EDGE_AFTER_COST_R`, not just a flat floor.
- `MAX_ESTIMATED_COST_R` — reject if the estimated round-trip cost itself
  exceeds this many R (default `0.20`).
- `MIN_NET_EV_AFTER_COST_R` — reject if `EV - estimated_cost_r` is below this
  floor (default `0.25`), i.e. the edge net of cost must still be meaningful,
  not just technically positive.
- `MIN_EXPECTED_REWARD_COST_MULTIPLE` — reject if the planned reward
  (`atr_mult_tp / atr_mult_sl`, in R) isn't at least this many multiples of
  the estimated cost (default `5x`) — catches setups with a technically
  acceptable EV but a reward too close to the cost to be worth the risk.

None of these change position size — they're rejection-only. Per-trade cost
facts (`gross_r`, `net_r_after_estimated_cost`, `cost_as_pct_of_gross_profit`,
`estimated_round_trip_cost_usdt`, `high_cost_trade`) are stored on
`indicator_snapshot` at entry, and the Risk page's "Fees & cost drag" card
aggregates them across the last 30 days — `avg_net_r_after_estimated_cost`
being meaningfully lower than the raw expectancy is the signal that fees are
eating a real share of the edge.

## Dynamic Market Scanner

`agent/adapt/roster.py` can source the roster's candidate pool from a live
scan of the whole exchange instead of (or in addition to) the fixed 15-coin
list — two stages, so the expensive part (full indicators/SMC/MTF/EV/risk
admission) still only ever runs on a short, curated list:

1. **Stage 1 (cheap)** — one `fetch_tickers()` call across every USDT-M
   perpetual on the exchange. Filters out stablecoins, leveraged tokens,
   configured exclusions, symbols under `MARKET_SCAN_MIN_QUOTE_VOLUME`, and
   spreads over `MARKET_SCAN_MAX_SPREAD_PCT`; ranks the rest by volume
   (80%) + momentum (20%); keeps the top `MARKET_SCAN_TOP_N`.
   `MARKET_SCAN_FIXED_MAJORS` are always included regardless of ranking.
2. **Stage 2 (unchanged)** — only the shortlisted symbols ever reach the
   full strategy stack; the existing 24h roster review (volume recheck,
   win-rate bench/promote, cooldowns) still governs which of them are
   actually *active* at any time.

Refreshes on its own cadence (`MARKET_SCAN_REFRESH_MINUTES`, default 60) and
is force-refreshed once a day alongside the roster review. Falls back to the
fixed `CANDIDATE_SYMBOLS` list — silently, with a warning logged, trading
uninterrupted — if disabled (`DYNAMIC_MARKET_SCAN=false`), unsupported by the
active exchange adapter, or the scan call fails for any reason. Status
(`enabled`/`status`/`last_scan_at`/counts/reject-reasons) is exposed via
`/api/roster`'s `scan` field and shown on the Settings page.

## News Context (cryptocurrency.cv)

Free, no-auth headline context for the daily coin digest and a small
confidence nudge — **never a trading signal on its own, never opens a trade
by itself**. Uses [cryptocurrency.cv](https://cryptocurrency.cv)'s public
news API, which requires a fixed `category` (not an arbitrary coin symbol):
BTC/ETH/SOL map directly to their own category; every other coin falls back
to the "general" market feed, keyword-filtered for the coin name where
possible. Scored with a keyword lexicon (positive/negative crypto terms), not
an LLM — zero ongoing cost, fully deterministic.

CryptoPanic is no longer used (its free tier was discontinued/paywalled).
`CRYPTOPANIC_API_KEY` still exists as a settings field only so an old `.env`
with it set doesn't break anything — nothing reads it anymore.

Any failure (timeout, rate limit, outage, response shape change) degrades to
"no data"/"News unavailable right now — trading continues as usual" instead
of raising; trading is never affected. Set `NEWS_ENABLED=false` to turn it
off entirely (shows "News context is turned off." instead). Status is
exposed via `/api/news-status` and shown on the Settings page.

## Telegram Commands

Send these to the configured Telegram bot:

```text
/help
/status
/positions
/pnl today
/pnl week
/coin BTC
/report daily
/report weekly
/pause all
/resume all
```

Pause/resume commands require a follow-up `confirm`.

Scheduled Telegram reports:

- Morning brief: 08:00 Manila
- End-of-day recap: 23:55 Manila
- Weekly report: Sunday 20:00 Manila

## Setup

```bash
git clone https://github.com/kaianbenitez/crypto-trading-ai.git trading-ai
cd trading-ai
bash deploy/deploy.sh
```

Create `.env` on the VPS:

```env
EXCHANGE=binance
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
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

WEBAPI_SECRET_KEY=any_random_32char_string
WEBAPI_PASSWORD_HASH=run_python_webapi_hash_password

TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional
TELEGRAM_ALLOWED_USER_IDS=optional_comma_separated_user_ids
```

Start/restart services:

```bash
sudo systemctl restart trading-agent webapi dashboard nginx telegram-bot
```

Check health:

```bash
systemctl is-active trading-agent webapi dashboard nginx telegram-bot
journalctl -u trading-agent -n 80 --no-pager
journalctl -u telegram-bot -n 80 --no-pager
```

## Services

- `trading-agent`: strategy scanner, execution, position monitoring
- `webapi`: FastAPI backend
- `dashboard`: Next.js frontend
- `telegram-bot`: Telegram reports and two-way commands
- `nginx`: public reverse proxy

## Trade Narrative

Every trade — open notification, close/postmortem, dashboard card, and journal
entry — is built from one deterministic, fact-based formatter
(`agent/dashboard/trade_narrative.py`, no LLM involved). It reads concrete
values already stored on the `Trade` row (`indicator_snapshot`,
`entry_reasoning`, `params_snapshot`) plus a same-symbol lookback query, so
two trades only read the same when their underlying numbers actually match —
not a fixed template repeated across coins.

- **Direction/strategy** — side, symbol, strategy label
- **Confidence + EV** — the signal's confidence score and expected value in R
- **Thesis** — coin/side/strategy-specific framing (e.g. "BNB is a
  momentum-continuation long, not a value entry"), plus where the entry sits
  in its recent range (late/premium, pullback-like, or mid-range) and whether
  MTF is aligned — composed from `range_position` and `mtf_bias`, not fixed
  wording. The generic "Regime: ..." line is filtered out since it's shown
  separately.
- **Why accepted** — concrete numbers: EV vs the required floor (and whether
  the edge is thin or comfortable), MTF score/confidence, whether risk was
  reduced by a portfolio/same-direction cap or a recovery/drawdown risk tier,
  elevated ATR without a shock-block, and any SMC confluence boost.
- **Weakness** — one line, picked by priority: a flagged entry concern
  (premium/discount-zone, counter-structure bias, a failing memory pattern) if
  one exists; otherwise a thin-EV or elevated-volatility flag if applicable;
  otherwise omitted.
- **Plan** — entry / stop-loss / take-profit / R:R / risk % / risk USDT
- **Invalidation** — what proves the thesis wrong (strategy-specific)
- **Past context** — the last same-symbol trade's outcome, or a negative-
  expectancy flag across the last 3+ same-symbol trades if the sample is
  large enough; says "No useful \<coin\> sample yet" rather than inventing
  context when there's no history
- **Postmortem (closed trades only)** — a failure/result line that ties
  directly back to the entry-time weakness when one was flagged (instead of a
  generic explanation), a lesson, and compact stats (exit reason, R multiple,
  hold duration)

Telegram open/close messages, the dashboard's open-position card, and the
journal's expanded row all render these same sections via
`agent/telegram/templates.py`, `agent/dashboard/reasoning_engine.py`, and the
`/api/trades/{id}/narrative` endpoint respectively. A standalone smoke check
lives at `tests/smoke_trade_narrative.py` — run with the venv's Python from
the repo root (`python -m tests.smoke_trade_narrative` or
`python tests/smoke_trade_narrative.py`) — and asserts that different
range-position/EV/risk/history combinations actually produce different text.

## Dashboard

The dashboard shows:

- bankroll, ROI, PnL, win rate, open positions
- service/agent status
- active symbol roster
- open-position details with structured reasoning (thesis/why-accepted/
  weakness/invalidation/past-context) and chart context
- recent closed trades
- journal with the same structured narrative sections per trade, fetched on
  expand instead of a flat dump of every reasoning line
- Settings page: dynamic market scanner status (enabled/last scan/counts) and
  news provider status
- Risk page: 30-day validation plus a "Fees & cost drag" card (avg estimated
  cost, high-cost trade count, net R after cost, tiny-win count, exit-reason
  breakdown)

## Handoff Docs

- [PROJECT.md](PROJECT.md): full project notes and deployment history
- [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md): current handoff state
- [ADAPTIVE_ARCHITECTURE.md](ADAPTIVE_ARCHITECTURE.md): adaptive/agentic design

## Safety Notes

- Keep `.env` off git.
- Rotate API keys if they were ever pasted into chat or logs.
- Stay on testnet until the bot has enough forward-test data.
- Do not enable live trading without reviewing risk, exchange permissions, and stop/TP behavior.
