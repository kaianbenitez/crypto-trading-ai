import ccxt

from agent.config.settings import settings
from agent.exchange.base import ExchangeAdapter, OHLCV, OrderResult


class BinanceFuturesAdapter(ExchangeAdapter):
    def __init__(self):
        self._client = ccxt.binance({
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
            "timeout": 15000,
        })
        if settings.binance_testnet:
            self._client.set_sandbox_mode(True)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[OHLCV]:
        raw = self._client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [OHLCV(timestamp=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in raw]

    def get_balance(self, asset: str = "USDT") -> float:
        bal = self._client.fetch_balance()
        return float(bal.get(asset, {}).get("free", 0.0))

    def set_leverage(self, symbol: str, leverage: int) -> None:
        leverage = max(1, min(leverage, settings.max_leverage))
        self._client.set_leverage(leverage, symbol)

    def place_market_order(self, symbol: str, side: str, qty: float) -> OrderResult:
        order = self._client.create_order(symbol, "market", side, qty)
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            side=side,
            qty=qty,
            price=float(order.get("average") or order.get("price") or 0.0),
            status=order.get("status", "unknown"),
        )

    def place_stop_loss(self, symbol: str, side: str, qty: float, stop_price: float) -> OrderResult:
        close_side = "sell" if side == "buy" else "buy"
        order = self._client.create_order(
            symbol, "STOP_MARKET", close_side, qty,
            params={"stopPrice": stop_price, "reduceOnly": True},
        )
        return OrderResult(
            order_id=str(order["id"]), symbol=symbol, side=close_side,
            qty=qty, price=stop_price, status=order.get("status", "unknown"),
        )

    def place_take_profit(self, symbol: str, side: str, qty: float, target_price: float) -> OrderResult:
        close_side = "sell" if side == "buy" else "buy"
        order = self._client.create_order(
            symbol, "TAKE_PROFIT_MARKET", close_side, qty,
            params={"stopPrice": target_price, "reduceOnly": True},
        )
        return OrderResult(
            order_id=str(order["id"]), symbol=symbol, side=close_side,
            qty=qty, price=target_price, status=order.get("status", "unknown"),
        )

    def get_open_positions(self) -> list[dict]:
        positions = self._client.fetch_positions()
        return [p for p in positions if float(p.get("contracts") or 0) != 0]

    def cancel_order(self, symbol: str, order_id: str) -> None:
        self._client.cancel_order(order_id, symbol)
