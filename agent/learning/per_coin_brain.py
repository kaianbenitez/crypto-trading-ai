"""Per-coin adaptive learning state.

This is intentionally simple and auditable: every symbol owns its own brain
record, stats are updated only from that symbol's closed trades, and parameter
changes are bounded plus logged for rollback.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from agent.db.models import Trade

DEFAULT_PARAMS = {
    "size_mult": 1.0,
    "sl_atr_mult": 1.5,
    "tp_atr_mult": 3.0,
    "trail_atr_mult": 2.2,
    "trail_activation_r": 1.0,
}

BOUNDS = {
    "size_mult": (0.5, 1.5),
    "sl_atr_mult": (1.0, 3.5),
    "tp_atr_mult": (1.5, 5.0),
    "trail_atr_mult": (1.5, 3.5),
    "trail_activation_r": (0.5, 1.5),
}

MIN_TRADES_FOR_ADJUST = 8
DISABLE_AFTER_TRADES = 30


@dataclass
class BrainUpdate:
    symbol: str
    version: int
    params: dict
    changed: bool
    reason: str
    disabled_legs: list[str]


def _clamp(key: str, value: float) -> float:
    lo, hi = BOUNDS[key]
    return max(lo, min(hi, value))


def _safe_json(value: str | None, default):
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _r_multiple(trade: "Trade") -> float:
    if not trade.entry_price or not trade.stop_loss:
        return 0.0
    initial_r = abs(trade.entry_price - trade.stop_loss)
    if initial_r <= 0:
        return 0.0
    direction = 1 if trade.side == "long" else -1
    exit_price = trade.exit_price or trade.entry_price
    return ((exit_price - trade.entry_price) * direction) / initial_r


def _stats(trades: list["Trade"]) -> dict:
    if not trades:
        return {"count": 0, "win_rate": 0.0, "avg_r": 0.0, "sharpe": 0.0, "expectancy": 0.0}
    rs = [_r_multiple(t) for t in trades]
    wins = [r for r in rs if r > 0]
    avg = sum(rs) / len(rs)
    if len(rs) > 1:
        mean = avg
        variance = sum((r - mean) ** 2 for r in rs) / (len(rs) - 1)
        stdev = math.sqrt(max(variance, 0.0))
        sharpe = (mean / stdev) * math.sqrt(len(rs)) if stdev > 0 else 0.0
    else:
        sharpe = 0.0
    return {
        "count": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_r": avg,
        "sharpe": sharpe,
        "expectancy": avg,
    }


class PerCoinBrain:
    def __init__(self, session: "Session", symbol: str):
        self.session = session
        self.symbol = symbol

    def _record(self):
        from agent.db.models import PerCoinBrainState
        record = (
            self.session.query(PerCoinBrainState)
            .filter(PerCoinBrainState.symbol == self.symbol)
            .first()
        )
        if record:
            return record
        record = PerCoinBrainState(
            symbol=self.symbol,
            params=json.dumps(DEFAULT_PARAMS),
            leg_stats=json.dumps({}),
            regime_stats=json.dumps({}),
            disabled_legs=json.dumps([]),
            version=1,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def params(self) -> dict:
        record = self._record()
        params = dict(DEFAULT_PARAMS)
        params.update(_safe_json(record.params, {}))
        return params

    def disabled_legs(self) -> list[str]:
        return _safe_json(self._record().disabled_legs, [])

    def apply_to_trade_params(self, params: dict) -> dict:
        """Return bot strategy/risk params adjusted for this symbol."""
        brain = self.params()
        adjusted = dict(params)
        adjusted["atr_mult_sl"] = brain["sl_atr_mult"]
        adjusted["atr_mult_tp"] = brain["tp_atr_mult"]
        adjusted["max_risk_per_trade_pct"] = round(
            adjusted.get("max_risk_per_trade_pct", 1.0) * brain["size_mult"], 4
        )
        adjusted["trail_atr_mult"] = brain["trail_atr_mult"]
        adjusted["trail_activation_r"] = brain["trail_activation_r"]
        return adjusted

    def update_after_trade(self, trade: "Trade") -> BrainUpdate:
        from agent.db.models import ParamChangeLog, Trade

        record = self._record()
        params = self.params()
        old_params = dict(params)

        recent = (
            self.session.query(Trade)
            .filter(Trade.symbol == self.symbol, Trade.closed_at.isnot(None))
            .order_by(Trade.closed_at.desc())
            .limit(100)
            .all()
        )
        recent20 = recent[:20]
        symbol_stats = _stats(recent20)

        by_leg: dict[str, list[Trade]] = {}
        by_leg_regime: dict[str, list[Trade]] = {}
        for t in recent:
            by_leg.setdefault(t.strategy_name, []).append(t)
            by_leg_regime.setdefault(f"{t.strategy_name}|{t.regime}", []).append(t)

        leg_stats = {leg: _stats(items[:50]) for leg, items in by_leg.items()}
        regime_stats = {key: _stats(items[:50]) for key, items in by_leg_regime.items()}

        disabled = set(_safe_json(record.disabled_legs, []))
        for leg, stats in leg_stats.items():
            if stats["count"] >= DISABLE_AFTER_TRADES and stats["expectancy"] < 0:
                disabled.add(leg)
            elif stats["count"] >= DISABLE_AFTER_TRADES and stats["expectancy"] > 0.05:
                disabled.discard(leg)

        reasons = []
        if symbol_stats["count"] >= MIN_TRADES_FOR_ADJUST:
            expectancy = symbol_stats["expectancy"]
            if expectancy > 0.20:
                params["size_mult"] = _clamp("size_mult", params["size_mult"] + 0.05)
                params["tp_atr_mult"] = _clamp("tp_atr_mult", params["tp_atr_mult"] + 0.10)
                reasons.append(f"positive expectancy {expectancy:+.2f}R on last {symbol_stats['count']}")
            elif expectancy < -0.10:
                params["size_mult"] = _clamp("size_mult", params["size_mult"] - 0.10)
                params["sl_atr_mult"] = _clamp("sl_atr_mult", params["sl_atr_mult"] - 0.05)
                reasons.append(f"negative expectancy {expectancy:+.2f}R on last {symbol_stats['count']}")

        snap = trade.get_indicator_snapshot()
        mfe = float(snap.get("mfe_r") or 0)
        exit_r = _r_multiple(trade)
        if trade.exit_reason == "stop_loss" and mfe >= exit_r + 1.0:
            params["trail_atr_mult"] = _clamp("trail_atr_mult", params["trail_atr_mult"] + 0.15)
            reasons.append("trail may be too tight: MFE materially exceeded exit R")

        changed = params != old_params or set(_safe_json(record.disabled_legs, [])) != disabled
        if changed:
            record.version = (record.version or 1) + 1
            record.params = json.dumps(params)
            record.disabled_legs = json.dumps(sorted(disabled))
            self.session.add(ParamChangeLog(
                symbol=self.symbol,
                source="per_coin_brain",
                old_params=json.dumps(old_params),
                new_params=json.dumps(params),
                reason="; ".join(reasons) or "leg allowlist changed from rolling expectancy",
                version=record.version,
            ))

        record.leg_stats = json.dumps(leg_stats)
        record.regime_stats = json.dumps(regime_stats)
        record.updated_at = datetime.utcnow()
        self.session.commit()

        return BrainUpdate(
            symbol=self.symbol,
            version=record.version or 1,
            params=params,
            changed=changed,
            reason="; ".join(reasons) if reasons else "stats refreshed",
            disabled_legs=sorted(disabled),
        )
