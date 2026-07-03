import asyncio
import json
import subprocess
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent.config.settings import settings
from agent.db.models import get_session, Trade, PerCoinBrainState, ParamChangeLog, TrailingStopEvent
from agent.exchange.binance_futures import BinanceFuturesAdapter
from agent.dashboard.candlestick_panel import build_candlestick_payload
from agent.dashboard.reasoning_engine import position_reasoning
from webapi import app_state  # noqa: F401 (registers AgentState on the shared Base)
from webapi.app_state import get_or_create_state
from webapi.auth import verify_password, create_session_token, require_session, SESSION_COOKIE
from webapi.schemas import LoginRequest, TradeOut, KillSwitchRequest, SummaryOut, AgentStatusOut

app = FastAPI(title="Crypto Trading AI")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*(:3000)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@app.post("/api/login")
def login(payload: LoginRequest, response: Response):
    if not verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    token = create_session_token()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/trades", response_model=list[TradeOut])
def list_trades(limit: int = 100, session=Depends(db), _=Depends(require_session)):
    trades = session.query(Trade).order_by(Trade.opened_at.desc()).limit(limit).all()
    return [
        TradeOut(
            id=t.id, symbol=t.symbol, side=t.side, strategy_name=t.strategy_name, regime=t.regime,
            entry_price=t.entry_price, exit_price=t.exit_price, qty=t.qty,
            stop_loss=t.stop_loss, take_profit=t.take_profit, leverage=t.leverage,
            entry_reasoning=t.get_entry_reasoning(), indicator_snapshot=t.get_indicator_snapshot(),
            pnl_usdt=t.pnl_usdt, outcome=t.outcome, exit_reason=t.exit_reason,
            postmortem=t.get_postmortem(), opened_at=t.opened_at, closed_at=t.closed_at,
        )
        for t in trades
    ]


@app.get("/api/trades/{trade_id}", response_model=TradeOut)
def get_trade(trade_id: int, session=Depends(db), _=Depends(require_session)):
    t = session.query(Trade).get(trade_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    return TradeOut(
        id=t.id, symbol=t.symbol, side=t.side, strategy_name=t.strategy_name, regime=t.regime,
        entry_price=t.entry_price, exit_price=t.exit_price, qty=t.qty,
        stop_loss=t.stop_loss, take_profit=t.take_profit, leverage=t.leverage,
        entry_reasoning=t.get_entry_reasoning(), indicator_snapshot=t.get_indicator_snapshot(),
        pnl_usdt=t.pnl_usdt, outcome=t.outcome, exit_reason=t.exit_reason,
        postmortem=t.get_postmortem(), opened_at=t.opened_at, closed_at=t.closed_at,
    )


@app.get("/api/summary", response_model=SummaryOut)
def summary(session=Depends(db), _=Depends(require_session)):
    trades = session.query(Trade).filter(Trade.closed_at.isnot(None)).all()
    wins = [t for t in trades if t.outcome == "win"]
    total_pnl = sum(t.pnl_usdt or 0 for t in trades)
    open_count = session.query(Trade).filter(Trade.closed_at.is_(None)).count()
    state = get_or_create_state(session)

    return SummaryOut(
        total_trades=len(trades),
        win_rate_pct=(len(wins) / len(trades) * 100) if trades else 0.0,
        roi_pct=(total_pnl / settings.bankroll_usdt * 100) if settings.bankroll_usdt else 0.0,
        open_positions=open_count,
        kill_switch_active=state.kill_switch_active,
        bankroll_usdt=settings.bankroll_usdt,
    )


@app.post("/api/kill-switch")
def set_kill_switch(payload: KillSwitchRequest, session=Depends(db), _=Depends(require_session)):
    state = get_or_create_state(session)
    state.kill_switch_active = payload.active
    state.kill_switch_reason = payload.reason
    session.commit()
    return {"ok": True, "kill_switch_active": state.kill_switch_active}


def _service_state(name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return (result.stdout or result.stderr or "unknown").strip() or "unknown"
    except Exception:
        return "unknown"


@app.get("/api/agent-status", response_model=AgentStatusOut)
def agent_status(_=Depends(require_session)):
    return AgentStatusOut(
        trading_agent=_service_state("trading-agent"),
        webapi=_service_state("webapi"),
        dashboard=_service_state("dashboard"),
        nginx=_service_state("nginx"),
        exchange=settings.exchange,
        testnet=settings.binance_testnet,
        symbols=[
            "BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "ADA/USDT",
            "BNB/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
            "POL/USDT", "LTC/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT",
        ],
        bankroll_usdt=settings.bankroll_usdt,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/open-positions-detail")
def open_positions_detail(session=Depends(db), _=Depends(require_session)):
    trades = (
        session.query(Trade)
        .filter(Trade.closed_at.is_(None))
        .order_by(Trade.opened_at.desc())
        .all()
    )
    return [
        {
            "trade": {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "strategy_name": t.strategy_name,
                "regime": t.regime,
                "entry_price": t.entry_price,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "qty": t.qty,
                "opened_at": t.opened_at,
                "indicator_snapshot": t.get_indicator_snapshot(),
            },
            "reasoning": position_reasoning(t, {
                "stop_loss": t.stop_loss,
                "trail_active": bool(
                    session.query(TrailingStopEvent)
                    .filter(TrailingStopEvent.trade_id == t.id)
                    .count()
                ),
            }),
        }
        for t in trades
    ]


@app.get("/api/candles/{symbol:path}")
def candles(symbol: str, timeframe: str = "1h", limit: int = 120, session=Depends(db), _=Depends(require_session)):
    safe_limit = max(20, min(limit, 300))
    adapter = BinanceFuturesAdapter()
    candle_rows = adapter.fetch_ohlcv(symbol, timeframe, limit=safe_limit)
    trade = (
        session.query(Trade)
        .filter(Trade.symbol == symbol, Trade.closed_at.is_(None))
        .order_by(Trade.opened_at.desc())
        .first()
    )
    trail_events = []
    if trade:
        trail_events = (
            session.query(TrailingStopEvent)
            .filter(TrailingStopEvent.trade_id == trade.id)
            .order_by(TrailingStopEvent.created_at.asc())
            .all()
        )
    return build_candlestick_payload(symbol, candle_rows, trade, trail_events)


@app.get("/api/coin-brains")
def coin_brains(session=Depends(db), _=Depends(require_session)):
    records = session.query(PerCoinBrainState).order_by(PerCoinBrainState.symbol.asc()).all()
    return [
        {
            "symbol": r.symbol,
            "params": json.loads(r.params),
            "leg_stats": json.loads(r.leg_stats),
            "regime_stats": json.loads(r.regime_stats),
            "disabled_legs": json.loads(r.disabled_legs),
            "version": r.version,
            "updated_at": r.updated_at,
        }
        for r in records
    ]


@app.get("/api/adaptive-activity")
def adaptive_activity(limit: int = 50, session=Depends(db), _=Depends(require_session)):
    safe_limit = max(1, min(limit, 200))
    param_changes = (
        session.query(ParamChangeLog)
        .order_by(ParamChangeLog.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    trail_events = (
        session.query(TrailingStopEvent)
        .order_by(TrailingStopEvent.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    rows = [
        {
            "type": "param_change",
            "symbol": p.symbol,
            "message": p.reason,
            "created_at": p.created_at,
            "payload": {"source": p.source, "version": p.version},
        }
        for p in param_changes
    ] + [
        {
            "type": "trail_move",
            "symbol": e.symbol,
            "message": e.reason,
            "created_at": e.created_at,
            "payload": {"old_stop": e.old_stop, "new_stop": e.new_stop, "mode": e.mode},
        }
        for e in trail_events
    ]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:safe_limit]


@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket, symbol: str = "BTC/USDT"):
    """Streams a public-data price tick every few seconds. Uses the same
    adapter as the live agent will, read-only (no order placement here)."""
    await websocket.accept()
    adapter = BinanceFuturesAdapter()
    try:
        while True:
            candles = adapter.fetch_ohlcv(symbol, "1m", limit=1)
            if candles:
                last = candles[-1]
                await websocket.send_text(json.dumps({
                    "symbol": symbol, "timestamp": last.timestamp, "close": last.close,
                }))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
