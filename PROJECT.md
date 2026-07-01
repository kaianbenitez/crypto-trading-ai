# Crypto Trading AI — Project Notes

Read this first if resuming after a context reset.

## Goal
Autonomous crypto trading agent for Binance Futures (testnet first, Bybit-compatible
later via adapter interface). TA/FA/SMC-driven entries, self-tunes parameters after
every trade, optimized for highest win-rate/ROI% without overfitting.

## Key decisions (confirmed with user)
- **Capital:** $1,000 USD recommended bankroll (updated from original $175 — at $1,000
  position sizing is clean, well above Binance minimum notionals, fee drag proportionally
  manageable). Set `BANKROLL_USDT=1000` in `.env`.
- **Execution:** Starting on **Binance Futures testnet** for paper trading (30-day
  minimum), then graduate to live. Exchange-side SL/TP orders always placed so positions
  are protected even if the bot process goes offline.
- **Paper trading duration:** 30 days minimum before going live — need ~25 trades to
  confirm the historical win rate holds forward.
- **Market:** Binance Futures, leveraged. Adapter interface allows Bybit later.
- **Confirmed trading symbols:** XRP/USDT + ETH/USDT (strongest backtest results).
  SOL/ADA/BTC scanned but not traded until they show consistent positive ROI.
- **Timeframe:** 1h primary. MTF scorer uses resampled 4h + 1d for confluence.
- **Self-adaptation:** PARAMETER-ONLY auto-tuning within preset safe bounds after each
  closed trade. Agent must NEVER rewrite strategy logic/code — only numeric params.
- **Risk defaults:** 1.5% risk/trade ($15 at $1k), 5% max daily drawdown kill-switch,
  1 max concurrent position, 3x default leverage / 5x max.
- **Stack:** Python, ccxt, pandas/numpy, `ta` lib, SQLAlchemy (SQLite), pydantic,
  python-dotenv, requests (Telegram). No LLM in the live loop — ever.

## Strategy stack (full, in execution order)

```
Every 1h candle close, per symbol:

1. FA GATE (market_context.py)
   - ATR ratio > 2.5× baseline → block (shock/event in progress)
   - Fear & Greed extreme → reduce size or skip (TODO: wire FA APIs)
   - Event calendar blackout (TODO: FOMC/CPI dates)
   - Funding rate extreme → skip crowded side (TODO)

2. REGIME DETECTION (regime.py)
   - ADX ≥ 25 → TRENDING → run trend_signal (EMA9/21 cross + MACD + volume)
   - ADX < 25  → RANGING  → run mean_reversion_signal (RSI 30/65 + BB touch + volume)

3. MARKET CONTEXT FILTER (market_context.py)
   - Rolling 120-candle window (5 days on 1h) — not 180-day history
   - Structure bias: only take longs in bullish BOS, shorts in bearish BOS
     (bias must be held ≥ 20 candles to be considered confirmed)
   - Premium/discount: price in top 65%+ of range → block longs;
     bottom 35%- of range → block shorts

4. SMC FILTER (smc.py)
   - Order Block nearby → +0.10 confidence boost
   - Fair Value Gap present → +0.05 boost
   - Liquidity sweep just fired → +0.15 boost (strongest SMC signal)
   - SMC is a soft filter (confidence boost), not a hard block

5. MTF CONFLUENCE (mtf_scorer.py)
   - Scores each TF 0-100: EMA, MACD, RSI, ADX, BB, structure, zone, SMC
   - Weights: 1d=40%, 4h=30%, 1h=10%, 15m=5%, 1w=15%
   - Blocks if MTF bias opposes signal direction
   - Blocks if EV < 0.10R (EV = win_prob × TP_mult − loss_prob × SL_mult)

6. RISK ENGINE (risk/engine.py)
   - 1.5% risk/trade → $15 at $1k bankroll
   - SL = ATR × 1.5, TP = ATR × 3.0 (2:1 R:R default)
   - Kill-switch check (both daily DD and manual dashboard toggle)
   - Exchange-side STOP_MARKET + TAKE_PROFIT_MARKET orders placed immediately

7. POST-TRADE
   - DB log: entry reasoning, indicator snapshot, params snapshot
   - On close: post-mortem generated, auto-tuner nudges params
   - Telegram alert on open/close/error
```

## Backtest results summary (2026-07-01, 180d, 1h, walk-forward out-of-sample)

### Confirmed winners (baseline ensemble, fixed params):
| Symbol | WR% | ROI%/fold | MaxDD% | Trades |
|---|---|---|---|---|
| XRP/USDT | 44.3 | +2.85 | 3.00 | 17 |
| ETH/USDT | 35.0 | +0.70 | 4.06 | 17 |

### Do not trade (negative ROI in all modes):
- SOL/USDT, ADA/USDT, BTC/USDT — all negative ROI on this 180-day window

### Mode comparison finding:
SMC+Context and MTF+SMC consistently reduce MaxDD but also cut trade frequency.
With fixed (non-optimized) params, the filters over-cut and hurt ROI. Baseline
ensemble with grid-optimized params performs best for now. SMC/MTF used as
dashboard overlay / reference layer until paper trading calibrates the thresholds.

### Earlier validated result (ETH, grid-optimized, fees+slippage):
- 59.6% win rate, ~2% ROI/fold, 3.35% max DD, 28 trades — this is the target
  to beat or match in live paper trading.

## Expected live performance (XRP + ETH combined, baseline)
- ~3-6 trades/week combined
- ~$15 risk per trade at $1,000 bankroll
- ~4-6% monthly ROI if historical edge holds forward
- 30-day paper trading run → ~25 trades to validate

## Infrastructure
- **VPS:** IONOS, AlmaLinux 9, 2 vCores / 2GB RAM / 90GB NVMe, $2/mo yearly ($24/yr)
  — signed up 2026-07-01. Enough headroom for crypto bot + sports prop hunter later.
- **Deploy:** `deploy/deploy.sh` — one-shot setup for AlmaLinux 9 (uses `dnf` not `apt`)
- **Services:** `deploy/trading-agent.service` + `deploy/webapi.service` (systemd,
  auto-restart on crash/reboot)
- **No Cloudflare needed** — access dashboard via `http://VPS_IP:3000` (password protected).
  Can add Cloudflare Tunnel later for clean URL + SSL if desired.

## How to run locally (dev/test)
```powershell
cd "Crypto Trading AI"
copy .env.example .env          # fill WEBAPI_PASSWORD_HASH + WEBAPI_SECRET_KEY + BANKROLL_USDT=1000
$env:PYTHONPATH="."; py -m uvicorn webapi.main:app --reload --port 8000
```
```powershell
cd "Crypto Trading AI/web"
npm run dev   # http://localhost:3000
```
```powershell
# Run orchestrator locally (paper trading test):
cd "Crypto Trading AI"
$env:PYTHONPATH="."; py -m agent.orchestrator
```

## How to deploy to IONOS VPS
```bash
ssh root@YOUR_VPS_IP
# upload project files (scp or git clone), then:
bash deploy/deploy.sh
# fill in /home/ubuntu/trading-ai/.env with:
#   BINANCE_API_KEY, BINANCE_API_SECRET (testnet keys from testnet.binancefuture.com)
#   BINANCE_TESTNET=true
#   BANKROLL_USDT=1000
#   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (optional but recommended)
#   WEBAPI_PASSWORD_HASH (run: py webapi/hash_password.py)
#   WEBAPI_SECRET_KEY (any random 32+ char string)
sudo systemctl restart trading-agent webapi
```

## Directory layout
```
agent/
  exchange/       - adapter interface + Binance Futures implementation
  strategy/
    indicators.py     - TA indicators (EMA, MACD, RSI, BB, ATR, ADX, volume)
    regime.py         - ADX-based trend/range regime detection
    trend.py          - EMA/MACD trend-following signal
    mean_reversion.py - RSI/BB mean-reversion signal
    ensemble.py       - regime gate + context filter + SMC boost (main signal fn)
    smc.py            - Smart Money Concepts: OB, FVG, liquidity sweeps
    mtf_scorer.py     - Multi-timeframe confluence scorer + EV calculation
  fundamental/
    market_context.py - Rolling 120-candle ATR baseline, structure bias, premium/discount
  risk/
    engine.py         - Position sizing, SL/TP, daily DD kill-switch
  backtest/
    engine.py         - Bar-by-bar simulator, fees+slippage included
    validate.py       - Walk-forward split + grid-search optimizer
  data/
    fetch.py          - OHLCV fetch from exchange
  adapt/
    postmortem.py     - Plain-English trade post-mortem generator
    tuner.py          - Bounded parameter auto-tuner (numeric params only)
  db/
    models.py         - SQLite: Trade table (entry/exit/reasoning/postmortem)
  config/
    settings.py       - Env-driven settings (bankroll, leverage, risk%, etc.)
  orchestrator.py     - MAIN LOOP: polls every 60s, acts on candle close
                        Symbols: XRP/USDT + ETH/USDT (+ SOL/ADA/BTC scan-only)
                        USE_SMC=True, USE_MTF=True toggles at top of file

webapi/             - FastAPI backend (REST + WebSocket)
  main.py           - /api/login, /api/trades, /api/summary, /api/kill-switch, /ws/prices
  auth.py           - bcrypt password auth (SHA-256 pre-hash, no passlib)
  schemas.py        - Pydantic response models

web/                - Next.js frontend
  app/page.tsx      - Dashboard (bankroll, ROI, win rate, kill-switch toggle)
  app/journal/      - Trade journal (expandable rows, entry reasoning, post-mortem)
  app/signals/      - Live price charts (BTC/ETH/SOL via WebSocket)

deploy/
  trading-agent.service  - systemd unit for orchestrator
  webapi.service         - systemd unit for FastAPI
  deploy.sh              - one-shot VPS setup script (AlmaLinux 9 / dnf)

run_backtest.py              - single-symbol backtest (grid-search, full params)
run_backtest_multi.py        - 12-symbol comparison (slow, full grid)
run_backtest_daytrading.py   - 5-strategy × 5-symbol × 2-TF fast comparison
run_backtest_smc.py          - fixed-param baseline vs SMC+Context (fast)
run_backtest_smc_optimized.py- grid-search baseline vs SMC+Context (ETH+XRP)
run_backtest_mtf.py          - 3-mode × 5-symbol MTF comparison (current best runner)
```

## Auth note
passlib is broken with bcrypt>=4.x. `webapi/auth.py` uses `bcrypt` directly with
SHA-256 pre-hash. Do NOT reintroduce passlib.

## Things NOT to do
- Don't let the adapt loop change strategy code — only bounded numeric params.
- Don't skip walk-forward validation.
- Don't go live without the kill-switch wired and tested.
- Don't trade SOL/ADA/BTC until they show positive ROI in paper trading.
- Don't add LLM to the live signal/execution loop.
- Don't use `apt` on the IONOS VPS — it's AlmaLinux (RHEL-based), use `dnf`.

## Next steps (in order)
1. ⏳ Get IONOS VPS IP → run `deploy/deploy.sh` → wire Binance testnet key
2. ⏳ Get Binance testnet API key (testnet.binancefuture.com → API Management)
3. ⏳ Set up Telegram bot (optional but recommended for trade alerts)
4. ⏳ Start 30-day paper trading run on XRP/USDT + ETH/USDT
5. ⏳ After 30 days: review journal, check if win rate matches backtest (~44-59%)
6. ⏳ Wire real Binance API key, graduate to live trading
7. ⏳ Sports prop hunter project (MLB/NBA/WNBA) — same VPS, separate service
