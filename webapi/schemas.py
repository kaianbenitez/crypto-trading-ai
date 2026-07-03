from pydantic import BaseModel
from datetime import datetime


class LoginRequest(BaseModel):
    password: str


class TradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    strategy_name: str
    regime: str
    entry_price: float
    exit_price: float | None
    qty: float
    stop_loss: float
    take_profit: float
    leverage: int
    entry_reasoning: list[str]
    indicator_snapshot: dict
    pnl_usdt: float | None
    outcome: str | None
    exit_reason: str | None
    postmortem: list[str]
    opened_at: datetime
    closed_at: datetime | None

    class Config:
        from_attributes = True


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str | None = None


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float


class SummaryOut(BaseModel):
    total_trades: int
    win_rate_pct: float
    roi_pct: float
    open_positions: int
    kill_switch_active: bool
    bankroll_usdt: float


class LivePositionOut(BaseModel):
    symbol: str
    mark_price: float | None = None
    unrealized_pnl: float | None = None
    roi_pct: float | None = None
    break_even_price: float | None = None


class AgentStatusOut(BaseModel):
    trading_agent: str
    webapi: str
    dashboard: str
    nginx: str
    exchange: str
    testnet: bool
    symbols: list[str]
    bankroll_usdt: float
    checked_at: str
