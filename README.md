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

- Scans a multi-coin roster:
  - BTC, ETH, XRP, SOL, ADA, BNB, DOGE, AVAX, LINK, DOT, POL, LTC, UNI, ATOM, FIL
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

## Handoff Docs

- [PROJECT.md](PROJECT.md): full project notes and deployment history
- [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md): current handoff state
- [ADAPTIVE_ARCHITECTURE.md](ADAPTIVE_ARCHITECTURE.md): adaptive/agentic design

## Safety Notes

- Keep `.env` off git.
- Rotate API keys if they were ever pasted into chat or logs.
- Stay on testnet until the bot has enough forward-test data.
- Do not enable live trading without reviewing risk, exchange permissions, and stop/TP behavior.
