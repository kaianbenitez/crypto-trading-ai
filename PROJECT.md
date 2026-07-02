# Crypto Trading AI - Claude Code Handoff

Read this first when resuming the project. This file is the current source of truth as of 2026-07-02.

## Current Production/Testnet Status

The bot is deployed and running on the user's IONOS Germany VPS.

- VPS: IONOS Germany, Ubuntu 24.04.4 LTS
- Public dashboard: http://31.70.111.85
- Reverse proxy: Nginx on port 80
- Backend API: FastAPI behind Nginx at `/api/*`, locally on `127.0.0.1:8000`
- Dashboard app: Next.js behind Nginx at `/`, locally on `127.0.0.1:3000`
- Trading agent: systemd service `trading-agent`
- Exchange: Binance USD-M Futures testnet
- Active trading symbols: `ETH/USDT`, `XRP/USDT` only
- Current mode: paper/testnet trading, not live money
- Testnet private API verified: balance read returned `5000.0 USDT`; open positions returned `0`
- Dashboard login was tested successfully
- API `/api/summary` was tested after login and returned zero trades, zero open positions, bankroll `1000.0`

Important: Do not write API keys, API secrets, VPS password, or dashboard plaintext password into this file. Runtime secrets are stored only on the VPS in `/root/trading-ai/.env`.

## Goal

Autonomous crypto trading agent for Binance Futures testnet first, live later only after a minimum 30-day paper trading period. Strategy uses TA, market context, SMC-style confluence, MTF scoring, risk controls, exchange-side SL/TP orders, DB logging, and bounded parameter-only self-tuning after trades close.

No LLM is allowed in the live trading or execution loop.

## Key Decisions

- Capital baseline: `BANKROLL_USDT=1000`
- Current exchange: Binance Futures testnet
- Current symbols: `ETH/USDT`, `XRP/USDT`
- Do not trade `SOL/USDT`, `ADA/USDT`, or `BTC/USDT` until they show consistent positive ROI in forward/paper results
- Timeframe: 1h primary
- Risk defaults:
  - `MAX_RISK_PER_TRADE_PCT=1.5`
  - `MAX_DAILY_DRAWDOWN_PCT=5`
  - `MAX_CONCURRENT_POSITIONS=1`
  - `DEFAULT_LEVERAGE=3`
  - `MAX_LEVERAGE=5`
- Paper trading duration: 30 days minimum before live trading
- Target validation: roughly 25 trades, compare live paper win rate/ROI to backtest range
- Self-adaptation: numeric parameter tuning only; never allow the bot to rewrite strategy code

## Current VPS Services

Use these commands over SSH as root:

```bash
systemctl status nginx dashboard webapi trading-agent --no-pager
journalctl -u trading-agent -f
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
```

Service files:

```text
/etc/systemd/system/trading-agent.service
/etc/systemd/system/webapi.service
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
MAX_DAILY_DRAWDOWN_PCT=5
MAX_CONCURRENT_POSITIONS=1
DEFAULT_LEVERAGE=3
MAX_LEVERAGE=5
WEBAPI_PASSWORD_HASH=<stored on VPS only>
WEBAPI_SECRET_KEY=<stored on VPS only>
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
   - Restricted live symbol list to:

```python
SYMBOLS = ["ETH/USDT", "XRP/USDT"]
```

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

7. `web/lib/api.ts`
   - Browser API URL now resolves from current host instead of hardcoded `localhost:8000`.
   - This matters because visitors' browsers cannot call VPS `localhost`.

8. `webapi/main.py`
   - CORS loosened to allow dashboard access from VPS/public origin.

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
   - Blocks low expected value.

6. Risk engine
   - Position sizing from bankroll and risk percent.
   - SL = ATR x 1.5.
   - TP = ATR x 3.0.
   - Daily drawdown kill-switch.
   - Exchange-side stop-loss/take-profit orders after entry.

7. Post-trade
   - Trade logged to SQLite.
   - Post-mortem generated.
   - Numeric params may be tuned within bounds.
   - Telegram alerts optional if env vars are configured.

## Backtest Notes

Backtest summary from 2026-07-01, 180d, 1h, walk-forward out-of-sample:

| Symbol | WR% | ROI%/fold | MaxDD% | Trades |
|---|---:|---:|---:|---:|
| XRP/USDT | 44.3 | +2.85 | 3.00 | 17 |
| ETH/USDT | 35.0 | +0.70 | 4.06 | 17 |

Do not trade these yet:

```text
SOL/USDT
ADA/USDT
BTC/USDT
```

Earlier ETH grid-optimized result:

```text
59.6% win rate, about 2% ROI/fold, 3.35% max DD, 28 trades
```

Expected paper performance if historical edge holds:

```text
3-6 trades/week combined
about $15 risk per trade at $1,000 bankroll
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
- Do not trade SOL/ADA/BTC yet.
- Do not add an LLM to signal generation, risk, or execution.
- Do not let adaptation modify code or strategy logic.
- Do not commit secrets.
- Do not expose port 8000 directly unless there is a reason; use Nginx proxy.
- Keep exchange-side SL/TP behavior intact.
- Keep kill-switch behavior intact.

## Immediate Next Steps For Claude Code

1. Run `git status` locally and review all uncommitted deployment changes.
2. Commit and push the VPS deployment fixes to GitHub.
3. Confirm `agent/exchange/binance_futures.py` uses the direct Binance Futures testnet URL patch.
4. Confirm `agent/orchestrator.py` trades only `ETH/USDT` and `XRP/USDT`.
5. Monitor the first 24 hours of paper trading logs:

```bash
ssh root@31.70.111.85
journalctl -u trading-agent -f
```

6. Watch dashboard at `http://31.70.111.85`.
7. Set up Telegram alerts if the user wants mobile notifications.
8. After 30 days, review closed trades, win rate, ROI, drawdown, and post-mortems before any live-trading discussion.