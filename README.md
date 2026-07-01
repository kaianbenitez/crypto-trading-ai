# Crypto Trading AI

Autonomous trading agent for Binance Futures. Runs 24/7 on a VPS, places and manages trades without manual intervention.

## What it does

- Scans XRP/USDT and ETH/USDT on 1h candles
- Detects market regime (trending vs ranging) and picks the right strategy
- Filters trades using Smart Money Concepts (order blocks, fair value gaps, liquidity sweeps)
- Scores multi-timeframe confluence (15m / 1h / 4h / 1d / 1w) before entering
- Places exchange-side stop-loss and take-profit orders so positions are protected even if the bot goes offline
- Auto-tunes numeric parameters after every closed trade
- Web dashboard for monitoring trades, PnL, and kill-switch

## Stack

- **Bot:** Python, ccxt, pandas, ta
- **Backend:** FastAPI + SQLite
- **Frontend:** Next.js
- **Infra:** VPS (systemd services, auto-restart on crash/reboot)

## Paper trading first

The bot runs on Binance Futures **testnet** for a minimum of 30 days before going live. Target: ~25 trades to validate the backtest win rate (44–59% depending on symbol).

## Setup (for the host)

```bash
git clone https://github.com/kaianbenitez/crypto-trading-ai.git trading-ai
cd trading-ai
bash deploy/deploy.sh
```

Then create `.env`:

```
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
BANKROLL_USDT=1000
WEBAPI_SECRET_KEY=any_random_32char_string
WEBAPI_PASSWORD_HASH=        # run: python webapi/hash_password.py
TELEGRAM_BOT_TOKEN=          # optional
TELEGRAM_CHAT_ID=            # optional
```

Start services:

```bash
sudo systemctl enable trading-agent webapi
sudo systemctl start trading-agent webapi
```

Dashboard is at `http://YOUR_VPS_IP:3000`.

## Architecture

See [PROJECT.md](PROJECT.md) for the full strategy stack, backtest results, and all design decisions.
