from dataclasses import dataclass
from datetime import date

from agent.strategy.signal import Side


@dataclass
class TradePlan:
    side: Side
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    leverage: int
    risk_amount_usdt: float
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
        self._daily_loss_usdt = 0.0
        self._daily_date: date | None = None
        self._open_symbols: set[str] = set()
        self.kill_switch_active = False

    def _roll_day(self):
        today = date.today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_loss_usdt = 0.0
            self.kill_switch_active = False

    def record_trade_result(self, pnl_usdt: float):
        self._roll_day()
        if pnl_usdt < 0:
            self._daily_loss_usdt += abs(pnl_usdt)
        max_dd = self.settings.bankroll_usdt * (self.settings.max_daily_drawdown_pct / 100)
        if self._daily_loss_usdt >= max_dd:
            self.kill_switch_active = True

    def mark_position_opened(self, symbol: str):
        self._open_symbols.add(symbol)

    def mark_position_closed(self, symbol: str):
        self._open_symbols.discard(symbol)

    def check_breakeven(
        self,
        side: Side,
        entry_price: float,
        current_price: float,
        atr: float,
        be_trigger_r: float = 1.0,
        atr_mult_sl: float = 1.5,
    ) -> float | None:
        """Returns the new SL price if BE should be armed, else None.

        BE arms when unrealised profit >= be_trigger_r × initial risk (1R default).
        New SL is set to entry_price + small buffer to lock in breakeven.
        """
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

    def plan_trade(self, symbol: str, side: Side, entry_price: float, atr: float) -> TradePlan:
        self._roll_day()

        if self.kill_switch_active:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Daily drawdown kill-switch active")

        if len(self._open_symbols) >= self.settings.max_concurrent_positions and symbol not in self._open_symbols:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Max concurrent positions reached")

        risk_pct = self.params.get("max_risk_per_trade_pct", self.settings.max_risk_per_trade_pct)
        risk_amount = self.settings.bankroll_usdt * (risk_pct / 100)

        atr_mult_sl = self.params.get("atr_mult_sl", 1.5)
        atr_mult_tp = self.params.get("atr_mult_tp", 3.0)  # default 2:1 reward:risk

        if atr <= 0:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Invalid ATR, cannot size stop-loss")

        sl_distance = atr * atr_mult_sl
        tp_distance = atr * atr_mult_tp

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
        if notional > self.settings.bankroll_usdt * leverage:
            return TradePlan(side, 0, entry_price, 0, 0, 0, 0,
                              reject_reason="Position notional exceeds available leverage capacity")

        return TradePlan(
            side=side, qty=qty, entry_price=entry_price,
            stop_loss=stop_loss, take_profit=take_profit,
            leverage=leverage, risk_amount_usdt=risk_amount,
        )
