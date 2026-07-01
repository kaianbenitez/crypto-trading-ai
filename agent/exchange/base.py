from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OHLCV:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    status: str


class ExchangeAdapter(ABC):
    """Common interface so Binance/Bybit/etc are interchangeable."""

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[OHLCV]:
        ...

    @abstractmethod
    def get_balance(self, asset: str = "USDT") -> float:
        ...

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> None:
        ...

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, qty: float) -> OrderResult:
        ...

    @abstractmethod
    def place_stop_loss(self, symbol: str, side: str, qty: float, stop_price: float) -> OrderResult:
        ...

    @abstractmethod
    def place_take_profit(self, symbol: str, side: str, qty: float, target_price: float) -> OrderResult:
        ...

    @abstractmethod
    def get_open_positions(self) -> list[dict]:
        ...
