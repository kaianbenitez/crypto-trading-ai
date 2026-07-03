"""Main orchestrator loop — runs the trading agent continuously.

Cycle (polls every 60s, evaluates at each 1h candle close):
  1. Fetch recent candles for each symbol
  2. Run ensemble signal (ATR shock → regime → TA → context → SMC)
  3. MTF confluence gate
  4. Memory + adaptive weight adjustments
  5. Risk engine sizes and places entry + exchange-side SL/TP
  6. Monitor open positions (BE arm, force-close after 48h)
  7. On close: postmortem, auto-tuner, memory lesson, weight update
  8. Self-monitoring: tracks idle hours, logs signal summaries

Hard rules:
  - Never modifies strategy logic — only numeric params via tuner
  - Kill-switch checked before every order
  - Max 1 concurrent position per symbol
  - Exchange-side SL/TP always placed immediately after entry fill
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
from agent.adapt.weights import update_weights, apply_weights
from agent.adapt.roster import CoinRoster, CANDIDATE_SYMBOLS
from agent.fundamental.macro import assess_macro
from agent.learning.per_coin_brain import PerCoinBrain
from agent.risk.trailing_stop_manager import TrailingStopManager
from agent.telegram import templates as tg_templates

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOLS    = CANDIDATE_SYMBOLS
TIMEFRAME  = "1h"
CANDLES    = 200
POLL_SEC   = 60
USE_SMC    = True
USE_MTF    = True
BE_TRIGGER_R    = 1.0
MAX_TRADE_HOURS = 48

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
# Telegram helper
# ---------------------------------------------------------------------------

def _tg(message: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    import requests
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.status_code == 200:
            return
        log.warning(f"Telegram Markdown send failed ({r.status_code}): {r.text[:200]} — retrying as plain text")
    except Exception as e:
        log.warning(f"Telegram Markdown send raised: {e} — retrying as plain text")

    # Fallback: strip Markdown formatting chars and send as plain text so
    # a malformed thesis/reflection string never silently drops a notification.
    plain = message.replace("`", "").replace("*", "").replace("_", "")
    try:
        r = requests.post(url, json={"chat_id": settings.telegram_chat_id, "text": plain}, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram plain-text send also failed ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        log.error(f"Telegram send failed completely: {e}")


# ---------------------------------------------------------------------------
# Candle helpers
# ---------------------------------------------------------------------------

def _candle_close_timestamp(tf: str) -> int:
    now_ms = int(time.time() * 1000)
    if tf == "1h":
        period_ms = 3_600_000
    elif tf == "15m":
        period_ms = 900_000
    else:
        period_ms = 3_600_000
    return (now_ms // period_ms) * period_ms


def _normalize_position_symbol(symbol: str | None) -> str:
    """Normalize spot/futures symbol variants like ADA/USDT:USDT."""
    if not symbol:
        return ""
    base = str(symbol).split(":", 1)[0]
    return base.replace("/", "").replace("-", "").upper()


def _same_price(a: float | None, b: float | None, tolerance: float = 0.002) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) / max(abs(float(b)), 1e-9) <= tolerance


def _recover_protective_order_ids(adapter, state, trade) -> None:
    if not hasattr(adapter, "fetch_open_algo_orders"):
        return
    try:
        orders = adapter.fetch_open_algo_orders(trade.symbol)
    except Exception as e:
        log.warning(f"[{trade.symbol}] Protective order recovery failed: {e}")
        return

    close_side = "SELL" if trade.side == "long" else "BUY"
    for order in orders:
        if str(order.get("side", "")).upper() != close_side:
            continue
        if str(order.get("algoStatus", "")).upper() != "NEW":
            continue
        if str(order.get("reduceOnly", "")).lower() not in {"true", "1"} and order.get("reduceOnly") is not True:
            continue
        order_type = str(order.get("orderType", "")).upper()
        trigger = float(order.get("triggerPrice") or 0)
        algo_id = str(order.get("algoId") or "")
        if not algo_id:
            continue
        if order_type == "STOP_MARKET" and _same_price(trigger, trade.stop_loss):
            state.sl_order_id = algo_id
        elif order_type == "TAKE_PROFIT_MARKET" and _same_price(trigger, trade.take_profit):
            state.tp_order_id = algo_id

    if state.sl_order_id or state.tp_order_id:
        log.info(
            f"[{trade.symbol}] Recovered protective orders "
            f"SL={state.sl_order_id or '-'} TP={state.tp_order_id or '-'}"
        )


def _fetch_df(adapter, symbol: str) -> pd.DataFrame:
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
        self.last_candle   = 0
        self.open_trade_id = None
        self.sl_order_id   = None
        self.tp_order_id   = None
        self.params        = dict(BASE_PARAMS, context_window_candles=120, max_atr_ratio=2.5)
        self.be_armed      = False


# ---------------------------------------------------------------------------
# Trade lifecycle
# ---------------------------------------------------------------------------

def _open_trade(adapter, session, risk, state, signal, row, params) -> bool:
    previous_risk_params = dict(risk.params)
    risk.params = dict(params)
    plan = risk.plan_trade(state.symbol, signal.side, row["close"], row["atr"])
    risk.params = previous_risk_params

    if not plan.approved:
        log.info(f"[{state.symbol}] Trade rejected by risk engine: {plan.reject_reason}")
        return False

    if plan.qty <= 0:
        log.info(f"[{state.symbol}] Zero qty computed — skipping")
        return False

    try:
        adapter.set_leverage(state.symbol, plan.leverage)
    except Exception as e:
        log.warning(f"[{state.symbol}] set_leverage failed: {e}")

    entry_side = "buy" if signal.side == Side.LONG else "sell"

    try:
        entry = adapter.place_market_order(state.symbol, entry_side, plan.qty)
    except Exception as e:
        log.error(f"[{state.symbol}] Entry order failed: {e}")
        _tg(f"❌ {state.symbol} entry FAILED: {e}")
        return False

    fill_price = entry.price or row["close"]

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
    signal.indicator_snapshot["confidence"] = round(signal.confidence, 3)
    signal.indicator_snapshot["trail_mode"] = TrailingStopManager.mode_for(signal.strategy_name, trade.regime)
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
    msg = tg_templates.opened(
        symbol=state.symbol,
        side=signal.side.value,
        entry=fill_price,
        stop=plan.stop_loss,
        take_profit=plan.take_profit,
        qty=plan.qty,
        leg=signal.strategy_name,
        regime=trade.regime,
        confidence=signal.confidence,
        thesis=signal.reasoning,
    )
    log.info(f"[{state.symbol}] " + msg.replace("\n", " | "))
    _tg(msg)
    return True


def _check_close(adapter, session, risk, state) -> bool:
    trade = session.get(Trade, state.open_trade_id)
    if not trade:
        return True

    live_qty: float | None = None
    try:
        open_positions = adapter.get_open_positions()
        clean_sym = _normalize_position_symbol(state.symbol)
        matched_pos = None
        for p in open_positions:
            if _normalize_position_symbol(p.get("symbol")) == clean_sym:
                matched_pos = p
                break
        still_open = matched_pos is not None
        if matched_pos:
            raw = matched_pos.get("contracts") or matched_pos.get("contractSize")
            if raw is not None:
                live_qty = abs(float(raw))
    except Exception as e:
        log.warning(f"[{state.symbol}] get_open_positions failed: {e}")
        still_open = True

    # Partial-fill reconciliation: TP order filled only part of the position.
    # Update DB qty so force-close uses the right size and dashboard shows correct numbers.
    if still_open and live_qty is not None and live_qty > 0 and trade.qty > 0:
        if live_qty < trade.qty * 0.99:  # >1% discrepancy = partial fill
            log.info(
                f"[{state.symbol}] Partial fill: DB qty={trade.qty:.4f} → "
                f"exchange qty={live_qty:.4f} ({(1 - live_qty / trade.qty) * 100:.1f}% closed by exchange)"
            )
            trade.qty = live_qty
            session.commit()
            _tg(
                f"🔄 {state.symbol} partial TP fill detected\n"
                f"Remaining: {live_qty:.4f} (was {trade.qty:.4f})\n"
                f"DB qty updated — continuing to monitor remainder"
            )

    if still_open:
        try:
            candles = adapter.fetch_ohlcv(state.symbol, "1m", limit=80)
            trail_df = pd.DataFrame([{
                "open": c.open, "high": c.high, "low": c.low,
                "close": c.close, "volume": c.volume, "timestamp": c.timestamp,
            } for c in candles])
            if len(trail_df) >= 30:
                trail_df = add_indicators(
                    trail_df.sort_values("timestamp").reset_index(drop=True),
                    state.params,
                ).dropna()
                trail = TrailingStopManager(adapter, session, _tg).maybe_update(
                    trade=trade,
                    state=state,
                    df=trail_df,
                    params=state.params,
                )
                if trail.moved:
                    state.be_armed = True
                    log.info(
                        f"[{state.symbol}] Trail moved {trail.old_stop:.4f} -> {trail.new_stop:.4f} "
                        f"mode={trail.mode} reason={trail.reason}"
                    )
                    if trail.is_major:
                        _tg(tg_templates.trail(
                            state.symbol,
                            trail.old_stop,
                            trail.new_stop,
                            trail.mode or "trail",
                            trail.reason or "trail update",
                        ))
        except Exception as e:
            log.warning(f"[{state.symbol}] trailing stop check failed: {e}")

        if False and not state.be_armed:
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

        if trade.opened_at:
            opened_at = trade.opened_at
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            hours_open = (datetime.now(timezone.utc) - opened_at).total_seconds() / 3600
            if hours_open >= MAX_TRADE_HOURS:
                log.info(f"[{state.symbol}] Force-closing after {hours_open:.1f}h (max {MAX_TRADE_HOURS}h)")
                _tg(f"⏰ {state.symbol} force-closed after {hours_open:.0f}h")
                try:
                    close_side = "sell" if trade.side == "long" else "buy"
                    close_qty = live_qty if (live_qty is not None and live_qty > 0) else trade.qty
                    adapter.place_market_order(state.symbol, close_side, close_qty)
                    for oid in [state.sl_order_id, state.tp_order_id]:
                        if oid:
                            try:
                                adapter.cancel_order(state.symbol, oid)
                            except Exception:
                                pass
                except Exception as e:
                    log.error(f"[{state.symbol}] Force-close order failed: {e}")
                    return False
                still_open = False

        if still_open:
            return False

    exit_fill = None
    try:
        if hasattr(adapter, "get_exit_fill"):
            exit_fill = adapter.get_exit_fill(
                state.symbol,
                trade.side,
                trade.opened_at,
                trade.qty,
            )
    except Exception as e:
        log.warning(f"[{state.symbol}] Could not fetch exchange exit fill: {e}")

    if exit_fill:
        exit_price = float(exit_fill["price"])
        log.info(
            f"[{state.symbol}] Exit fill resolved from exchange trades: "
            f"price={exit_price:.4f} qty={float(exit_fill.get('qty') or 0):.4f}"
        )
    else:
        try:
            candles = adapter.fetch_ohlcv(state.symbol, "1m", limit=1)
            exit_price = candles[-1].close if candles else trade.entry_price
            log.warning(
                f"[{state.symbol}] Exit fill unavailable; using latest 1m close "
                f"{exit_price:.4f} as fallback"
            )
        except Exception:
            exit_price = trade.entry_price
            log.warning(f"[{state.symbol}] Exit fill and fallback candle unavailable; using entry price")

    direction  = 1 if trade.side == "long" else -1
    raw_pnl    = (exit_price - trade.entry_price) * direction * trade.qty
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

    try:
        save_lesson(trade, session)
        log.info(f"[{state.symbol}] Memory lesson saved")
    except Exception as e:
        log.warning(f"[{state.symbol}] Memory save failed: {e}")

    try:
        update_weights(trade, session)
        log.info(f"[{state.symbol}] Indicator weights updated")
    except Exception as e:
        log.warning(f"[{state.symbol}] Weight update failed: {e}")

    try:
        brain_update = PerCoinBrain(session, state.symbol).update_after_trade(trade)
        if brain_update.changed:
            log.info(f"[{state.symbol}] Per-coin brain updated: {brain_update.reason}")
            _tg(tg_templates.brain_update(
                state.symbol,
                brain_update.version,
                brain_update.reason,
                brain_update.disabled_legs,
            ))
    except Exception as e:
        log.warning(f"[{state.symbol}] Per-coin brain update failed: {e}")

    try:
        from agent.adapt.roster import CoinRoster as _Roster
        _roster = _Roster(session)
        bench_msg = _roster.record_trade(state.symbol, outcome)
        if bench_msg:
            _tg(bench_msg)
    except Exception as e:
        log.warning(f"[{state.symbol}] Roster update failed: {e}")

    msg = tg_templates.closed(
        state.symbol,
        trade.side,
        exit_price,
        raw_pnl,
        outcome,
        exit_reason,
        postmortem,
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

    session = get_session()
    exch_settings = SimpleSettings(
        bankroll_usdt=settings.bankroll_usdt,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        max_daily_drawdown_pct=settings.max_daily_drawdown_pct,
        max_concurrent_positions=settings.max_concurrent_positions,
        default_leverage=settings.default_leverage,
        max_leverage=settings.max_leverage,
    )
    risk   = RiskEngine(exch_settings)
    roster = CoinRoster(session, adapter)
    states: dict[str, SymbolState] = {s: SymbolState(s) for s in roster.get_active()}

    open_trades = session.query(Trade).filter(Trade.closed_at.is_(None)).all()
    for trade in open_trades:
        if trade.symbol not in states:
            states[trade.symbol] = SymbolState(trade.symbol)
        states[trade.symbol].open_trade_id = trade.id
        _recover_protective_order_ids(adapter, states[trade.symbol], trade)
        risk.mark_position_opened(trade.symbol)
        log.info(f"[{trade.symbol}] Recovered open DB trade id={trade.id} on startup")

    # Safety net: the DB is not the source of truth for what's actually live on
    # the exchange (e.g. it can be wiped/rolled back). Cross-check against real
    # exchange positions so we never open a second position on top of one the
    # DB doesn't know about.
    try:
        live_positions = adapter.get_open_positions()
    except Exception as e:
        live_positions = []
        log.warning(f"Startup exchange position check failed: {e}")
    db_open_symbols = {t.symbol for t in open_trades}
    for pos in live_positions:
        sym = pos.get("symbol", "").replace(":USDT", "")
        if not sym.endswith("/USDT") and "/" not in sym:
            sym = sym.replace("USDT", "/USDT")
        if sym in db_open_symbols:
            continue
        if sym not in states:
            states[sym] = SymbolState(sym)
        states[sym].open_trade_id = -1  # sentinel: exchange has a position, DB doesn't — block entries
        risk.mark_position_opened(sym)
        log.error(f"[{sym}] Exchange position with NO matching DB record — blocking new entries until reconciled")
        _tg(f"🚨 {sym} has an open exchange position with no DB record (likely DB reset). Blocking new entries on it — reconcile manually.")

    cycle = 0
    macro = assess_macro(adapter)
    candles_since_trade = 0
    last_daily_review = 0      # UTC hour of last daily review
    last_macro_update = 0      # UTC hour of last macro refresh

    log.info(f"Roster: {roster.get_active()}")
    _tg(f"🤖 Trading bot started\nSymbols: {', '.join(roster.get_active())}\nMacro: {macro.regime}")

    while True:
        cycle += 1
        now_candle = _candle_close_timestamp(TIMEFRAME)
        now_utc = datetime.now(timezone.utc)

        # --- Macro refresh every 4 hours ---
        if now_utc.hour != last_macro_update and now_utc.hour % 4 == 0:
            macro = assess_macro(adapter)
            last_macro_update = now_utc.hour

        # --- Daily roster review at 00:00 UTC ---
        if now_utc.hour == 0 and now_utc.hour != last_daily_review:
            roster.daily_review()
            for sym in roster.get_active():
                if sym not in states:
                    states[sym] = SymbolState(sym)
            for sym in list(states.keys()):
                if sym not in roster.get_active():
                    del states[sym]
            log.info(f"Daily review done. Active: {roster.get_active()}")
            last_daily_review = now_utc.hour

        # Track whether this cycle processes a new candle
        new_candle_this_cycle = False
        signal_summary = []

        for symbol, state in list(states.items()):
            try:
                # Check kill-switch from DB
                from webapi.app_state import get_or_create_state as get_agent_state
                try:
                    agent_state = get_agent_state(session)
                    if agent_state.kill_switch_active:
                        risk.kill_switch_active = True
                except Exception:
                    pass

                # --- Unreconciled exchange position (no DB record) — hold, don't touch ---
                if state.open_trade_id == -1:
                    continue

                # --- Monitor open position ---
                if state.open_trade_id is not None:
                    _check_close(adapter, session, risk, state)
                    continue

                # --- Only act on a new candle close ---
                if now_candle <= state.last_candle:
                    continue

                new_candle_this_cycle = True

                # --- Fetch + prepare data ---
                df = _fetch_df(adapter, symbol)
                if len(df) < 50:
                    log.warning(f"[{symbol}] Not enough candles ({len(df)}), skipping")
                    state.last_candle = now_candle
                    continue

                df = _prepare_df(df, state.params)
                if len(df) < 2:
                    state.last_candle = now_candle
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

                try:
                    disabled_legs = PerCoinBrain(session, symbol).disabled_legs()
                    if signal.strategy_name in disabled_legs:
                        log.info(f"[{symbol}] {signal.strategy_name} disabled by per-coin brain")
                        signal_summary.append(f"{symbol}: {signal.strategy_name} disabled by per-coin brain")
                        state.last_candle = now_candle
                        continue
                except Exception as e:
                    log.warning(f"[{symbol}] Per-coin leg check failed (continuing): {e}")

                if signal.is_actionable and signal.confidence > 0:
                    # --- MTF confluence gate ---
                    if USE_MTF:
                        try:
                            tf_dfs = {"1h": df}
                            raw_1h = _fetch_df(adapter, symbol)
                            for tf in ("4h", "1d"):
                                tf_dfs[tf] = resample_ohlcv(raw_1h, tf)
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
                                log.info(f"[{symbol}] {signal.side.value.upper()} conf={signal.confidence:.2f} → MTF blocked: {mtf['block_reason']}")
                                signal_summary.append(f"{symbol}: {signal.side.value.upper()} blocked by MTF (score={mtf['weighted_score']:.0f})")
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

                    if signal.confidence <= 0:
                        log.info(f"[{symbol}] Memory reduced confidence to zero — skipping")
                        signal_summary.append(f"{symbol}: killed by memory")
                        state.last_candle = now_candle
                        continue

                    # --- Adaptive indicator weights ---
                    try:
                        weight_delta = apply_weights(signal, row, symbol, session)
                        if weight_delta != 0:
                            signal.confidence = max(0.0, min(1.0, signal.confidence + weight_delta))
                            signal.indicator_snapshot["weight_delta"] = round(weight_delta, 2)
                            log.info(f"[{symbol}] Weight delta: {weight_delta:+.2f} → confidence={signal.confidence:.2f}")
                    except Exception as e:
                        log.warning(f"[{symbol}] Weight apply failed (continuing): {e}")

                    # --- Per-coin + macro size adjustment ---
                    trade_params = PerCoinBrain(session, symbol).apply_to_trade_params(state.params)
                    if macro.size_multiplier < 1.0:
                        orig_risk = trade_params.get("max_risk_per_trade_pct", 1.5)
                        trade_params["max_risk_per_trade_pct"] = round(orig_risk * macro.size_multiplier, 3)
                        log.info(f"[{symbol}] Macro size reduced: {orig_risk}% → {trade_params['max_risk_per_trade_pct']}%")

                    log.info(
                        f"[{symbol}] ✅ ENTRY SIGNAL: {signal.side.value.upper()} "
                        f"confidence={signal.confidence:.2f} macro={macro.regime} — {signal.reasoning[0]}"
                    )
                    opened = _open_trade(adapter, session, risk, state, signal, row, trade_params)
                    if opened:
                        candles_since_trade = 0
                        signal_summary.append(f"{symbol}: {signal.side.value.upper()} OPENED")
                    else:
                        signal_summary.append(f"{symbol}: signal passed but risk engine rejected")
                else:
                    reason = signal.reasoning[0] if signal.reasoning else "no signal"
                    log.info(f"[{symbol}] No signal — {reason}")
                    signal_summary.append(f"{symbol}: {reason[:60]}")

                state.last_candle = now_candle

            except Exception as e:
                if "BadSymbol" in type(e).__name__ or "does not have market symbol" in str(e):
                    log.warning(f"[{symbol}] BadSymbol — auto-benching and removing from active roster")
                    roster._bench(symbol, "BadSymbol on exchange")
                    states.pop(symbol, None)
                    _tg(f"🚫 [{symbol}] auto-benched: not available on exchange")
                else:
                    log.error(f"[{symbol}] Unhandled error in main loop: {e}", exc_info=True)
                    _tg(f"⚠️ [{symbol}] Loop error: {e}")

        # --- Self-awareness: candle summary ---
        if new_candle_this_cycle:
            candles_since_trade += 1
            log.info(
                f"📊 Candle summary (idle {candles_since_trade}h) | macro={macro.regime} "
                f"size={macro.size_multiplier:.2f} | {len(signal_summary)} symbols evaluated"
            )
            for s in signal_summary:
                log.info(f"  → {s}")

            # Self-awareness alert: if idle for 24+ hours, log a diagnostic
            if candles_since_trade > 0 and candles_since_trade % 24 == 0:
                idle_days = candles_since_trade / 24
                log.warning(
                    f"🔍 SELF-CHECK: No trades for {idle_days:.0f} day(s). "
                    f"Macro={macro.regime} FG={macro.fear_greed} Funding={macro.funding_rate_pct:+.1f}%"
                )
                _tg(
                    f"🔍 Self-check: no trades for {idle_days:.0f} day(s)\n"
                    f"Macro: {macro.regime} | F&G: {macro.fear_greed} | Funding: {macro.funding_rate_pct:+.1f}%\n"
                    f"Most common block: check journalctl for signal summaries"
                )

        # Heartbeat every 6 cycles (~6 min)
        if cycle % 6 == 0:
            log.info(f"Heartbeat — cycle {cycle}, kill_switch={risk.kill_switch_active}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()
