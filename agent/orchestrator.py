"""Main orchestrator loop — runs the trading agent continuously.

Cycle (every 1h candle close):
  1. Fetch recent candles for each symbol
  2. Run FA gate (ATR shock check via market context)
  3. Run SMC + TA ensemble to generate signal
  4. Risk engine gates sizing and kill-switch
  5. Place market entry + exchange-side SL/TP orders (Binance holds these
     even if this process is offline — safe for unattended operation)
  6. Monitor open positions for fill confirmation
  7. On close: log post-mortem, run bounded auto-tuner
  8. Telegram alert on every meaningful event

Hard rules enforced here:
  - Never modifies strategy logic or code — only numeric params via tuner
  - Kill-switch checked before every order
  - Max 1 concurrent position per symbol, 1 symbol active at a time
  - Exchange-side SL/TP always placed immediately after entry fill

Run with:
  cd "Crypto Trading AI"
  py -m agent.orchestrator
  (or as a systemd service on the VPS)
"""
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from agent.adapt.postmortem import generate_postmortem
from agent.adapt.tuner import tune_parameters, diff_params
from agent.config.settings import settings
from agent.backtest.engine import SimpleSettings
from agent.db.models import Trade, get_session
from agent.exchange.binance_futures import BinanceFuturesAdapter
from agent.exchange.bybit_futures import BybitFuturesAdapter
from agent.fundamental.market_context import add_market_context
from agent.risk.engine import RiskEngine
from agent.strategy.ensemble import generate_signal
from agent.strategy.indicators import add_indicators
from agent.strategy.mtf_scorer import compute_confluence, resample_ohlcv
from agent.strategy.signal import Side
from agent.strategy.smc import add_smc
from agent.backtest.validate import BASE_PARAMS
from agent.adapt.memory import save_lesson, apply_memory

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOLS    = ["ETH/USDT", "XRP/USDT"]
TIMEFRAME  = "1h"
CANDLES    = 200          # enough for all indicators + 120-candle context window
POLL_SEC   = 60           # check for new candle every 60s
USE_SMC    = True         # toggle SMC+Context filters (set False for baseline mode)
USE_MTF    = True         # multi-timeframe confluence filter
MTF_MIN_CONFLUENCE = 55   # minimum weighted score to allow entry
BE_TRIGGER_R    = 1.0     # arm breakeven after +1R unrealised profit
MAX_TRADE_HOURS = 48      # force-close if trade still open after this many hours

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("orchestrator.log"),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram helper (optional — silently skipped if token not configured)
# ---------------------------------------------------------------------------

def _tg(message: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": message},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


# ---------------------------------------------------------------------------
# Candle helpers
# ---------------------------------------------------------------------------

def _candle_close_timestamp(tf: str) -> int:
    """Returns the UTC timestamp (ms) of the most recently closed 1h candle."""
    now_ms = int(time.time() * 1000)
    if tf == "1h":
        period_ms = 3_600_000
    elif tf == "15m":
        period_ms = 900_000
    else:
        period_ms = 3_600_000
    return (now_ms // period_ms) * period_ms


def _fetch_df(adapter: BinanceFuturesAdapter, symbol: str) -> pd.DataFrame:
    candles = adapter.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLES)
    df = pd.DataFrame([{
        "open": c.open, "high": c.high, "low": c.low,
        "close": c.close, "volume": c.volume, "timestamp": c.timestamp,
    } for c in candles])
    return df.sort_values("timestamp").reset_index(drop=True)


def _prepare_df(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = add_indicators(df, params)
    if USE_SMC:
        df = add_market_context(df, params)
        df = add_smc(df, params)
    return df.dropna().reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-symbol state
# ---------------------------------------------------------------------------

class SymbolState:
    def __init__(self, symbol: str):
        self.symbol        = symbol
        self.last_candle   = 0        # timestamp of last processed candle
        self.open_trade_id = None     # DB Trade.id of the open position
        self.sl_order_id   = None
        self.tp_order_id   = None
        self.params        = dict(BASE_PARAMS, context_window_candles=120, max_atr_ratio=2.5)
        self.be_armed      = False    # True once breakeven SL has been placed


# ---------------------------------------------------------------------------
# Trade lifecycle
# ---------------------------------------------------------------------------

def _open_trade(
    adapter: BinanceFuturesAdapter,
    session,
    risk: RiskEngine,
    state: SymbolState,
    signal,
    row: pd.Series,
    params: dict,
) -> bool:
    """Size, place, and log a new entry. Returns True if order went through."""
    plan = risk.plan_trade(state.symbol, signal.side, row["close"], row["atr"])

    if not plan.approved:
        log.info(f"[{state.symbol}] Trade rejected by risk engine: {plan.reject_reason}")
        return False

    if plan.qty <= 0:
        log.info(f"[{state.symbol}] Zero qty computed — skipping")
        return False

    # Set leverage before entry
    try:
        adapter.set_leverage(state.symbol, plan.leverage)
    except Exception as e:
        log.warning(f"[{state.symbol}] set_leverage failed: {e}")

    entry_side = "buy" if signal.side == Side.LONG else "sell"

    # Market entry
    try:
        entry = adapter.place_market_order(state.symbol, entry_side, plan.qty)
    except Exception as e:
        log.error(f"[{state.symbol}] Entry order failed: {e}")
        _tg(f"❌ {state.symbol} entry FAILED: {e}")
        return False

    fill_price = entry.price or row["close"]

    # Exchange-side SL/TP (held by Binance even if this process goes offline)
    try:
        sl_order = adapter.place_stop_loss(state.symbol, entry_side, plan.qty, plan.stop_loss)
        state.sl_order_id = sl_order.order_id
    except Exception as e:
        log.error(f"[{state.symbol}] Stop-loss order failed: {e}")
        _tg(f"⚠️ {state.symbol} SL order FAILED — position open without SL: {e}")

    try:
        tp_order = adapter.place_take_profit(state.symbol, entry_side, plan.qty, plan.take_profit)
        state.tp_order_id = tp_order.order_id
    except Exception as e:
        log.warning(f"[{state.symbol}] Take-profit order failed: {e}")

    # Log to DB
    trade = Trade(
        symbol=state.symbol,
        side=signal.side.value,
        strategy_name=signal.strategy_name,
        regime=str(signal.indicator_snapshot.get("regime", "unknown")),
        entry_price=fill_price,
        qty=plan.qty,
        stop_loss=plan.stop_loss,
        take_profit=plan.take_profit,
        leverage=plan.leverage,
    )
    trade.set_entry_reasoning(signal.reasoning)
    trade.set_indicator_snapshot(signal.indicator_snapshot)
    trade.set_params_snapshot(params)
    session.add(trade)
    session.commit()

    state.open_trade_id = trade.id
    risk.mark_position_opened(state.symbol)

    msg = (
        f"📈 {state.symbol} {signal.side.value.upper()} opened\n"
        f"Entry: {fill_price:.4f} | SL: {plan.stop_loss:.4f} | TP: {plan.take_profit:.4f}\n"
        f"Qty: {plan.qty:.4f} | Leverage: {plan.leverage}x\n"
        f"Reason: {signal.reasoning[0] if signal.reasoning else '-'}"
    )
    log.info(f"[{state.symbol}] " + msg.replace("\n", " | "))
    _tg(msg)
    return True


def _check_close(
    adapter: BinanceFuturesAdapter,
    session,
    risk: RiskEngine,
    state: SymbolState,
) -> bool:
    """Check if the open position has been closed; also handles BE arm + force-close.
    Returns True if position is now closed."""
    trade = session.get(Trade, state.open_trade_id)
    if not trade:
        return True

    try:
        open_positions = adapter.get_open_positions()
        open_syms = {p["symbol"].replace("/", "") for p in open_positions}
        clean_sym = state.symbol.replace("/", "")
        still_open = clean_sym in open_syms
    except Exception as e:
        log.warning(f"[{state.symbol}] get_open_positions failed: {e}")
        still_open = True  # assume open if we can't check

    if still_open:
        # --- Breakeven auto-arm ---
        if not state.be_armed:
            try:
                candles = adapter.fetch_ohlcv(state.symbol, "1m", limit=1)
                current_price = candles[-1].close if candles else None
                if current_price and trade.stop_loss:
                    from agent.strategy.signal import Side as _Side
                    trade_side = _Side.LONG if trade.side == "long" else _Side.SHORT
                    atr_mult_sl = state.params.get("atr_mult_sl", 1.5)
                    atr = abs(trade.entry_price - trade.stop_loss) / atr_mult_sl
                    new_sl = risk.check_breakeven(
                        trade_side, trade.entry_price, current_price, atr,
                        be_trigger_r=BE_TRIGGER_R, atr_mult_sl=atr_mult_sl,
                    )
                    if new_sl is not None:
                        # Cancel old SL order and place new one at breakeven
                        be_side = "sell" if trade.side == "long" else "buy"
                        try:
                            if state.sl_order_id:
                                adapter.cancel_order(state.symbol, state.sl_order_id)
                            sl_order = adapter.place_stop_loss(state.symbol, be_side, trade.qty, new_sl)
                            state.sl_order_id = sl_order.order_id
                            state.be_armed = True
                            log.info(f"[{state.symbol}] BE armed — SL moved to {new_sl:.4f}")
                            _tg(f"🛡️ {state.symbol} breakeven armed — SL → {new_sl:.4f}")
                        except Exception as e:
                            log.warning(f"[{state.symbol}] BE arm failed: {e}")
            except Exception as e:
                log.warning(f"[{state.symbol}] BE check failed: {e}")

        # --- Time-based force close ---
        if trade.opened_at:
            hours_open = (datetime.now(timezone.utc) - trade.opened_at).total_seconds() / 3600
            if hours_open >= MAX_TRADE_HOURS:
                log.info(f"[{state.symbol}] Force-closing after {hours_open:.1f}h (max {MAX_TRADE_HOURS}h)")
                _tg(f"⏰ {state.symbol} force-closed after {hours_open:.0f}h")
                try:
                    close_side = "sell" if trade.side == "long" else "buy"
                    adapter.place_market_order(state.symbol, close_side, trade.qty)
                    # Cancel outstanding SL/TP
                    for oid in [state.sl_order_id, state.tp_order_id]:
                        if oid:
                            try:
                                adapter.cancel_order(state.symbol, oid)
                            except Exception:
                                pass
                except Exception as e:
                    log.error(f"[{state.symbol}] Force-close order failed: {e}")
                    return False
                still_open = False  # fall through to close logic below

        if still_open:
            return False

    # Position is gone — closed by exchange (SL/TP triggered) or force-closed above
    # Determine exit price and reason from the current market price (approximation)
    try:
        candles = adapter.fetch_ohlcv(state.symbol, "1m", limit=1)
        exit_price = candles[-1].close if candles else trade.entry_price
    except Exception:
        exit_price = trade.entry_price

    direction  = 1 if trade.side == "long" else -1
    raw_pnl    = (exit_price - trade.entry_price) * direction * trade.qty
    # Estimate exit reason: if pnl negative hit SL, if positive hit TP
    exit_reason = "take_profit" if raw_pnl > 0 else "stop_loss"
    outcome     = "win" if raw_pnl > 0 else ("loss" if raw_pnl < 0 else "breakeven")

    trade.exit_price  = exit_price
    trade.pnl_usdt    = raw_pnl
    trade.outcome     = outcome
    trade.exit_reason = exit_reason
    trade.closed_at   = datetime.now(timezone.utc)

    postmortem = generate_postmortem(trade)
    trade.set_postmortem(postmortem)
    session.commit()

    risk.record_trade_result(raw_pnl)
    risk.mark_position_closed(state.symbol)

    # Auto-tune params from last 20 closed trades
    recent = (
        session.query(Trade)
        .filter(Trade.symbol == state.symbol, Trade.closed_at.isnot(None))
        .order_by(Trade.closed_at.desc())
        .limit(20)
        .all()
    )
    new_params = tune_parameters(recent, state.params)
    changes    = diff_params(state.params, new_params)
    if changes:
        log.info(f"[{state.symbol}] Param nudge: {changes}")
    state.params = new_params

    # Save per-symbol lesson to memory
    try:
        save_lesson(trade, session)
        log.info(f"[{state.symbol}] Memory lesson saved")
    except Exception as e:
        log.warning(f"[{state.symbol}] Memory save failed: {e}")

    emoji = "✅" if outcome == "win" else "❌"
    msg = (
        f"{emoji} {state.symbol} {trade.side.upper()} CLOSED\n"
        f"Exit: {exit_price:.4f} | PnL: {raw_pnl:+.2f} USDT | {outcome.upper()}\n"
        f"Reason: {exit_reason}"
    )
    log.info(f"[{state.symbol}] " + msg.replace("\n", " | "))
    _tg(msg)

    state.open_trade_id = None
    state.sl_order_id   = None
    state.tp_order_id   = None
    state.be_armed      = False
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    log.info("=" * 60)
    log.info("Orchestrator starting")
    log.info(f"Symbols: {SYMBOLS} | TF: {TIMEFRAME} | SMC: {USE_SMC}")
    log.info(f"Testnet: {settings.binance_testnet} | Bankroll: ${settings.bankroll_usdt}")
    log.info("=" * 60)
    _tg(f"🤖 Trading bot started\nSymbols: {', '.join(SYMBOLS)}\nTestnet: {settings.binance_testnet}")

    if settings.exchange == "bybit":
        adapter = BybitFuturesAdapter()
        log.info("Exchange: Bybit Futures")
    else:
        adapter = BinanceFuturesAdapter()
        log.info("Exchange: Binance Futures")
    session  = get_session()
    exch_settings = SimpleSettings(
        bankroll_usdt=settings.bankroll_usdt,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        max_daily_drawdown_pct=settings.max_daily_drawdown_pct,
        max_concurrent_positions=settings.max_concurrent_positions,
        default_leverage=settings.default_leverage,
        max_leverage=settings.max_leverage,
    )
    risk   = RiskEngine(exch_settings)
    states = {s: SymbolState(s) for s in SYMBOLS}

    heartbeat_every = 6   # log heartbeat every N cycles (~6h)
    cycle = 0

    while True:
        cycle += 1
        now_candle = _candle_close_timestamp(TIMEFRAME)

        for symbol, state in states.items():
            try:
                # Check kill-switch from DB (in case dashboard toggled it)
                from webapi.app_state import get_or_create_state as get_agent_state
                try:
                    agent_state = get_agent_state(session)
                    if agent_state.kill_switch_active:
                        risk.kill_switch_active = True
                except Exception:
                    pass  # webapi state table may not exist yet

                # --- Monitor open position ---
                if state.open_trade_id is not None:
                    _check_close(adapter, session, risk, state)
                    continue  # one position per symbol at a time

                # --- Only act on a new candle close ---
                if now_candle <= state.last_candle:
                    continue

                # --- Fetch + prepare data ---
                df = _fetch_df(adapter, symbol)
                if len(df) < 50:
                    log.warning(f"[{symbol}] Not enough candles ({len(df)}), skipping")
                    continue

                df = _prepare_df(df, state.params)
                if len(df) < 2:
                    continue

                row  = df.iloc[-1]
                prev = df.iloc[-2]

                # --- Kill-switch hard check ---
                if risk.kill_switch_active:
                    log.info(f"[{symbol}] Kill-switch active — no new entries")
                    state.last_candle = now_candle
                    continue

                # --- Generate signal ---
                signal = generate_signal(row, prev, state.params)

                if signal.is_actionable and signal.confidence > 0:
                    # --- MTF confluence gate ---
                    if USE_MTF:
                        try:
                            tf_dfs = {"1h": df}
                            raw_1h = _fetch_df(adapter, symbol)
                            for tf in ("4h", "1d"):
                                tf_dfs[tf] = resample_ohlcv(raw_1h, tf)
                            # Fetch 4h directly for more candles
                            candles_4h = adapter.fetch_ohlcv(symbol, "4h", limit=100)
                            tf_dfs["4h"] = pd.DataFrame([{
                                "open": c.open, "high": c.high, "low": c.low,
                                "close": c.close, "volume": c.volume, "timestamp": c.timestamp,
                            } for c in candles_4h])

                            mtf = compute_confluence(
                                tf_dfs, state.params,
                                signal_side=signal.side.value,
                            )
                            signal.indicator_snapshot["mtf_score"]     = round(mtf["weighted_score"], 1)
                            signal.indicator_snapshot["mtf_bias"]      = mtf["overall_bias"]
                            signal.indicator_snapshot["mtf_ev"]        = round(mtf.get("ev") or 0, 2)
                            signal.indicator_snapshot["mtf_confluence"] = round(mtf["confluence_pct"], 1)

                            if not mtf["approved"]:
                                log.info(f"[{symbol}] MTF blocked: {mtf['block_reason']}")
                                state.last_candle = now_candle
                                continue

                            log.info(
                                f"[{symbol}] MTF score={mtf['weighted_score']:.1f} "
                                f"bias={mtf['overall_bias']} EV={mtf.get('ev', 0):.2f}R ✓"
                            )
                        except Exception as e:
                            log.warning(f"[{symbol}] MTF scorer failed (continuing): {e}")

                    # --- Memory check ---
                    try:
                        mem_delta, mem_notes = apply_memory(symbol, signal, row, session)
                        if mem_delta != 0:
                            signal.confidence = max(0.0, min(1.0, signal.confidence + mem_delta))
                            for note in mem_notes:
                                signal.reasoning.append(note)
                                log.info(f"[{symbol}] {note}")
                            signal.indicator_snapshot["memory_delta"] = round(mem_delta, 2)
                    except Exception as e:
                        log.warning(f"[{symbol}] Memory check failed (continuing): {e}")

                    # Block if memory tanked confidence below actionable threshold
                    if signal.confidence <= 0:
                        log.info(f"[{symbol}] Memory reduced confidence to zero — skipping")
                        state.last_candle = now_candle
                        continue

                    log.info(
                        f"[{symbol}] Signal: {signal.side.value.upper()} "
                        f"confidence={signal.confidence:.2f} — {signal.reasoning[0]}"
                    )
                    _open_trade(adapter, session, risk, state, signal, row, state.params)
                else:
                    log.debug(f"[{symbol}] No signal this candle")

                state.last_candle = now_candle

            except Exception as e:
                log.error(f"[{symbol}] Unhandled error in main loop: {e}", exc_info=True)
                _tg(f"⚠️ [{symbol}] Loop error: {e}")

        # Heartbeat
        if cycle % heartbeat_every == 0:
            log.info(f"Heartbeat — cycle {cycle}, kill_switch={risk.kill_switch_active}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()
