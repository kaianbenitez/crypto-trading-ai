from dataclasses import dataclass
from datetime import date, datetime, timezone

from agent.strategy.signal import Side


@dataclass
class OpenRisk:
    side: str
    risk_pct: float
    risk_amount_usdt: float


@dataclass
class TradePlan:
    side: Side
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    leverage: int
    risk_amount_usdt: float
    risk_pct: float = 0.0
    reject_reason: str | None = None

    @property
    def approved(self) -> bool:
        return self.reject_reason is None


class RiskEngine:
    """Position sizing, SL/TP, and account-protection guardrails.

    Conservative by design for thin accounts: caps risk per trade as a % of
    bankroll, enforces a daily drawdown kill-switch, and limits concurrent
    positions / correlated exposure.
    """

    def __init__(self, settings, params: dict | None = None):
        self.settings = settings
        self.params = params or {}
        self.bankroll_usdt = float(settings.bankroll_usdt)
        self._daily_loss_usdt = 0.0    # gross losses only (legacy mode)
        self._daily_net_pnl_usdt = 0.0  # wins offset losses (default mode)
        self._daily_date: date | None = None
        self._open_positions: dict[str, OpenRisk] = {}
        self.kill_switch_active = False

    def set_bankroll(self, bankroll_usdt: float):
        if bankroll_usdt > 0:
            self.bankroll_usdt = float(bankroll_usdt)

    def current_bankroll(self) -> float:
        return float(self.bankroll_usdt or self.settings.bankroll_usdt)

    def _roll_day(self):
        today = datetime.now(timezone.utc).date()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_loss_usdt = 0.0
            self._daily_net_pnl_usdt = 0.0
            self.kill_switch_active = False

    def _daily_drawdown_usdt(self) -> float:
        """Today's drawdown per the configured mode: net (wins offset losses,
        the standard definition) or losses_only (gross losses, stricter)."""
        mode = str(getattr(self.settings, "daily_drawdown_mode", "net") or "net").lower()
        if mode == "losses_only":
            return self._daily_loss_usdt
        return max(0.0, -self._daily_net_pnl_usdt)

    def record_trade_result(self, pnl_usdt: float):
        self._roll_day()
        self._daily_net_pnl_usdt += pnl_usdt
        if pnl_usdt < 0:
            self._daily_loss_usdt += abs(pnl_usdt)
        max_dd = self.current_bankroll() * (self.settings.max_daily_drawdown_pct / 100)
        if self._daily_drawdown_usdt() >= max_dd:
            self.kill_switch_active = True

    # -- Day-state persistence: the daily loss counter and auto kill-switch --
    # -- live in memory, so without these hooks every service restart      --
    # -- (i.e. every deploy) silently resets the daily drawdown protection. --

    def export_day_state(self) -> dict:
        return {
            "daily_date": self._daily_date.isoformat() if self._daily_date else None,
            "daily_loss_usdt": self._daily_loss_usdt,
            "daily_net_pnl_usdt": self._daily_net_pnl_usdt,
            "auto_kill_active": self.kill_switch_active,
        }

    def restore_day_state(self, state: dict | None):
        if not state:
            return
        stored_date = state.get("daily_date")
        if not stored_date:
            return
        try:
            parsed = date.fromisoformat(str(stored_date))
        except ValueError:
            return
        if parsed != datetime.now(timezone.utc).date():
            return  # stale — a fresh day starts clean anyway
        self._daily_date = parsed
        self._daily_loss_usdt = float(state.get("daily_loss_usdt") or 0.0)
        self._daily_net_pnl_usdt = float(state.get("daily_net_pnl_usdt") or 0.0)
        if bool(state.get("auto_kill_active")):
            self.kill_switch_active = True

    def mark_position_opened(
        self,
        symbol: str,
        side: str | Side | None = None,
        risk_pct: float | None = None,
        risk_amount_usdt: float | None = None,
    ):
        side_value = side.value if isinstance(side, Side) else str(side or "unknown")
        amount = float(risk_amount_usdt or 0.0)
        pct = float(risk_pct or 0.0)
        if pct <= 0 and amount > 0:
            pct = amount / max(self.current_bankroll(), 1e-9) * 100
        if pct <= 0:
            pct = float(getattr(self.settings, "max_risk_per_trade_pct", 0.0) or 0.0)
        self._open_positions[symbol] = OpenRisk(side_value.lower(), pct, amount)

    def mark_position_closed(self, symbol: str):
        self._open_positions.pop(symbol, None)

    def open_position_count(self) -> int:
        return len(self._open_positions)

    def open_risk_pct(self) -> float:
        return sum(max(0.0, pos.risk_pct) for pos in self._open_positions.values())

    def same_direction_risk_pct(self, side: Side) -> float:
        side_value = side.value.lower()
        return sum(
            max(0.0, pos.risk_pct)
            for pos in self._open_positions.values()
            if pos.side == side_value
        )

    def check_breakeven(
        self,
        side: Side,
        entry_price: float,
        current_price: float,
        atr: float,
        be_trigger_r: float = 1.0,
        atr_mult_sl: float = 1.5,
        initial_stop: float | None = None,
    ) -> float | None:
        """Returns the new SL price if BE should be armed, else None.

        BE arms when unrealised profit >= be_trigger_r × initial risk (1R default).
        New SL is set to entry_price + small buffer to lock in breakeven.
        Pass initial_stop (the actual entry-time stop) so 1R reflects the risk
        actually taken, not a reconstruction from current ATR — volatility may
        have shifted since entry.
        """
        if initial_stop is not None and initial_stop > 0:
            sl_distance = abs(entry_price - initial_stop)
        else:
            sl_distance = atr * atr_mult_sl
        if sl_distance <= 0:
            return None
        buffer = atr * 0.1  # tiny buffer above/below entry to avoid premature fill
        if side == Side.LONG:
            profit = current_price - entry_price
            if profit >= sl_distance * be_trigger_r:
                return entry_price + buffer
        else:
            profit = entry_price - current_price
            if profit >= sl_distance * be_trigger_r:
                return entry_price - buffer
        return None

    def plan_trade(
        self,
        symbol: str,
        side: Side,
        entry_price: float,
        atr: float,
        confidence: float | None = None,
    ) -> TradePlan:
        self._roll_day()

        if self.kill_switch_active:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Daily drawdown kill-switch active")

        if symbol in self._open_positions:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Symbol already has an open position")

        if len(self._open_positions) >= self.settings.max_concurrent_positions:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Max concurrent positions reached")

        bankroll = float(self.params.get("bankroll_usdt", self.current_bankroll()))
        risk_pct = self.params.get("max_risk_per_trade_pct", self.settings.max_risk_per_trade_pct)
        risk_pct = float(risk_pct or 0.0)

        portfolio_cap = float(self.params.get(
            "max_portfolio_risk_pct",
            getattr(self.settings, "max_portfolio_risk_pct", 0.0),
        ) or 0.0)
        same_direction_cap = float(self.params.get(
            "max_same_direction_risk_pct",
            getattr(self.settings, "max_same_direction_risk_pct", 0.0),
        ) or 0.0)
        if same_direction_cap <= 0 and portfolio_cap > 0:
            same_direction_cap = portfolio_cap
        min_entry_risk_pct = float(self.params.get(
            "min_entry_risk_pct",
            getattr(self.settings, "min_entry_risk_pct", 0.0),
        ) or 0.0)

        if portfolio_cap > 0:
            remaining = portfolio_cap - self.open_risk_pct()
            if remaining <= 0:
                return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                                  reject_reason=f"Portfolio risk cap reached ({self.open_risk_pct():.2f}% >= {portfolio_cap:.2f}%)")
            risk_pct = min(risk_pct, remaining)

        if same_direction_cap > 0:
            remaining = same_direction_cap - self.same_direction_risk_pct(side)
            if remaining <= 0:
                return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                                  reject_reason=f"Same-direction risk cap reached ({self.same_direction_risk_pct(side):.2f}% >= {same_direction_cap:.2f}%)")
            risk_pct = min(risk_pct, remaining)

        if risk_pct <= 0 or (min_entry_risk_pct > 0 and risk_pct < min_entry_risk_pct):
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason=f"Remaining risk budget too small ({risk_pct:.2f}% < {min_entry_risk_pct:.2f}%)")

        # Confidence-scaled sizing: low-conviction signals risk less. Scale-down
        # only (never above the tier risk), floored at min_entry_risk_pct so an
        # otherwise-approved trade isn't rejected purely for being low-confidence.
        if (
            confidence is not None
            and bool(getattr(self.settings, "confidence_risk_scaling", False))
        ):
            full_at = float(getattr(self.settings, "confidence_full_risk_at", 0.6) or 0.6)
            if full_at > 0 and confidence < full_at:
                scaled = risk_pct * max(0.0, float(confidence)) / full_at
                risk_pct = max(scaled, min_entry_risk_pct) if min_entry_risk_pct > 0 else scaled

        risk_amount = bankroll * (risk_pct / 100)

        atr_mult_sl = self.params.get("atr_mult_sl", 1.5)
        atr_mult_tp = self.params.get("atr_mult_tp", 3.0)  # default 2:1 reward:risk

        if atr <= 0:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Invalid ATR, cannot size stop-loss")

        sl_distance = atr * atr_mult_sl
        tp_distance = atr * atr_mult_tp

        fee_pct = float(getattr(self.settings, "taker_fee_pct", 0.0) or 0.0)
        slippage_pct = float(getattr(self.settings, "slippage_pct", 0.0) or 0.0)
        min_cost_multiple = float(self.params.get(
            "min_stop_cost_multiple",
            getattr(self.settings, "min_stop_cost_multiple", 0.0),
        ) or 0.0)
        if min_cost_multiple > 0 and entry_price > 0:
            per_side_cost = (fee_pct + slippage_pct) / 100
            round_trip_unit_cost = entry_price * per_side_cost * 2
            if round_trip_unit_cost > 0 and sl_distance < round_trip_unit_cost * min_cost_multiple:
                return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                                  reject_reason="Stop distance too tight versus estimated fees/slippage")

        if side == Side.LONG:
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

        # qty such that loss at stop-loss == risk_amount (before leverage scales notional, not loss)
        qty = risk_amount / sl_distance if sl_distance > 0 else 0
        leverage = min(self.params.get("leverage", self.settings.default_leverage), self.settings.max_leverage)

        notional = qty * entry_price
        if notional > bankroll * leverage:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Position notional exceeds available leverage capacity")

        return TradePlan(
            side=side, qty=qty, entry_price=entry_price,
            stop_loss=stop_loss, take_profit=take_profit,
            leverage=leverage, risk_amount_usdt=risk_amount, risk_pct=risk_pct,
        )
