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
- Default risk: `MAX_RISK_PER_TRADE_PCT=1.5`
- Default max concurrent positions: `1`
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

Example: with `BANKROLL_USDT=1000` and `MAX_RISK_PER_TRADE_PCT=1.5`, base risk is
`15 USDT`. If macro size is `0.70`, trade risk becomes `10.50 USDT`.

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
MAX_DAILY_DRAWDOWN_PCT=5
MAX_CONCURRENT_POSITIONS=1
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

## Dashboard

The dashboard shows:

- bankroll, ROI, PnL, win rate, open positions
- service/agent status
- active symbol roster
- open-position details with reasoning and chart context
- recent closed trades
- journal with entry reasoning and postmortem

## Handoff Docs

- [PROJECT.md](PROJECT.md): full project notes and deployment history
- [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md): current handoff state
- [ADAPTIVE_ARCHITECTURE.md](ADAPTIVE_ARCHITECTURE.md): adaptive/agentic design

## Safety Notes

- Keep `.env` off git.
- Rotate API keys if they were ever pasted into chat or logs.
- Stay on testnet until the bot has enough forward-test data.
- Do not enable live trading without reviewing risk, exchange permissions, and stop/TP behavior.
