"""Serializable candlestick payloads for frontend chart panels."""
from __future__ import annotations


def build_candlestick_payload(symbol: str, candles, trade=None, trail_events=None) -> dict:
    payload = {
        "symbol": symbol,
        "candles": [
            {
                "time": int(c.timestamp / 1000),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
        "overlays": {},
    }
    if trade:
        payload["overlays"].update({
            "entry": trade.entry_price,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "side": trade.side,
            "regime": trade.regime,
            "strategy": trade.strategy_name,
        })
    if trail_events:
        payload["overlays"]["trail"] = [
            {"time": e.created_at.isoformat(), "price": e.new_stop, "mode": e.mode}
            for e in trail_events
        ]
    return payload
