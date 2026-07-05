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

    def get_account_equity(self, asset: str = "USDT") -> float:
        return self.get_balance(asset)

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> None:
        ...

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, qty: float) -> OrderResult:
        ...

    def close_position_market(self, symbol: str, entry_side: str, qty: float) -> OrderResult:
        """Reduce-only market close of an existing position.

        Default falls back to a plain market order; exchange adapters should
        override with a reduceOnly order so a qty mismatch can never flip into
        a new position in the opposite direction.
        """
        close_side = "sell" if entry_side == "buy" else "buy"
        return self.place_market_order(symbol, close_side, qty)

    @abstractmethod
    def place_stop_loss(self, symbol: str, side: str, qty: float, stop_price: float) -> OrderResult:
        ...

    @abstractmethod
    def place_take_profit(self, symbol: str, side: str, qty: float, target_price: float) -> OrderResult:
        ...

    @abstractmethod
    def get_open_positions(self) -> list[dict]:
        ...

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> None:
        ...

    def fetch_all_tickers(self) -> dict:
        """One cheap call returning {symbol: ticker} for every market on the
        exchange — used by the dynamic market scanner's stage 1 (volume/
        spread/momentum filtering) instead of per-symbol OHLCV calls. Default
        raises; adapters that support it (Binance) override this."""
        raise NotImplementedError("fetch_all_tickers not supported by this adapter")
