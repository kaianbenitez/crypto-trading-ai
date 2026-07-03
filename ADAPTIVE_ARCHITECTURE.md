# Adaptive Bot Extension

Do not rewrite the existing bot. The live path remains:

```text
Exchange candles
  -> indicators + SMC context
  -> ensemble signal
  -> per-coin brain adjustment
  -> risk plan
  -> exchange entry + exchange SL/TP
  -> trailing stop manager
  -> close reconciliation
  -> postmortem + per-coin brain update
  -> Telegram/dashboard reports
```

## Added Files

- `agent/learning/per_coin_brain.py`: isolated per-symbol stats, safe param bounds, leg disable/re-enable state.
- `agent/risk/trailing_stop_manager.py`: exchange-side ATR, structure, step, and chandelier stop movement.
- `agent/regime/router.py`: TREND_UP, TREND_DOWN, RANGE, CHOP, HIGH_VOL routing labels.
- `agent/strategy/momentum_kama.py`: volatility-filtered KAMA/Donchian momentum leg.
- `agent/portfolio/dynamic_weights.py`: 14-day Sharpe based leg weights with 10%-50% clamps.
- `agent/meta/self_monitor.py`: daily/hourly health report payloads.
- `agent/telegram/*`: notifier, templates, and safe command scaffolding.
- `agent/dashboard/*`: reasoning and candlestick payload helpers.
- `config/adaptive.yaml`: canonical config schema for the new adaptive layer.

## Database Additions

New additive tables only:

- `per_coin_brain_state`
- `param_change_log`
- `trailing_stop_events`
- `command_audit`
- `self_monitor_reports`

No existing trade columns were changed, so current SQLite data stays compatible.

## Current Wiring

The orchestrator now:

- Applies per-coin brain parameters before opening a trade.
- Stores a cleaner entry Telegram message with confidence, leg, regime, and thesis.
- Moves stops through `TrailingStopManager`, which only tightens and replaces the exchange-side SL order.
- Updates per-coin brain state after each closed trade and sends a concise adaptive update when params/legs change.

## Still To Wire Next

- Add frontend candlestick cards using `/api/candles` and `lightweight-charts`.
- Add Telegram polling/webhook runner for `/status`, `/positions`, `/reasoning`, and confirmed destructive commands.
- Promote `momentum_kama_signal` into the ensemble behind the regime router after a backtest.
- Add tests for all four trailing modes and command confirmation timeouts.
