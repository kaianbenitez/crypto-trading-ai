import ccxt
from datetime import datetime, timezone

from agent.config.settings import settings
from agent.exchange.base import ExchangeAdapter, OHLCV, OrderResult


class BinanceFuturesAdapter(ExchangeAdapter):
    def __init__(self):
        self._client = ccxt.binanceusdm({
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "options": {"fetchCurrencies": False},
            "enableRateLimit": True,
            "timeout": 15000,
        })
        if settings.binance_testnet:
            base_url = "https://testnet.binancefuture.com"
            self._client.urls["api"].update({
                "fapiPublic": f"{base_url}/fapi/v1",
                "fapiPublicV2": f"{base_url}/fapi/v2",
                "fapiPublicV3": f"{base_url}/fapi/v3",
                "fapiPrivate": f"{base_url}/fapi/v1",
                "fapiPrivateV2": f"{base_url}/fapi/v2",
                "fapiPrivateV3": f"{base_url}/fapi/v3",
                "fapiData": f"{base_url}/futures/data",
            })

    def _raw_symbol(self, symbol: str) -> str:
        try:
            return self._client.market_id(symbol)
        except Exception:
            return symbol.split(":", 1)[0].replace("/", "").upper()

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> list[OHLCV]:
        raw = self._client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [OHLCV(timestamp=r[0], open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5]) for r in raw]

    def get_balance(self, asset: str = "USDT") -> float:
        bal = self._client.fetch_balance()
        return float(bal.get(asset, {}).get("free", 0.0))

    def get_account_equity(self, asset: str = "USDT") -> float:
        bal = self._client.fetch_balance()
        asset_row = bal.get(asset, {}) or {}
        value = asset_row.get("total")
        if value is None:
            value = asset_row.get("free")
        if value is None:
            info = bal.get("info") or {}
            for key in ("totalWalletBalance", "totalMarginBalance"):
                if info.get(key) is not None:
                    value = info[key]
                    break
        return float(value or 0.0)

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

    def close_position_market(self, symbol: str, entry_side: str, qty: float) -> OrderResult:
        close_side = "sell" if entry_side == "buy" else "buy"
        order = self._client.create_order(symbol, "market", close_side, qty, params={"reduceOnly": True})
        return OrderResult(
            order_id=str(order["id"]),
            symbol=symbol,
            side=close_side,
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

    def fetch_open_algo_orders(self, symbol: str) -> list[dict]:
        return self._client.fapiPrivateGetOpenAlgoOrders({"symbol": self._raw_symbol(symbol)})

    def cancel_order(self, symbol: str, order_id: str) -> None:
        try:
            self._client.cancel_order(order_id, symbol)
            return
        except Exception as standard_error:
            try:
                self._client.fapiPrivateDeleteAlgoOrder({
                    "symbol": self._raw_symbol(symbol),
                    "algoId": str(order_id),
                })
                return
            except Exception:
                raise standard_error

    def fetch_order(self, symbol: str, order_id: str) -> dict:
        try:
            return self._client.fetch_order(order_id, symbol)
        except Exception:
            return self._client.fapiPrivateGetAlgoOrder({
                "symbol": self._raw_symbol(symbol),
                "algoId": str(order_id),
            })

    def fetch_my_trades(self, symbol: str, since_ms: int | None = None, limit: int = 50) -> list[dict]:
        return self._client.fetch_my_trades(symbol, since=since_ms, limit=limit)

    def get_exit_fill(
        self,
        symbol: str,
        trade_side: str,
        opened_at: datetime | None,
        expected_qty: float,
    ) -> dict | None:
        """Return average exit fill from account trades after the entry.

        The orchestrator can notice an exchange-side SL/TP after the position is
        already gone. In that case, using the current candle close understates or
        overstates the real result. Binance account trades are the closest source
        of truth for actual fill price.
        """
        if opened_at is None:
            return None

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        since_ms = int(opened_at.timestamp() * 1000) - 60_000
        exit_side = "sell" if trade_side == "long" else "buy"

        fills = []
        for fill in self.fetch_my_trades(symbol, since_ms=since_ms, limit=100):
            if str(fill.get("side", "")).lower() != exit_side:
                continue
            amount = float(fill.get("amount") or 0)
            price = float(fill.get("price") or 0)
            if amount <= 0 or price <= 0:
                continue
            fills.append(fill)

        if not fills:
            return None

        qty = 0.0
        notional = 0.0
        order_ids = []
        for fill in fills:
            amount = float(fill.get("amount") or 0)
            price = float(fill.get("price") or 0)
            qty += amount
            notional += amount * price
            if fill.get("order"):
                order_ids.append(str(fill["order"]))
            if expected_qty > 0 and qty >= expected_qty * 0.98:
                break

        if qty <= 0:
            return None

        return {
            "price": notional / qty,
            "qty": qty,
            "order_ids": order_ids,
            "fills": fills,
        }
