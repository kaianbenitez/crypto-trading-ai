"""Exchange-side trailing stop manager.

The manager only moves stops in the profitable direction. It computes the next
stop from the trade leg/regime, replaces the exchange order, records the event,
and returns a concise human-readable update for Telegram/logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from agent.db.models import Trade


@dataclass
class TrailResult:
    moved: bool
    order_id: str | None = None
    old_stop: float | None = None
    new_stop: float | None = None
    mode: str | None = None
    reason: str | None = None
    is_major: bool = False


class TrailingStopManager:
    def __init__(self, adapter, session: "Session", tg_fn=None):
        self.adapter = adapter
        self.session = session
        self.tg_fn = tg_fn

    @staticmethod
    def mode_for(strategy_name: str, regime: str) -> str:
        strategy = (strategy_name or "").lower()
        regime = (regime or "").upper()
        if regime == "HIGH_VOL":
            return "chandelier"
        if "mean" in strategy or "reversion" in strategy:
            return "step"
        if "trend" in strategy or "momentum" in strategy or "kama" in strategy:
            return "atr"
        return "structure"

    @staticmethod
    def _initial_r(trade: "Trade") -> float:
        return abs(float(trade.entry_price) - float(trade.stop_loss or trade.entry_price))

    @staticmethod
    def _profit_r(trade: "Trade", price: float) -> float:
        initial_r = TrailingStopManager._initial_r(trade)
        if initial_r <= 0:
            return 0.0
        direction = 1 if trade.side == "long" else -1
        return ((price - trade.entry_price) * direction) / initial_r

    @staticmethod
    def _profitable_only(trade: "Trade", old_stop: float, candidate: float) -> float | None:
        if trade.side == "long" and candidate > old_stop:
            return candidate
        if trade.side == "short" and candidate < old_stop:
            return candidate
        return None

    def _candidate(
        self,
        trade: "Trade",
        df: pd.DataFrame,
        params: dict,
        current_price: float,
    ) -> tuple[float | None, str, str, bool]:
        mode = self.mode_for(trade.strategy_name, trade.regime)
        initial_r = self._initial_r(trade)
        profit_r = self._profit_r(trade, current_price)
        activation = float(params.get("trail_activation_r", 1.0))
        if initial_r <= 0 or profit_r < activation:
            return None, mode, f"waiting for +{activation:.1f}R activation", False

        atr = float(df.iloc[-1].get("atr") or 0)
        if atr <= 0:
            return None, mode, "ATR unavailable", False

        old_stop = float(trade.stop_loss)
        is_major = False

        if mode == "step":
            if profit_r >= 1.5:
                lock_r = 1.0
                is_major = True
            elif profit_r >= 1.0:
                lock_r = 0.5
                is_major = True
            elif profit_r >= 0.5:
                lock_r = 0.0
                is_major = True
            else:
                return None, mode, "step trail not armed yet", False
            candidate = trade.entry_price + initial_r * lock_r if trade.side == "long" else trade.entry_price - initial_r * lock_r
            return candidate, mode, f"step lock at +{lock_r:.1f}R after trade reached +{profit_r:.2f}R", is_major

        if mode == "chandelier":
            lookback = int(params.get("trail_chandelier_lookback", 22))
            atr_mult = float(params.get("trail_chandelier_atr_mult", 3.0))
            window = df.tail(max(lookback, 2))
            if trade.side == "long":
                candidate = float(window["high"].max()) - atr * atr_mult
            else:
                candidate = float(window["low"].min()) + atr * atr_mult
            return candidate, mode, f"high-vol chandelier {atr_mult:.1f}x ATR after +{profit_r:.2f}R", profit_r >= 1.0

        if mode == "atr":
            atr_mult = float(params.get("trail_atr_mult", 2.2))
            candidate = current_price - atr * atr_mult if trade.side == "long" else current_price + atr * atr_mult
            return candidate, mode, f"ATR trail {atr_mult:.1f}x after +{profit_r:.2f}R", profit_r >= 1.0

        # Structure mode: approximate confirmed swing using closed candles only.
        lookback = int(params.get("trail_structure_lookback", 5))
        closed = df.iloc[:-1].tail(max(lookback, 2))
        if len(closed) < 2:
            return None, mode, "not enough closed structure candles", False
        if trade.side == "long":
            candidate = float(closed["low"].min())
            reason = f"structure trail to confirmed swing low after +{profit_r:.2f}R"
        else:
            candidate = float(closed["high"].max())
            reason = f"structure trail to confirmed swing high after +{profit_r:.2f}R"
        return candidate, mode, reason, profit_r >= 1.0

    def maybe_update(
        self,
        trade: "Trade",
        state,
        df: pd.DataFrame,
        params: dict,
    ) -> TrailResult:
        if not state.sl_order_id or df.empty:
            return TrailResult(False, reason="no active SL order to replace")

        current_price = float(df.iloc[-1]["close"])
        old_stop = float(trade.stop_loss)
        candidate, mode, reason, is_major = self._candidate(trade, df, params, current_price)
        if candidate is None:
            return TrailResult(False, mode=mode, reason=reason)

        new_stop = self._profitable_only(trade, old_stop, float(candidate))
        if new_stop is None:
            return TrailResult(False, mode=mode, reason="candidate would loosen stop")

        # Avoid tiny churn that spams exchange/API for no practical protection.
        if abs(new_stop - old_stop) / max(abs(old_stop), 1e-9) < float(params.get("trail_min_move_pct", 0.0005)):
            return TrailResult(False, mode=mode, reason="candidate move too small")

        entry_side = "buy" if trade.side == "long" else "sell"
        try:
            self.adapter.cancel_order(trade.symbol, state.sl_order_id)
        except Exception:
            pass
        order = self.adapter.place_stop_loss(trade.symbol, entry_side, trade.qty, new_stop)
        state.sl_order_id = order.order_id
        trade.stop_loss = new_stop

        from agent.db.models import TrailingStopEvent
        self.session.add(TrailingStopEvent(
            trade_id=trade.id,
            symbol=trade.symbol,
            old_stop=old_stop,
            new_stop=new_stop,
            mode=mode,
            reason=reason,
            exchange_order_id=order.order_id,
            is_major=is_major,
        ))
        self.session.commit()

        return TrailResult(
            True,
            order_id=order.order_id,
            old_stop=old_stop,
            new_stop=new_stop,
            mode=mode,
            reason=reason,
            is_major=is_major,
        )
