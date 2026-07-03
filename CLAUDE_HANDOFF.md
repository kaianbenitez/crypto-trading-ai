# Claude Code Handoff - Crypto Trading AI

Current as of 2026-07-03.

## Latest Codex Update - Adaptive Extension Deployed

Status: deployed to VPS `/root/trading-ai` and services restarted successfully.

Do not clamp coins. The current active roster is the full 15-symbol candidate set:

`BTC/USDT`, `ETH/USDT`, `XRP/USDT`, `SOL/USDT`, `ADA/USDT`, `BNB/USDT`, `DOGE/USDT`, `AVAX/USDT`, `LINK/USDT`, `DOT/USDT`, `POL/USDT`, `LTC/USDT`, `UNI/USDT`, `ATOM/USDT`, `FIL/USDT`.

New additive adaptive modules:

- `agent/learning/per_coin_brain.py`
- `agent/risk/trailing_stop_manager.py`
- `agent/regime/router.py`
- `agent/strategy/momentum_kama.py`
- `agent/portfolio/dynamic_weights.py`
- `agent/meta/self_monitor.py`
- `agent/telegram/notifier.py`
- `agent/telegram/templates.py`
- `agent/telegram/commander.py`
- `agent/dashboard/reasoning_engine.py`
- `agent/dashboard/candlestick_panel.py`
- `config/adaptive.yaml`
- `ADAPTIVE_ARCHITECTURE.md`

New DB tables are additive and already exist on VPS:

- `per_coin_brain_state`
- `param_change_log`
- `trailing_stop_events`
- `command_audit`
- `self_monitor_reports`

Runtime wiring now active:

- Per-coin brain can adjust risk/SL/TP/trailing params before entry.
- Legs can be disabled per coin by the per-coin brain.
- `TrailingStopManager` owns exchange-side SL replacement and only moves stops in the profitable direction.
- Entry/close/trail Telegram formatting now uses compact emoji templates with confidence/leg/regime/reasoning.
- `/api/open-positions-detail`, `/api/candles/{symbol}`, `/api/coin-brains`, and `/api/adaptive-activity` are available behind auth for dashboard wiring.

Verification already done on VPS:

- `python -m compileall agent webapi reconcile_trade_fills.py` passed.
- `systemctl is-active webapi trading-agent dashboard nginx` returned all `active`.
- Trading-agent logs after restart show all 15 symbols evaluated with no startup exception.
- Unauthenticated `/api/summary` returns `401`, so auth remains enforced.

Frontend chart/reasoning update:

- `web/lib/api.ts` now includes typed calls for open-position details and candles.
- `web/app/page.tsx` renders live candlestick cards for open positions using `lightweight-charts`.
- Each open position card shows entry/SL/TP overlays, trail trajectory if present, confidence, leg/regime, trail mode, and THESIS/NOW/NEXT reasoning.
- `web/app/globals.css` includes a responsive rule so the chart and reasoning stack on phone screens.
- Built locally and on VPS with `npm run build`; dashboard restarted and returned HTTP `200`.

Remaining next steps:

- Backtest and explicitly promote `momentum_kama_signal` into the production ensemble before allowing it to trade.
- Add unit/scenario tests for ATR, structure, step, and chandelier trailing modes.

Telegram scheduled reports and two-way commands:

- Added `agent/telegram/service.py` as a polling Telegram bot service.
- Added `agent/telegram/reports.py` for morning brief, end-of-day recap, weekly report, status, positions, PnL, and coin summaries.
- Added `deploy/telegram-bot.service`; installed/enabled on VPS.
- New DB state table: `telegram_bot_state`.
- New/used audit table: `command_audit`.
- VPS verification: `telegram-bot`, `trading-agent`, `webapi`, `dashboard`, and `nginx` all active.
- On first start, service marks existing Telegram updates as seen so old setup messages are not answered.

Scheduled Telegram reports:

- Morning brief: daily at 08:00 Manila.
- End-of-day recap: daily at 23:55 Manila.
- Weekly report: Sunday at 20:00 Manila.

Telegram commands:

- `/status`
- `/positions`
- `/pnl today|week|month|all`
- `/coin BTC`
- `/report daily|weekly`
- `/pause all` with `confirm`
- `/resume all` with `confirm`
- `/help`

## July 3 Resume Notes

The user continued work with another agent while Codex was limited. New pasted log notes show:

- The agent was running and evaluating symbols hourly.
- A trend-signal volume gate was removed from Tier 2 trend entries.
- An ETH/USDT LONG opened on testnet.
- The ETH trade later closed and was reported as a small loss, but the close accounting is likely wrong.
- Diagnosis: `_check_close()` used the latest 1m candle close as `exit_price` after the exchange-side SL/TP had already closed the position. This can materially understate or overstate PnL.

Local fixes now applied:

- `agent/exchange/binance_futures.py`
  - Added `fetch_order()`, `fetch_my_trades()`, and `get_exit_fill()`.
  - `get_exit_fill()` aggregates actual opposite-side account fills after trade open time.

- `agent/orchestrator.py`
  - Close handling now tries real exchange fills first.
  - Falls back to latest 1m candle only with a warning.
  - Recovers open DB trades on startup so restarts do not leave open trades unmanaged.

- `reconcile_trade_fills.py`
  - Added dry-run/apply script to correct already-closed DB trades from actual Binance fills.
  - Use on VPS after deploying the adapter patch:

```bash
cd /root/trading-ai
PYTHONPATH=. venv/bin/python reconcile_trade_fills.py
PYTHONPATH=. venv/bin/python reconcile_trade_fills.py --apply
```

Earlier safety fixes, later superseded by the user's "don't clamp coins" instruction:

- `agent/adapt/roster.py`
  - The temporary ETH/XRP clamp was reverted.
  - `MAX_ACTIVE = 15` and the DB active roster is the full 15-symbol list.

- `webapi/main.py`
  - Restored dashboard/API auth checks.
  - Restored authenticated `/api/summary`, `/api/trades`, `/api/agent-status`, and kill-switch endpoints.
  - Status endpoint reports the full 15-symbol roster.

Important: the current VPS password provided by the user worked, and the latest adaptive extension has been deployed.

## Current Status

The bot is deployed and running on the user's IONOS Germany VPS.

- Dashboard: http://31.70.111.85
- VPS OS: Ubuntu 24.04.4 LTS
- Runtime path: `/root/trading-ai`
- Exchange: Binance USD-M Futures testnet
- Live trading mode: paper/testnet only
- Active symbols: full 15-symbol roster listed above
- Do not switch to real/live funds without explicit user approval and 30-day paper criteria
- Telegram alerts: configured and test message sent successfully
- Nginx reverse proxy: public port 80 routes dashboard and API

Expected services:

```bash
systemctl status nginx dashboard webapi trading-agent --no-pager
```

Expected:

```text
nginx active
dashboard active
webapi active
trading-agent active
```

## Secrets

Do not commit or print secrets.

Secrets live on the VPS in:

```bash
/root/trading-ai/.env
```

That file contains Binance API credentials, Telegram bot token/chat ID, dashboard auth hash, and web API secret.

## Dashboard Login

Dashboard URL:

```text
http://31.70.111.85
```

Dashboard auth is already configured on the VPS. Do not write plaintext dashboard password into repo files.

## Important Code Changes Not Necessarily Pushed

The VPS was deployed from local files/tarball, not guaranteed from GitHub. Before redeploying, run:

```powershell
cd "C:\Users\kbeni\Downloads\Crypto Trading AI"
git status
```

Review, commit, and push these important changes:

- `agent/exchange/binance_futures.py`
  - Uses `ccxt.binanceusdm`.
  - Avoids deprecated `set_sandbox_mode(True)`.
  - Sets `options.fetchCurrencies=False`.
  - Points Binance USD-M Futures testnet endpoints to `https://testnet.binancefuture.com`.
  - Verified private testnet calls work: balance and positions.

- `agent/orchestrator.py`
  - Live symbol list restricted to:

```python
SYMBOLS = ["ETH/USDT", "XRP/USDT"]
```

- `webapi/main.py`
  - Added `/api/agent-status`.
  - CORS supports the dashboard origin.

- `webapi/schemas.py`
  - Added `AgentStatusOut`.

- `web/lib/api.ts`
  - Uses current browser origin by default instead of hardcoded `localhost:8000`.
  - Added `agentStatus()`.

- `web/app/page.tsx`
  - Refreshed dashboard UI.
  - Added agent status, service status, risk panel, open positions, recent closed trades.

- `web/app/globals.css`, `web/app/components/NavBar.tsx`
  - Cleaner dark UI styling.

- `deploy/deploy.sh`
  - Ubuntu 24.04 support.
  - Installs Node 22.
  - Builds frontend.
  - Installs/enables `dashboard`, `webapi`, `trading-agent`.

- `deploy/dashboard.service`
  - Added Next.js production service.

- `run_backtest_trend_breakout.py`
  - Added challenger 4H trend + 1H breakout backtest.

## Verified Runtime Checks

Binance testnet verification succeeded:

```text
exchange=binance
testnet=True
balance=5000.0 USDT
open_positions=0
ETH candles fetched
XRP candles fetched
```

Agent log confirmed:

```text
Symbols: ['ETH/USDT', 'XRP/USDT']
Testnet: True
Bankroll: $1000.0
Exchange: Binance Futures
Heartbeat, kill_switch=False
```

## Telegram Alerts

Telegram is configured on the VPS and a test alert was sent successfully.

Desired alert style:

```text
🤖 AI Trading Digest
🕙 02 Jul 2026, 22:45 PH

🆕 NEW SIGNALS
🟢 XRP/USDT LONG | Conf 74% | EV +0.31R
🧠 1H trend + 4H bias aligned; ATR normal.

⚠️ ATTENTION
🟡 ETH/USDT weakening | EV +0.18R → +0.04R
🧠 BTC context turned bearish; volume faded.

📊 Dashboard: http://31.70.111.85
```

Trade open alerts should be concise:

```text
🚀 OPENED XRP/USDT LONG
📊 Conf 74% | EV +0.31R | Risk 15 USDT

🎯 Entry 2.1840 | 🛑 SL 2.1512 | 💰 TP 2.2496
🧩 Strategy: trend_context_mtf

🧠 Reason: 1H trend + 4H bias aligned; price not in premium zone.
📚 Past: Similar XRP longs 4W/2L, avg +0.37R.

📊 Dashboard: http://31.70.111.85
```

Avoid noisy candle-by-candle Telegram spam. Telegram should be for:

- bot start/stop
- trade opened
- trade closed
- stop-loss/take-profit placement failures
- kill switch events
- daily summary
- optional scan digest

## Current Dashboard

Dashboard now has:

- top status row
- agent status
- testnet/live mode
- bankroll
- ROI
- win rate
- open positions count
- trading state panel
- service health panel
- risk panel
- dedicated Open Positions section
- dedicated Recent Closed Trades section

Public check returned HTTP 200.

Authenticated `/api/agent-status` returned active service states.

## Strategy Notes

Current live bot remains the original ensemble/SMC/MTF strategy, trading only `ETH/USDT` and `XRP/USDT`.

Backtest summary from original project notes:

```text
XRP/USDT: WR 44.3%, ROI +2.85%/fold, MaxDD 3.00%, 17 trades
ETH/USDT: WR 35.0%, ROI +0.70%/fold, MaxDD 4.06%, 17 trades
```

Expected frequency:

```text
~3-6 trades/week combined
roughly 1 trade every 1-2 days, but uneven
```

No trade yet is normal. Bot acts only on approved 1h candle-close setups.

## Challenger Strategy Backtest

Added `run_backtest_trend_breakout.py`.

Strategy:

- 4H trend filter
- 1H breakout execution
- ATR volatility filter
- ATR x2 SL
- ATR x4 TP

Backtested on 180 days for BTC/SOL/ADA:

```text
BTC/USDT   WR 19.6% | ROI -2.72% | MaxDD 4.43% | 23 trades
SOL/USDT   WR 34.0% | ROI -0.19% | MaxDD 2.89% | 23 trades
ADA/USDT   WR 30.2% | ROI -0.49% | MaxDD 3.15% | 24 trades
```

Conclusion: do not enable BTC/SOL/ADA live yet, even with the challenger strategy. SOL was closest but still negative.

## Safety Rules

- Do not switch `BINANCE_TESTNET=false` without explicit user approval.
- Do not commit `.env` or credentials.
- Do not trade BTC/SOL/ADA yet.
- Do not add LLMs to signal generation or execution.
- Do not let adaptation rewrite strategy code.
- Keep exchange-side SL/TP behavior.
- Keep dashboard kill switch working.
- Keep max concurrent positions conservative.

## Useful VPS Commands

```bash
ssh root@31.70.111.85
cd /root/trading-ai

systemctl status nginx dashboard webapi trading-agent --no-pager
journalctl -u trading-agent -f
journalctl -u webapi -n 100 --no-pager
journalctl -u dashboard -n 100 --no-pager

systemctl restart webapi dashboard
systemctl restart trading-agent
systemctl stop trading-agent
systemctl enable --now trading-agent
```

Check ports:

```bash
ss -ltnp | grep -E ':80|:3000|:8000'
```

## Immediate Next Steps

1. Commit and push current local changes to GitHub.
2. Monitor `journalctl -u trading-agent -f` for the first trade.
3. Add richer Telegram trade reasoning and past-context summaries.
4. Add daily Telegram digest if desired.
5. After 15 days, review early paper stats but do not go live yet.
6. After 30 days, review full paper trading performance before any live-money decision.
