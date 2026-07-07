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
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from agent.adapt.postmortem import generate_postmortem
from agent.adapt.tuner import tune_parameters, diff_params
from agent.config.settings import settings
from agent.backtest.engine import SimpleSettings
from agent.db.models import Trade, get_session, SignalGateEvent, AgentActivityLog
from agent.exchange.binance_futures import BinanceFuturesAdapter
from agent.exchange.bybit_futures import BybitFuturesAdapter
from agent.fundamental.market_context import add_market_context
from agent.risk.engine import RiskEngine
from agent.strategy.ensemble import generate_signal
from agent.strategy.profiles import get_profile, gated_delta, alignment_report
from agent.strategy.indicators import add_indicators
from agent.strategy.mtf_scorer import compute_confluence, resample_ohlcv, get_ev_calibration
from agent.strategy.signal import Side
from agent.strategy.smc import add_smc
from agent.backtest.validate import BASE_PARAMS
from agent.adapt.memory import save_lesson, apply_memory
from agent.adapt.weights import update_weights, apply_weights
from agent.adapt.roster import CoinRoster, CANDIDATE_SYMBOLS
from agent.fundamental.coin_digest import apply_sentiment_adjustment, build_all_digests, save_digest
from agent.fundamental.macro import assess_macro
from agent.learning.per_coin_brain import PerCoinBrain
from agent.risk.bankroll import BankrollManager
from agent.risk.costs import estimate_round_trip_cost_r
from agent.risk.reentry_guard import evaluate_reentry
from agent.risk.trailing_stop_manager import TrailingStopManager
from agent.telegram import templates as tg_templates

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOLS    = CANDIDATE_SYMBOLS
TIMEFRAME  = "1h"
TIMEFRAME_HOURS = 1.0
CANDLES    = 200
POLL_SEC   = 60
USE_SMC    = True
USE_MTF    = True
BE_TRIGGER_R    = 1.0
MAX_TRADE_HOURS = 48

# Which modules may affect a trade decision this run. Default baseline_simple:
# base signal + MTF + cost/risk gates decide; SMC/news/memory/adaptive observe
# and log but cannot change confidence/EV/sizing or block/approve. Switch via
# STRATEGY_PROFILE=full_agentic to restore the full stack.
ACTIVE_PROFILE = get_profile(settings.strategy_profile)

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


def _trade_params(trade: Trade, state) -> dict:
    try:
        params = trade.get_params_snapshot()
        if params:
            return params
    except Exception:
        pass
    return state.params


def _planned_prices(side: Side, entry_price: float, atr: float, params: dict) -> tuple[float, float]:
    sl_distance = float(atr) * float(params.get("atr_mult_sl", 1.5))
    tp_distance = float(atr) * float(params.get("atr_mult_tp", 3.0))
    if side == Side.LONG:
        return entry_price - sl_distance, entry_price + tp_distance
    return entry_price + sl_distance, entry_price - tp_distance


def _cost_context_r(row, side: Side, params: dict) -> tuple[float, float]:
    entry_price = float(row.get("close") or 0)
    atr = float(row.get("atr") or 0)
    if entry_price <= 0 or atr <= 0:
        return 0.0, float(params.get("min_ev_r", settings.min_live_ev_r))

    stop_loss, take_profit = _planned_prices(side, entry_price, atr, params)
    cost_r = estimate_round_trip_cost_r(
        entry_price,
        stop_loss,
        take_profit,
        taker_fee_pct=settings.taker_fee_pct,
        slippage_pct=settings.slippage_pct,
    )
    min_required = max(
        float(params.get("min_ev_r", settings.min_live_ev_r)),
        cost_r + float(settings.min_edge_after_cost_r),
    )
    return cost_r, min_required


def _cost_edge_metrics(row, side: Side, params: dict, cost_r: float, mtf_ev: float) -> dict:
    """Extra cost/edge facts layered on top of the existing cost-aware floor
    (_cost_context_r) — these only add rejection criteria, never change
    position size. gross_r is the planned reward:risk multiple (fixed by
    atr_mult_tp/atr_mult_sl, independent of the entry price)."""
    atr_mult_sl = float(params.get("atr_mult_sl", 1.5)) or 1.5
    atr_mult_tp = float(params.get("atr_mult_tp", 3.0))
    gross_r = atr_mult_tp / atr_mult_sl if atr_mult_sl > 0 else 0.0
    net_r_after_cost = mtf_ev - cost_r
    cost_pct_of_gross = (cost_r / gross_r * 100) if gross_r > 0 else 0.0

    # cost_r is already expressed as a fraction of 1R (dimensionless); convert
    # to USDT using the risk amount this trade is actually sized to.
    bankroll = float(params.get("bankroll_usdt") or 0)
    risk_pct = float(params.get("max_risk_per_trade_pct") or 0)
    risk_amount_usdt = bankroll * risk_pct / 100 if bankroll > 0 and risk_pct > 0 else None
    round_trip_cost_usdt = cost_r * risk_amount_usdt if risk_amount_usdt is not None else None

    return {
        "gross_r": round(gross_r, 3),
        "net_r_after_estimated_cost": round(net_r_after_cost, 3),
        "cost_as_pct_of_gross_profit": round(cost_pct_of_gross, 2),
        "estimated_round_trip_cost_usdt": round(round_trip_cost_usdt, 4) if round_trip_cost_usdt is not None else None,
        "high_cost_trade": cost_r > settings.max_estimated_cost_r or cost_pct_of_gross >= 20.0,
    }


def _cost_edge_gate(metrics: dict, cost_r: float) -> str | None:
    """Returns a rejection reason string, or None if the trade clears all
    three extra cost/edge gates (reject-only; never adjusts size)."""
    if cost_r > settings.max_estimated_cost_r:
        return f"estimated cost {cost_r:.2f}R exceeds max {settings.max_estimated_cost_r:.2f}R"
    if metrics["net_r_after_estimated_cost"] < settings.min_net_ev_after_cost_r:
        return (
            f"net EV after cost {metrics['net_r_after_estimated_cost']:.2f}R "
            f"below floor {settings.min_net_ev_after_cost_r:.2f}R"
        )
    required_reward = settings.min_expected_reward_cost_multiple * cost_r
    if cost_r > 0 and metrics["gross_r"] < required_reward:
        return (
            f"expected reward {metrics['gross_r']:.2f}R is less than "
            f"{settings.min_expected_reward_cost_multiple:.0f}x estimated cost ({required_reward:.2f}R)"
        )
    return None


def _live_position_snapshot(adapter, symbol: str) -> dict | None:
    clean_sym = _normalize_position_symbol(symbol)
    for pos in adapter.get_open_positions():
        if _normalize_position_symbol(pos.get("symbol")) != clean_sym:
            continue
        qty = abs(float(pos.get("contracts") or 0.0))
        entry = pos.get("entryPrice")
        return {
            "qty": qty,
            "entry_price": float(entry) if entry is not None else None,
        }
    return None


def _reduce_only_market_close(adapter, symbol: str, entry_side: str, qty: float) -> None:
    adapter.close_position_market(symbol, entry_side, qty)


def _candidate_score(signal) -> float:
    """Rank setup quality before spending one of the limited risk slots."""
    snapshot = signal.indicator_snapshot or {}
    ev_r = float(snapshot.get("mtf_ev") or 0.0)
    cost_r = float(snapshot.get("estimated_cost_r") or 0.0)
    min_ev_r = float(snapshot.get("min_required_ev_r") or 0.0)
    edge_after_floor = ev_r - max(cost_r, min_ev_r)
    return round(edge_after_floor + float(signal.confidence or 0.0) * 0.35, 4)


def _profit_r(trade: Trade, price: float) -> float:
    initial_r = abs(float(trade.entry_price) - float(trade.stop_loss or trade.entry_price))
    if initial_r <= 0:
        return 0.0
    direction = 1 if trade.side == "long" else -1
    return ((float(price) - float(trade.entry_price)) * direction) / initial_r


def _locked_r(trade: Trade) -> float:
    initial_r = abs(float(trade.entry_price) - float(trade.stop_loss or trade.entry_price))
    if initial_r <= 0:
        return 0.0
    direction = 1 if trade.side == "long" else -1
    return ((float(trade.stop_loss) - float(trade.entry_price)) * direction) / initial_r


def _trend_runner_eligible(trade: Trade) -> bool:
    strategy = (trade.strategy_name or "").lower()
    regime = (trade.regime or "").lower()
    return (
        "trend" in strategy
        or "momentum" in strategy
        or "kama" in strategy
        or "trending" in regime
        or "high_vol" in regime
    )


def _set_trade_snapshot(trade: Trade, updates: dict) -> None:
    snapshot = trade.get_indicator_snapshot()
    snapshot.update(updates)
    trade.set_indicator_snapshot(snapshot)


def _maybe_activate_trailing_take_profit(adapter, session, state, trade: Trade, df: pd.DataFrame, params: dict) -> bool:
    if state.tp_trailing_active or not state.tp_order_id or not state.sl_order_id or df.empty:
        return False
    if not bool(params.get("enable_trailing_take_profit", True)):
        return False
    if not _trend_runner_eligible(trade):
        return False

    current_price = float(df.iloc[-1]["close"])
    profit_r = _profit_r(trade, current_price)
    activation_r = float(params.get("tp_trail_activation_r", 1.6))
    if profit_r < activation_r:
        return False

    locked_r = _locked_r(trade)
    min_locked_r = float(params.get("tp_trail_min_locked_r", 0.5))
    if locked_r < min_locked_r:
        return False

    entry_snapshot = trade.get_indicator_snapshot()
    entry_ev = float(entry_snapshot.get("mtf_ev") or 0)
    min_ev = float(params.get("tp_trail_min_ev_r", 0.35))
    if entry_ev and entry_ev < min_ev:
        return False

    try:
        adapter.cancel_order(trade.symbol, state.tp_order_id)
    except Exception as e:
        log.warning(f"[{trade.symbol}] TP runner activation failed; could not cancel fixed TP: {e}")
        return False

    state.tp_order_id = None
    state.tp_trailing_active = True
    _set_trade_snapshot(trade, {
        "tp_trailing_active": True,
        "tp_trailing_activated_at": datetime.now(timezone.utc).isoformat(),
        "tp_trailing_activation_r": round(profit_r, 2),
        "tp_trailing_locked_r": round(locked_r, 2),
    })
    session.commit()

    msg = (
        f"🏁 TP RUNNER | {trade.symbol}\n"
        f"Fixed TP cancelled; trailing SL is managing the exit.\n"
        f"Current: +{profit_r:.2f}R | Locked: +{locked_r:.2f}R\n"
        f"Why: trend setup reached runner threshold."
    )
    log.info(f"[{trade.symbol}] " + msg.replace("\n", " | "))
    _tg(msg)
    return True


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

    try:
        snapshot = trade.get_indicator_snapshot()
        if snapshot.get("tp_trailing_active") and not state.tp_order_id:
            state.tp_trailing_active = True
            log.info(f"[{trade.symbol}] Recovered TP runner state")
    except Exception:
        pass


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
        self.params        = dict(
            BASE_PARAMS,
            context_window_candles=120,
            max_atr_ratio=2.5,
            min_ev_r=settings.min_live_ev_r,
        )
        self.be_armed      = False
        self.tp_trailing_active = False


@dataclass
class EntryCandidate:
    symbol: str
    state: SymbolState
    signal: object
    row: pd.Series
    params: dict
    score: float


# ---------------------------------------------------------------------------
# Daily risk-state persistence — the drawdown counter and auto kill-switch are
# in-memory, so without these a restart (i.e. every deploy) resets them.
# ---------------------------------------------------------------------------

def _restore_risk_day_state(session, risk):
    try:
        from webapi.app_state import get_or_create_state
        st = get_or_create_state(session)
        risk.restore_day_state({
            "daily_date": st.risk_day,
            "daily_loss_usdt": st.daily_loss_usdt,
            "daily_net_pnl_usdt": st.daily_net_pnl_usdt,
            "auto_kill_active": st.auto_kill_active,
        })
        if risk.kill_switch_active:
            log.warning("Restored daily risk state — drawdown kill switch is still active for today")
        elif st.risk_day:
            log.info(f"Restored daily risk state for {st.risk_day}: net {st.daily_net_pnl_usdt or 0:+.2f} USDT")
    except Exception as e:
        log.warning(f"Could not restore daily risk state: {e}")


def _persist_risk_day_state(session, risk):
    try:
        from webapi.app_state import get_or_create_state
        st = get_or_create_state(session)
        day = risk.export_day_state()
        st.risk_day = day["daily_date"]
        st.daily_loss_usdt = day["daily_loss_usdt"]
        st.daily_net_pnl_usdt = day["daily_net_pnl_usdt"]
        st.auto_kill_active = day["auto_kill_active"]
        session.commit()
    except Exception as e:
        log.warning(f"Could not persist daily risk state: {e}")


# ---------------------------------------------------------------------------
# Decision-log persistence (observability only — never influences trading).
# Mirrors the per-cycle `signal_summary` lines into agent_activity_log, and
# every gate rejection into signal_gate_events, so the API/dashboard can show
# which gate is rejecting the most trades.
# ---------------------------------------------------------------------------

# Rolling retention: activity log is high-volume chat, gate events feed a
# 30-day stats window so they're kept longer.
_ACTIVITY_MAX_ROWS = 5000
_ACTIVITY_MAX_DAYS = 7
_GATE_MAX_DAYS = 30
_GATE_MAX_ROWS = 50000


def _flush_decision_log(session, cycle: int, activity_events: list[dict], gate_events: list[dict]):
    """Batch-write this cycle's notes. Best-effort: a failure here must never
    disturb the trading loop, so we swallow and roll back on any error."""
    if not activity_events and not gate_events:
        return
    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        for ev in activity_events:
            session.add(AgentActivityLog(
                cycle=cycle,
                symbol=ev.get("symbol"),
                level=ev.get("level") or "info",
                message=ev.get("message") or "",
                created_at=ts,
            ))
        for ev in gate_events:
            session.add(SignalGateEvent(
                symbol=ev.get("symbol") or "?",
                gate=ev.get("gate") or "unknown",
                reason=ev.get("reason"),
                side=ev.get("side"),
                confidence=ev.get("confidence"),
                created_at=ts,
            ))
        session.commit()
    except Exception as e:
        log.warning(f"Could not persist decision log: {e}")
        try:
            session.rollback()
        except Exception:
            pass


def _prune_decision_log(session):
    """Keep the observability tables bounded. Cheap enough to run periodically
    (called every N cycles, not every cycle)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        # --- agent_activity_log: last 7 days, then cap to newest 5000 rows ---
        session.query(AgentActivityLog).filter(
            AgentActivityLog.created_at < now - timedelta(days=_ACTIVITY_MAX_DAYS)
        ).delete(synchronize_session=False)
        cutoff = (
            session.query(AgentActivityLog.id)
            .order_by(AgentActivityLog.id.desc())
            .offset(_ACTIVITY_MAX_ROWS)
            .first()
        )
        if cutoff:
            session.query(AgentActivityLog).filter(
                AgentActivityLog.id <= cutoff[0]
            ).delete(synchronize_session=False)

        # --- signal_gate_events: last 30 days (feeds the 30d stats window) ---
        session.query(SignalGateEvent).filter(
            SignalGateEvent.created_at < now - timedelta(days=_GATE_MAX_DAYS)
        ).delete(synchronize_session=False)
        cutoff_g = (
            session.query(SignalGateEvent.id)
            .order_by(SignalGateEvent.id.desc())
            .offset(_GATE_MAX_ROWS)
            .first()
        )
        if cutoff_g:
            session.query(SignalGateEvent).filter(
                SignalGateEvent.id <= cutoff_g[0]
            ).delete(synchronize_session=False)
        session.commit()
    except Exception as e:
        log.warning(f"Could not prune decision log: {e}")
        try:
            session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Trade lifecycle
# ---------------------------------------------------------------------------

def _open_trade(adapter, session, risk, state, signal, row, params) -> bool:
    previous_risk_params = dict(risk.params)
    risk.params = dict(params)
    plan = risk.plan_trade(
        state.symbol, signal.side, row["close"], row["atr"],
        confidence=float(signal.confidence or 0) or None,
    )
    risk.params = previous_risk_params

    if not plan.approved:
        log.info(f"[{state.symbol}] Trade rejected by risk engine: {plan.reject_reason}")
        return False

    if plan.qty <= 0:
        log.info(f"[{state.symbol}] Zero qty computed — skipping")
        return False

    requested_risk_pct = float(params.get("max_risk_per_trade_pct", plan.risk_pct) or plan.risk_pct)
    if plan.risk_pct < requested_risk_pct:
        log.info(
            f"[{state.symbol}] Risk downsized by portfolio caps: "
            f"{requested_risk_pct:.2f}% -> {plan.risk_pct:.2f}%"
        )

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

    fill_price = float(entry.price or row["close"])
    actual_qty = float(plan.qty)
    try:
        live = _live_position_snapshot(adapter, state.symbol)
        if live:
            if live.get("entry_price"):
                fill_price = float(live["entry_price"])
            if live.get("qty"):
                actual_qty = float(live["qty"])
    except Exception as e:
        log.warning(f"[{state.symbol}] Could not confirm live fill from exchange: {e}")

    if not _same_price(fill_price, plan.entry_price, tolerance=0.0005):
        old_sl, old_tp = plan.stop_loss, plan.take_profit
        plan.entry_price = fill_price
        plan.stop_loss, plan.take_profit = _planned_prices(
            signal.side,
            fill_price,
            float(row["atr"]),
            params,
        )
        log.info(
            f"[{state.symbol}] Repriced SL/TP from actual fill {fill_price:.4f}: "
            f"SL {old_sl:.4f}->{plan.stop_loss:.4f}, TP {old_tp:.4f}->{plan.take_profit:.4f}"
        )

    try:
        sl_order = adapter.place_stop_loss(state.symbol, entry_side, actual_qty, plan.stop_loss)
        state.sl_order_id = sl_order.order_id
    except Exception as e:
        log.error(f"[{state.symbol}] Stop-loss order failed: {e}")
        _tg(f"⚠️ {state.symbol} SL order FAILED; emergency-closing entry: {e}")
        try:
            _reduce_only_market_close(adapter, state.symbol, entry_side, actual_qty)
            log.error(f"[{state.symbol}] Emergency close sent after SL placement failure")
        except Exception as close_error:
            state.open_trade_id = -1
            log.critical(f"[{state.symbol}] Emergency close FAILED after SL failure: {close_error}")
            _tg(f"🚨 {state.symbol} emergency close FAILED after SL failure: {close_error}")
        return False

    try:
        tp_order = adapter.place_take_profit(state.symbol, entry_side, actual_qty, plan.take_profit)
        state.tp_order_id = tp_order.order_id
    except Exception as e:
        log.warning(f"[{state.symbol}] Take-profit order failed: {e}")

    actual_risk_amount = abs(float(fill_price) - float(plan.stop_loss)) * float(actual_qty)
    bankroll = float(params.get("bankroll_usdt") or settings.bankroll_usdt or 0.0)
    actual_risk_pct = (actual_risk_amount / bankroll * 100) if bankroll > 0 else plan.risk_pct

    trade = Trade(
        symbol=state.symbol,
        side=signal.side.value,
        strategy_name=signal.strategy_name,
        regime=str(signal.indicator_snapshot.get("regime", "unknown")),
        entry_price=fill_price,
        qty=actual_qty,
        original_qty=actual_qty,
        stop_loss=plan.stop_loss,
        take_profit=plan.take_profit,
        leverage=plan.leverage,
    )
    signal.indicator_snapshot["confidence"] = round(signal.confidence, 3)
    signal.indicator_snapshot["trail_mode"] = TrailingStopManager.mode_for(signal.strategy_name, trade.regime)
    signal.indicator_snapshot["estimated_cost_r"] = round(
        estimate_round_trip_cost_r(
            fill_price,
            plan.stop_loss,
            plan.take_profit,
            taker_fee_pct=settings.taker_fee_pct,
            slippage_pct=settings.slippage_pct,
        ),
        3,
    )
    signal.indicator_snapshot["planned_risk_pct"] = round(plan.risk_pct, 4)
    signal.indicator_snapshot["planned_risk_usdt"] = round(plan.risk_amount_usdt, 4)
    signal.indicator_snapshot["actual_risk_pct"] = round(actual_risk_pct, 4)
    signal.indicator_snapshot["actual_risk_usdt"] = round(actual_risk_amount, 4)
    signal.indicator_snapshot["actual_qty"] = round(actual_qty, 8)
    trade.set_entry_reasoning(signal.reasoning)
    trade.set_indicator_snapshot(signal.indicator_snapshot)
    trade.set_params_snapshot(params)
    session.add(trade)
    session.commit()

    state.open_trade_id = trade.id
    state.tp_trailing_active = False
    risk.mark_position_opened(
        state.symbol,
        side=signal.side.value,
        risk_pct=actual_risk_pct,
        risk_amount_usdt=actual_risk_amount,
    )

    msg = tg_templates.opened(trade, session)
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
        trade_params = _trade_params(trade, state)
        try:
            candles = adapter.fetch_ohlcv(state.symbol, "1m", limit=80)
            trail_df = pd.DataFrame([{
                "open": c.open, "high": c.high, "low": c.low,
                "close": c.close, "volume": c.volume, "timestamp": c.timestamp,
            } for c in candles])
            if len(trail_df) >= 30:
                trail_df = add_indicators(
                    trail_df.sort_values("timestamp").reset_index(drop=True),
                    trade_params,
                ).dropna()
                trail = TrailingStopManager(adapter, session, _tg).maybe_update(
                    trade=trade,
                    state=state,
                    df=trail_df,
                    params=trade_params,
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
                _maybe_activate_trailing_take_profit(adapter, session, state, trade, trail_df, trade_params)
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
                    entry_side = "buy" if trade.side == "long" else "sell"
                    close_qty = live_qty if (live_qty is not None and live_qty > 0) else trade.qty
                    adapter.close_position_market(state.symbol, entry_side, close_qty)
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

    # Use the FULL original position size for PnL, not trade.qty — that field
    # gets overwritten to the remaining size on a partial-fill reconciliation
    # (see above), and multiplying the final exit price by only the remainder
    # silently drops the profit/loss already realized on the filled portion.
    full_qty = float(trade.original_qty or trade.qty)

    exit_fill = None
    try:
        if hasattr(adapter, "get_exit_fill"):
            exit_fill = adapter.get_exit_fill(
                state.symbol,
                trade.side,
                trade.opened_at,
                full_qty,
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
    raw_pnl    = (exit_price - trade.entry_price) * direction * full_qty
    if raw_pnl > 0 and state.tp_trailing_active:
        exit_reason = "trailing_take_profit"
    else:
        exit_reason = "take_profit" if raw_pnl > 0 else "stop_loss"
    outcome     = "win" if raw_pnl > 0 else ("loss" if raw_pnl < 0 else "breakeven")

    trade.exit_price  = exit_price
    trade.pnl_usdt    = raw_pnl
    trade.outcome     = outcome
    trade.exit_reason = exit_reason
    trade.closed_at   = datetime.now(timezone.utc)

    postmortem = generate_postmortem(trade, session)
    trade.set_postmortem(postmortem)
    session.commit()

    was_killed = risk.kill_switch_active
    risk.record_trade_result(raw_pnl)
    _persist_risk_day_state(session, risk)
    if risk.kill_switch_active and not was_killed:
        _tg(
            f"🛑 Daily drawdown limit hit — no new entries for the rest of the day "
            f"(net {risk.export_day_state()['daily_net_pnl_usdt']:+.2f} USDT today)."
        )
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

    msg = tg_templates.closed(trade, session)
    log.info(f"[{state.symbol}] " + msg.replace("\n", " | "))
    _tg(msg)

    state.open_trade_id = None
    state.sl_order_id   = None
    state.tp_order_id   = None
    state.be_armed      = False
    state.tp_trailing_active = False
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
        max_portfolio_risk_pct=settings.max_portfolio_risk_pct,
        max_same_direction_risk_pct=settings.max_same_direction_risk_pct,
        min_entry_risk_pct=settings.min_entry_risk_pct,
        min_stop_cost_multiple=settings.min_stop_cost_multiple,
        taker_fee_pct=settings.taker_fee_pct,
        slippage_pct=settings.slippage_pct,
        default_leverage=settings.default_leverage,
        max_leverage=settings.max_leverage,
        daily_drawdown_mode=settings.daily_drawdown_mode,
        confidence_risk_scaling=settings.confidence_risk_scaling,
        confidence_full_risk_at=settings.confidence_full_risk_at,
    )
    risk   = RiskEngine(exch_settings)
    _restore_risk_day_state(session, risk)
    bankroll_manager = BankrollManager(settings)
    risk_profile = bankroll_manager.sync(session, adapter)
    risk.set_bankroll(risk_profile.effective_bankroll_usdt)
    log.info(
        f"Risk profile: bankroll={risk_profile.effective_bankroll_usdt:.2f} "
        f"risk={risk_profile.risk_pct:.2f}% tier={risk_profile.tier} "
        f"mode={risk_profile.mode} reason={risk_profile.reason}"
    )
    roster = CoinRoster(session, adapter)
    states: dict[str, SymbolState] = {s: SymbolState(s) for s in roster.get_active()}

    open_trades = session.query(Trade).filter(Trade.closed_at.is_(None)).all()
    for trade in open_trades:
        if trade.symbol not in states:
            states[trade.symbol] = SymbolState(trade.symbol)
        states[trade.symbol].open_trade_id = trade.id
        _recover_protective_order_ids(adapter, states[trade.symbol], trade)
        params = trade.get_params_snapshot()
        snapshot = trade.get_indicator_snapshot()
        risk.mark_position_opened(
            trade.symbol,
            side=trade.side,
            risk_pct=float(snapshot.get("actual_risk_pct") or params.get("max_risk_per_trade_pct") or snapshot.get("planned_risk_pct") or settings.max_risk_per_trade_pct),
            risk_amount_usdt=float(snapshot.get("actual_risk_usdt") or snapshot.get("planned_risk_usdt") or 0.0),
        )
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
        risk.mark_position_opened(sym, risk_pct=settings.max_risk_per_trade_pct)
        log.error(f"[{sym}] Exchange position with NO matching DB record — blocking new entries until reconciled")
        _tg(f"🚨 {sym} has an open exchange position with no DB record (likely DB reset). Blocking new entries on it — reconcile manually.")

    cycle = 0
    macro = assess_macro(adapter)
    candles_since_trade = 0
    last_daily_review = 0      # UTC hour of last daily review
    last_macro_update = 0      # UTC hour of last macro refresh
    last_bankroll_sync = time.time()
    last_coin_digest_date = ""  # UTC date string of last coin-digest run
    digest_utc_hour = (settings.coin_digest_hour_ph - 8) % 24

    log.info(f"Roster: {roster.get_active()}")
    _tg(f"🤖 Trading bot started\nSymbols: {', '.join(roster.get_active())}\nMacro: {macro.regime}")

    while True:
        cycle += 1
        now_candle = _candle_close_timestamp(TIMEFRAME)
        now_utc = datetime.now(timezone.utc)

        if time.time() - last_bankroll_sync >= settings.bankroll_sync_interval_sec:
            try:
                risk_profile = bankroll_manager.sync(session, adapter)
                risk.set_bankroll(risk_profile.effective_bankroll_usdt)
                last_bankroll_sync = time.time()
                log.info(
                    f"Risk profile: bankroll={risk_profile.effective_bankroll_usdt:.2f} "
                    f"risk={risk_profile.risk_pct:.2f}% tier={risk_profile.tier} "
                    f"drawdown={risk_profile.drawdown_pct:.2f}%"
                )
            except Exception as e:
                log.warning(f"Bankroll/risk sync failed: {e}")

        # --- Macro refresh every 4 hours ---
        if now_utc.hour != last_macro_update and now_utc.hour % 4 == 0:
            macro = assess_macro(adapter)
            last_macro_update = now_utc.hour

        # --- Dynamic market scan refresh (own cadence via MARKET_SCAN_REFRESH_MINUTES,
        # this call is a cheap no-op if the cache isn't stale yet). Keeps the
        # candidate pool warm between daily reviews and the API status fresh.
        try:
            roster.refresh_market_scan()
        except Exception as e:
            log.warning(f"Market scan refresh failed (continuing on fixed roster): {e}")

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

        # --- Daily coin digest: price action + agent's read + news sentiment ---
        today_str = now_utc.strftime("%Y-%m-%d")
        if now_utc.hour == digest_utc_hour and last_coin_digest_date != today_str:
            try:
                digests = build_all_digests(roster.get_active(), adapter)
                for result in digests:
                    save_digest(session, result)
                if digests:
                    _tg(tg_templates.coin_digest_report(digests))
                log.info(f"Coin digest built for {len(digests)} symbol(s)")
            except Exception as e:
                log.warning(f"Coin digest run failed: {e}")
            last_coin_digest_date = today_str

        # Track whether this cycle processes a new candle
        new_candle_this_cycle = False
        opened_this_cycle = False
        signal_summary = []
        activity_events: list[dict] = []   # -> agent_activity_log
        gate_events: list[dict] = []       # -> signal_gate_events (rejections)
        entry_candidates: list[EntryCandidate] = []

        # Single sink for per-cycle decision notes: preserves the existing
        # `signal_summary` log lines verbatim AND captures structured rows for
        # the observability tables. Pure logging — no control-flow effect.
        def record(symbol, message, *, gate=None, level=None, side=None, confidence=None):
            signal_summary.append(f"{symbol}: {message}")
            if level is None:
                level = "block" if (gate and gate != "no_signal") else "info"
            activity_events.append({"symbol": symbol, "message": message, "level": level})
            if gate:
                gate_events.append({
                    "symbol": symbol, "gate": gate, "reason": message,
                    "side": side, "confidence": confidence,
                })

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

                # --- Generate signal (profile gates SMC inside) ---
                signal = generate_signal(row, prev, state.params, profile=ACTIVE_PROFILE)

                # --- Coin-brain auto-disable — decision-active only when the
                #     profile allows adaptive modules; otherwise observe-only. ---
                try:
                    disabled_legs = PerCoinBrain(session, symbol).disabled_legs()
                    if signal.strategy_name in disabled_legs:
                        if ACTIVE_PROFILE.adaptive_active:
                            log.info(f"[{symbol}] {signal.strategy_name} disabled by per-coin brain")
                            record(symbol, f"{signal.strategy_name} disabled by per-coin brain",
                                   gate="leg_disabled", side=signal.side.value, confidence=signal.confidence)
                            state.last_candle = now_candle
                            continue
                        else:
                            log.info(f"[{symbol}] [observed] coin-brain would disable {signal.strategy_name} "
                                     f"(not applied under profile {ACTIVE_PROFILE.name})")
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
                                calibration=get_ev_calibration(session),
                            )
                            signal.indicator_snapshot["mtf_score"]     = round(mtf["weighted_score"], 1)
                            signal.indicator_snapshot["mtf_bias"]      = mtf["overall_bias"]
                            signal.indicator_snapshot["mtf_ev"]        = round(mtf.get("ev") or 0, 2)
                            signal.indicator_snapshot["mtf_confluence"] = round(mtf["confluence_pct"], 1)

                            if not mtf["approved"]:
                                log.info(f"[{symbol}] {signal.side.value.upper()} conf={signal.confidence:.2f} → MTF blocked: {mtf['block_reason']}")
                                record(symbol, f"{signal.side.value.upper()} blocked by MTF (score={mtf['weighted_score']:.0f})",
                                       gate="mtf", side=signal.side.value, confidence=signal.confidence)
                                state.last_candle = now_candle
                                continue

                            log.info(
                                f"[{symbol}] MTF score={mtf['weighted_score']:.1f} "
                                f"bias={mtf['overall_bias']} EV={mtf.get('ev', 0):.2f}R ✓"
                            )
                        except Exception as e:
                            log.warning(f"[{symbol}] MTF scorer failed (continuing): {e}")

                    # Running confidence audit trail (seeded by the ensemble).
                    breakdown = signal.indicator_snapshot.setdefault("confidence_breakdown", {"profile": ACTIVE_PROFILE.name})

                    # --- Double-counting diagnostic (observe-only, never gates) ---
                    try:
                        align = alignment_report(row, signal.side.value, signal.indicator_snapshot.get("mtf_bias"))
                        signal.indicator_snapshot["alignment"] = align
                        if align["redundancy_flag"]:
                            log.info(
                                f"[{symbol}] ⚠ redundancy: {align['aligned_count']}/5 signals aligned but "
                                f"~{align['independent_signals_est']} independent — 'confluence' may be the trend counted twice"
                            )
                    except Exception as e:
                        log.warning(f"[{symbol}] alignment diagnostic failed (continuing): {e}")

                    # --- Memory check — observe-only unless profile.memory_active ---
                    try:
                        mem_delta, mem_notes = apply_memory(symbol, signal, row, session)
                        gated_delta(signal, mem_delta, ACTIVE_PROFILE.memory_active, "memory", breakdown)
                        if mem_delta != 0:
                            signal.indicator_snapshot["memory_delta"] = round(mem_delta, 2)
                            tag = "" if ACTIVE_PROFILE.memory_active else "[observed] "
                            for note in mem_notes:
                                signal.reasoning.append(f"{tag}{note}")
                                if ACTIVE_PROFILE.memory_active or ACTIVE_PROFILE.memory_verbose:
                                    log.info(f"[{symbol}] {tag}{note}")
                    except Exception as e:
                        log.warning(f"[{symbol}] Memory check failed (continuing): {e}")

                    if signal.confidence <= 0:
                        log.info(f"[{symbol}] Memory reduced confidence to zero — skipping")
                        record(symbol, "killed by memory", gate="memory", side=signal.side.value, confidence=signal.confidence)
                        state.last_candle = now_candle
                        continue

                    # --- Adaptive indicator weights — observe-only unless adaptive_active ---
                    try:
                        weight_delta = apply_weights(signal, row, symbol, session)
                        gated_delta(signal, weight_delta, ACTIVE_PROFILE.adaptive_active, "adaptive_weights", breakdown)
                        if weight_delta != 0:
                            signal.indicator_snapshot["weight_delta"] = round(weight_delta, 2)
                            if ACTIVE_PROFILE.adaptive_active or ACTIVE_PROFILE.memory_verbose:
                                tag = "" if ACTIVE_PROFILE.adaptive_active else "[observed] "
                                log.info(f"[{symbol}] {tag}Weight delta: {weight_delta:+.2f} → confidence={signal.confidence:.2f}")
                    except Exception as e:
                        log.warning(f"[{symbol}] Weight apply failed (continuing): {e}")

                    # --- News sentiment (FA) — observe-only unless news_active ---
                    try:
                        fa_delta = apply_sentiment_adjustment(symbol, signal, session)
                        gated_delta(signal, fa_delta, ACTIVE_PROFILE.news_active, "news", breakdown)
                        if fa_delta != 0:
                            signal.indicator_snapshot["fa_delta"] = round(fa_delta, 2)
                    except Exception as e:
                        log.warning(f"[{symbol}] Sentiment apply failed (continuing): {e}")

                    # Finalize the confidence audit trail.
                    breakdown["final_confidence"] = round(signal.confidence, 4)
                    breakdown["decision_active"] = ACTIVE_PROFILE.decision_active_modules
                    breakdown["observe_only"] = ACTIVE_PROFILE.observe_only_modules

                    # --- Per-coin + macro size adjustment — coin-brain param
                    #     tuning is adaptive, so gate it by profile too. ---
                    if ACTIVE_PROFILE.adaptive_active:
                        trade_params = PerCoinBrain(session, symbol).apply_to_trade_params(state.params)
                    else:
                        trade_params = dict(state.params)
                    if macro.size_multiplier < 1.0:
                        orig_risk = trade_params.get("max_risk_per_trade_pct", 1.5)
                        trade_params["max_risk_per_trade_pct"] = round(orig_risk * macro.size_multiplier, 3)
                        log.info(f"[{symbol}] Macro size reduced: {orig_risk}% → {trade_params['max_risk_per_trade_pct']}%")

                    log.info(
                        f"[{symbol}] ✅ ENTRY SIGNAL: {signal.side.value.upper()} "
                        f"confidence={signal.confidence:.2f} macro={macro.regime} — {signal.reasoning[0]}"
                    )
                    tier_cap = float(risk_profile.risk_pct)
                    requested_risk = float(trade_params.get("max_risk_per_trade_pct", settings.max_risk_per_trade_pct))
                    slot_cap = tier_cap
                    if settings.split_risk_across_slots:
                        slot_cap = tier_cap / max(1, int(settings.max_concurrent_positions))
                    portfolio_cap = float(settings.max_portfolio_risk_pct or 0.0) or tier_cap
                    same_direction_cap = float(settings.max_same_direction_risk_pct or 0.0) or portfolio_cap
                    trade_params["max_risk_per_trade_pct"] = round(min(requested_risk, slot_cap), 4)
                    trade_params["max_portfolio_risk_pct"] = round(portfolio_cap, 4)
                    trade_params["max_same_direction_risk_pct"] = round(same_direction_cap, 4)
                    trade_params["min_entry_risk_pct"] = settings.min_entry_risk_pct
                    trade_params["min_stop_cost_multiple"] = settings.min_stop_cost_multiple
                    trade_params["reentry_max_trades_per_symbol_per_day"] = settings.reentry_max_trades_per_symbol_per_day
                    trade_params["reentry_min_ev_multiplier"] = settings.reentry_min_ev_multiplier
                    trade_params["bankroll_usdt"] = risk_profile.effective_bankroll_usdt
                    signal.indicator_snapshot["risk_tier"] = risk_profile.tier
                    signal.indicator_snapshot["risk_pct"] = trade_params["max_risk_per_trade_pct"]
                    signal.indicator_snapshot["portfolio_risk_cap_pct"] = trade_params["max_portfolio_risk_pct"]
                    signal.indicator_snapshot["same_direction_risk_cap_pct"] = trade_params["max_same_direction_risk_pct"]
                    signal.indicator_snapshot["effective_bankroll_usdt"] = round(risk_profile.effective_bankroll_usdt, 2)
                    if trade_params["max_risk_per_trade_pct"] < requested_risk:
                        log.info(
                            f"[{symbol}] Risk slot capped size: {requested_risk:.2f}% -> "
                            f"{trade_params['max_risk_per_trade_pct']:.2f}% "
                            f"({risk_profile.tier}, {settings.max_concurrent_positions} slots)"
                        )

                    entry_candle_ts = int(row.get("timestamp") or now_candle)
                    signal.indicator_snapshot["entry_candle_timestamp"] = entry_candle_ts
                    signal.indicator_snapshot["entry_candle_time_utc"] = datetime.fromtimestamp(
                        entry_candle_ts / 1000,
                        tz=timezone.utc,
                    ).isoformat()
                    signal.indicator_snapshot["entry_candle_close"] = round(float(row.get("close") or 0), 8)
                    signal.indicator_snapshot["entry_cycle_time_utc"] = now_utc.isoformat()

                    cost_r, min_required_ev = _cost_context_r(row, signal.side, trade_params)
                    signal.indicator_snapshot["estimated_cost_r"] = round(cost_r, 3)
                    signal.indicator_snapshot["min_required_ev_r"] = round(min_required_ev, 3)
                    if "mtf_ev" in signal.indicator_snapshot:
                        mtf_ev = float(signal.indicator_snapshot.get("mtf_ev") or 0)
                        if mtf_ev < min_required_ev:
                            reason = (
                                f"EV {mtf_ev:.2f}R below cost-aware floor {min_required_ev:.2f}R "
                                f"(estimated costs {cost_r:.2f}R)"
                            )
                            log.info(f"[{symbol}] {reason} - skipping")
                            record(symbol, reason, gate="cost_edge", side=signal.side.value, confidence=signal.confidence)
                            state.last_candle = now_candle
                            continue

                        # Extra cost/edge gates: reject-only, never adjusts size.
                        # Catches trades that barely cleared the floor above but
                        # still net a thin/fee-eaten result (the "$3-5 win"
                        # pattern) — requires more reward relative to cost, not
                        # just more EV relative to the minimum floor.
                        cost_metrics = _cost_edge_metrics(row, signal.side, trade_params, cost_r, mtf_ev)
                        signal.indicator_snapshot.update(cost_metrics)
                        gate_reason = _cost_edge_gate(cost_metrics, cost_r)
                        if gate_reason:
                            log.info(f"[{symbol}] Cost/edge gate: {gate_reason} - skipping")
                            record(symbol, f"cost/edge gate ({gate_reason})",
                                   gate="cost_edge", side=signal.side.value, confidence=signal.confidence)
                            state.last_candle = now_candle
                            continue

                    reentry = evaluate_reentry(
                        session,
                        symbol,
                        signal,
                        trade_params,
                        now=now_utc,
                        timeframe_hours=TIMEFRAME_HOURS,
                    )
                    if not reentry.allowed:
                        log.info(f"[{symbol}] Re-entry blocked: {reentry.reason}")
                        record(symbol, f"re-entry blocked ({reentry.reason})",
                               gate="reentry", side=signal.side.value, confidence=signal.confidence)
                        state.last_candle = now_candle
                        continue

                    score = _candidate_score(signal)
                    signal.indicator_snapshot["candidate_score"] = score
                    entry_candidates.append(EntryCandidate(symbol, state, signal, row, trade_params, score))
                    record(
                        symbol,
                        f"candidate {signal.side.value.upper()} "
                        f"score={score:.2f} EV={float(signal.indicator_snapshot.get('mtf_ev') or 0):.2f}R",
                        level="candidate",
                    )
                else:
                    reason = signal.reasoning[0] if signal.reasoning else "no signal"
                    log.info(f"[{symbol}] No signal — {reason}")
                    record(symbol, reason[:60], gate="no_signal", level="info",
                           side=signal.side.value, confidence=signal.confidence)

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

        # --- Ranked admission: best setups get the limited risk slots first ---
        if entry_candidates:
            entry_candidates.sort(key=lambda c: c.score, reverse=True)
            ranked = ", ".join(f"{c.symbol}:{c.score:.2f}" for c in entry_candidates[:5])
            log.info(f"Ranked entry candidates: {ranked}")
            for candidate in entry_candidates:
                if candidate.state.open_trade_id is not None:
                    continue
                opened = _open_trade(
                    adapter,
                    session,
                    risk,
                    candidate.state,
                    candidate.signal,
                    candidate.row,
                    candidate.params,
                )
                if opened:
                    opened_this_cycle = True
                    record(
                        candidate.symbol,
                        f"{candidate.signal.side.value.upper()} OPENED (ranked score={candidate.score:.2f})",
                        level="open",
                    )
                else:
                    record(
                        candidate.symbol,
                        "ranked candidate rejected by risk/admission caps",
                        gate="risk_cap", side=candidate.signal.side.value,
                        confidence=candidate.signal.confidence,
                    )

        # --- Self-awareness: candle summary ---
        if new_candle_this_cycle:
            if opened_this_cycle:
                candles_since_trade = 0
            else:
                candles_since_trade += 1
            open_position_count = sum(1 for st in states.values() if st.open_trade_id is not None)
            log.info(
                f"📊 Candle summary (no_new_entries {candles_since_trade}h, open={open_position_count}) "
                f"| macro={macro.regime} size={macro.size_multiplier:.2f} "
                f"| {len(signal_summary)} notes"
            )
            for s in signal_summary:
                log.info(f"  → {s}")

            # Self-awareness alert: if idle for 24+ hours, log a diagnostic
            if candles_since_trade > 0 and candles_since_trade % 24 == 0:
                idle_days = candles_since_trade / 24
                log.warning(
                    f"🔍 SELF-CHECK: No new entries for {idle_days:.0f} day(s). "
                    f"Macro={macro.regime} FG={macro.fear_greed} Funding={macro.funding_rate_pct:+.1f}%"
                )
                _tg(
                    f"🔍 Self-check: no new entries for {idle_days:.0f} day(s)\n"
                    f"Open positions: {open_position_count}\n"
                    f"Macro: {macro.regime} | F&G: {macro.fear_greed} | Funding: {macro.funding_rate_pct:+.1f}%\n"
                    f"Most common block: check journalctl for signal summaries"
                )

        # --- Persist this cycle's decision notes (observability only) ---
        _flush_decision_log(session, cycle, activity_events, gate_events)
        if cycle % 30 == 0:
            _prune_decision_log(session)

        # Heartbeat every 6 cycles (~6 min)
        if cycle % 6 == 0:
            log.info(f"Heartbeat — cycle {cycle}, kill_switch={risk.kill_switch_active}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()
