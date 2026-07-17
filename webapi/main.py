import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, Depends, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent.config.settings import settings, save_runtime_overrides
from agent.db.models import get_session, Trade, PerCoinBrainState, ParamChangeLog, TrailingStopEvent, CoinDigest, RosterState, SignalGateEvent, AgentActivityLog
from agent.exchange.binance_futures import BinanceFuturesAdapter
from agent.dashboard.candlestick_panel import build_candlestick_payload
from agent.dashboard.plain_english import simplify_lines
from agent.dashboard.reasoning_engine import position_reasoning
from agent.dashboard.trade_narrative import build_narrative
from agent.fundamental.coin_digest import cached_sentiment
from agent.risk.bankroll import latest_risk_snapshot
from webapi import app_state  # noqa: F401 (registers AgentState on the shared Base)
from webapi.app_state import get_or_create_state
from webapi.auth import verify_password, create_session_token, require_session, SESSION_COOKIE
from webapi.schemas import (
    LoginRequest, TradeOut, KillSwitchRequest, SummaryOut, AgentStatusOut, LivePositionOut, CoinDigestOut,
    SettingsSnapshotOut, SettingsUpdateRequest, SettingsUpdateOut, InsightsOut, InsightItemOut,
)

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
            entry_reasoning=simplify_lines(t.get_entry_reasoning()), indicator_snapshot=t.get_indicator_snapshot(),
            pnl_usdt=t.pnl_usdt, outcome=t.outcome, exit_reason=t.exit_reason,
            postmortem=simplify_lines(t.get_postmortem()), opened_at=t.opened_at, closed_at=t.closed_at,
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
        entry_reasoning=simplify_lines(t.get_entry_reasoning()), indicator_snapshot=t.get_indicator_snapshot(),
        pnl_usdt=t.pnl_usdt, outcome=t.outcome, exit_reason=t.exit_reason,
        postmortem=simplify_lines(t.get_postmortem()), opened_at=t.opened_at, closed_at=t.closed_at,
    )


@app.get("/api/trades/{trade_id}/narrative")
def trade_narrative(trade_id: int, session=Depends(db), _=Depends(require_session)):
    """Structured thesis/concern/plan/invalidation/past-context (and, once
    closed, failure/lesson/stats) — the same sections shown in the Telegram
    open/close notifications, for the Journal's expanded row instead of a
    flat dump of every reasoning line."""
    t = session.query(Trade).get(trade_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    n = build_narrative(t, session)
    return {
        "symbol": n.symbol, "side": n.side, "strategy_name": n.strategy_name, "regime": n.regime,
        "confidence": n.confidence, "ev_r": n.ev_r,
        "thesis_lines": n.thesis_lines, "why_accepted_lines": n.why_accepted_lines, "weakness_line": n.weakness_line,
        "entry": n.entry, "stop_loss": n.stop_loss, "take_profit": n.take_profit, "rr": n.rr,
        "risk_pct": n.risk_pct, "risk_usdt": n.risk_usdt,
        "invalidation_line": n.invalidation_line, "past_context_line": n.past_context_line,
        "outcome": n.outcome, "exit_reason": n.exit_reason, "exit_price": n.exit_price,
        "pnl_usdt": n.pnl_usdt, "r_multiple": n.r_multiple, "held_duration": n.held_duration,
        "mfe_r": n.mfe_r, "mae_r": n.mae_r, "mfe_price": n.mfe_price, "mae_price": n.mae_price,
        "lesson_line": n.lesson_line, "failure_line": n.failure_line,
    }


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
        total_pnl_usdt=total_pnl,
        open_positions=open_count,
        kill_switch_active=state.kill_switch_active,
        bankroll_usdt=settings.bankroll_usdt,
    )


@app.get("/api/risk-status")
def risk_status(session=Depends(db), _=Depends(require_session)):
    risk = latest_risk_snapshot(session, settings)
    return {
        "effective_bankroll_usdt": risk["effective_bankroll_usdt"],
        "configured_bankroll_usdt": risk["configured_bankroll_usdt"],
        "account_equity_usdt": risk["account_equity_usdt"],
        "bankroll_divergence_pct": risk["bankroll_divergence_pct"],
        "risk_pct": risk["risk_pct"],
        "tier": risk["tier"],
        "mode": risk["mode"],
        "drawdown_pct": risk["drawdown_pct"],
        "reason": risk["reason"],
        "created_at": risk["created_at"],
    }


@app.get("/api/validation")
def validation(session=Depends(db), _=Depends(require_session)):
    risk = latest_risk_snapshot(session, settings)
    leg_readiness_out = {
        key: {
            "closed_count": v["closed_count"],
            "ready": v["ready"],
            "failed": v["failed"],
        }
        for key, v in risk["validation"]["leg_readiness"].items()
    }
    return {
        "risk": {
            "effective_bankroll_usdt": risk["effective_bankroll_usdt"],
            "risk_pct": risk["risk_pct"],
            "tier": risk["tier"],
            "mode": risk["mode"],
            "reason": risk["reason"],
            "bankroll_divergence_pct": risk["bankroll_divergence_pct"],
        },
        "metrics": asdict(risk["metrics"]),
        "readiness": risk["readiness"],
        # Fixed window anchored to validation_started_at (Fix 9) — doesn't
        # decay just because the rolling 30d window's trade count drops.
        "metrics_fixed_window": asdict(risk["metrics_fixed_window"]),
        "readiness_fixed_window": risk["readiness_fixed_window"],
        "validation": {
            "validation_started_at": risk["validation"]["validation_started_at"],
            "days_elapsed": risk["validation"]["days_elapsed"],
            "days_remaining": risk["validation"]["days_remaining"],
            "min_days_required": risk["validation"]["min_days_required"],
            "leg_readiness": leg_readiness_out,
        },
    }


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


@app.get("/api/news-status")
def news_status(_=Depends(require_session)):
    """News provider config state — enabled/disabled, provider name. Does not
    make a live API call; this is just the configuration, not a live probe."""
    return {
        "enabled": settings.news_enabled,
        "provider": settings.news_provider,
        "api_url": settings.news_api_url,
    }


@app.get("/api/settings", response_model=SettingsSnapshotOut)
def get_settings(_=Depends(require_session)):
    return SettingsSnapshotOut(
        updated_at=None,
        values=settings.runtime_snapshot(),
    )


@app.put("/api/settings", response_model=SettingsUpdateOut)
def update_settings(payload: SettingsUpdateRequest, _=Depends(require_session)):
    save_runtime_overrides(payload.values)
    return SettingsUpdateOut(
        ok=True,
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        values=settings.runtime_snapshot(),
    )


_CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


@app.get("/api/insights", response_model=InsightsOut)
def insights(session=Depends(db), _=Depends(require_session)):
    risk = latest_risk_snapshot(session, settings)
    summary = {
        "total_trades": risk["metrics"].trade_count,
        "closed_trades": risk["metrics"].closed_count,
        "open_positions": risk["metrics"].open_count,
        "roi_pct": risk["metrics"].roi_pct,
        "win_rate_pct": risk["metrics"].win_rate_pct,
        "total_pnl_usdt": risk["metrics"].total_pnl_usdt,
    }
    roster_data = roster(session=session)
    gate_24h = gate_stats("24h", session=session)
    gate_7d = gate_stats("7d", session=session)
    recent_activity = activity_log(limit=12, session=session)
    adaptive = adaptive_activity(limit=8, session=session)
    recent_trades = (
        session.query(Trade)
        .filter(Trade.closed_at.isnot(None))
        .order_by(Trade.closed_at.desc())
        .limit(12)
        .all()
    )

    exit_breakdown = risk["metrics"].exit_reason_breakdown
    strongest_symbol = max(risk["metrics"].by_symbol.items(), key=lambda item: item[1]["pnl"], default=None)
    weakest_symbol = min(risk["metrics"].by_symbol.items(), key=lambda item: item[1]["pnl"], default=None)
    top_strategy = max(risk["metrics"].by_strategy.items(), key=lambda item: item[1]["pnl"], default=None)
    runner_count = risk["metrics"].runner_count
    trailing_stop_count = exit_breakdown.get("trailing_stop", 0)
    take_profit_count = exit_breakdown.get("take_profit", 0)

    recommendations = []
    if not risk["readiness"]["ready"]:
        recommendations.append(
            f"Validation is still gating proven risk: {', '.join(risk['readiness']['failed'][:3]) or 'sample still maturing'}."
        )
    if risk["metrics"].avg_estimated_cost_r and risk["metrics"].tiny_win_count > 0:
        recommendations.append(
            f"Average estimated cost is {risk['metrics'].avg_estimated_cost_r:.2f}R and {risk['metrics'].tiny_win_count} small wins are leaving little room after fees."
        )
    if trailing_stop_count > take_profit_count:
        recommendations.append(
            f"Trailing-stop exits ({trailing_stop_count}) are outnumbering fixed TPs ({take_profit_count}); the runner path may be too aggressive."
        )
    if runner_count == 0 and take_profit_count > 0:
        recommendations.append("No runner closes were recorded in this window, so trend trades are probably still hitting the fixed TP or stop too early.")
    if risk["metrics"].reentry_count > 0:
        recommendations.append(
            f"Re-entries contributed {risk['metrics'].reentry_count} trades; check whether same-coin churn is helping or just paying extra fees."
        )
    if roster_data.get("scan", {}).get("status") not in (None, "healthy", "running", "ok", "admitted"):
        recommendations.append(f"Scanner status is {roster_data.get('scan', {}).get('status')} — shortlist quality may be lagging.")

    if strongest_symbol:
        sym, row = strongest_symbol
        recommendations.append(f"Best symbol by P&L: {sym} ({_fmt_money(row['pnl'])}, avg {row['avg_r']:.2f}R).")
    if weakest_symbol:
        sym, row = weakest_symbol
        recommendations.append(f"Weakest symbol by P&L: {sym} ({_fmt_money(row['pnl'])}, avg {row['avg_r']:.2f}R).")
    if top_strategy:
        sym, row = top_strategy
        recommendations.append(f"Top strategy: {sym} ({_fmt_money(row['pnl'])}, {row['count']} trades).")

    signals = [
        InsightItemOut(title="Validation", value=f"{risk['validation']['days_elapsed']}d", note=f"{risk['validation']['days_remaining']}d until the 30-day floor"),
        InsightItemOut(title="Profit factor", value=f"{risk['metrics'].profit_factor:.2f}", note=f"Expectancy {risk['metrics'].expectancy_r:.2f}R / after cost {risk['metrics'].expectancy_after_estimated_cost_r:.2f}R"),
        InsightItemOut(title="Trailing exits", value=str(trailing_stop_count), note=f"Runner exits {runner_count}, fixed TPs {take_profit_count}"),
        InsightItemOut(title="Gate pressure", value=str(gate_24h["total"]), note=f"{gate_24h['window']} rejects, {gate_7d['total']} over 7d"),
        InsightItemOut(title="Scanner", value=str(roster_data.get("scan", {}).get("selected_count") or 0), note=f"Shortlisted out of {roster_data.get('scan', {}).get('eligible') or 0} eligible"),
    ]

    return InsightsOut(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        summary=summary,
        risk={
            "tier": risk["tier"],
            "risk_pct": risk["risk_pct"],
            "drawdown_pct": risk["drawdown_pct"],
            "reason": risk["reason"],
            "effective_bankroll_usdt": risk["effective_bankroll_usdt"],
            "bankroll_divergence_pct": risk["bankroll_divergence_pct"],
        },
        validation={
            "ready": risk["readiness"]["ready"],
            "failed": risk["readiness"]["failed"],
            "days_elapsed": risk["validation"]["days_elapsed"],
            "days_remaining": risk["validation"]["days_remaining"],
            "min_days_required": risk["validation"]["min_days_required"],
            "closed_count": risk["metrics"].closed_count,
            "expectancy_after_cost_r": risk["metrics"].expectancy_after_estimated_cost_r,
            "profit_factor": risk["metrics"].profit_factor,
            "max_drawdown_pct": risk["metrics"].max_drawdown_pct,
        },
        scan=roster_data,
        trading={
            "exit_breakdown": exit_breakdown,
            "by_symbol": risk["metrics"].by_symbol,
            "by_strategy": risk["metrics"].by_strategy,
            "reentry_count": risk["metrics"].reentry_count,
            "reentry_expectancy_r": risk["metrics"].reentry_expectancy_r,
            "runner_count": runner_count,
            "runner_pnl_usdt": risk["metrics"].runner_pnl_usdt,
            "avg_estimated_cost_r": risk["metrics"].avg_estimated_cost_r,
            "high_cost_trade_count": risk["metrics"].high_cost_trade_count,
            "tiny_win_count": risk["metrics"].tiny_win_count,
            "open_risk_usdt": risk["metrics"].open_risk_usdt,
            "recent_closed_trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "strategy_name": t.strategy_name,
                    "pnl_usdt": t.pnl_usdt,
                    "exit_reason": t.exit_reason,
                    "opened_at": t.opened_at,
                    "closed_at": t.closed_at,
                }
                for t in recent_trades
            ],
        },
        signals=signals,
        recommendations=recommendations,
        recent_activity=[
            {
                "id": entry["id"],
                "cycle": entry["cycle"],
                "symbol": entry["symbol"],
                "level": entry["level"],
                "message": entry["message"],
                "created_at": entry["created_at"],
            }
            for entry in recent_activity[:8]
        ] + [
            {
                "id": idx,
                "cycle": None,
                "symbol": item["symbol"],
                "level": "info",
                "message": f"{item['type']}: {item['message']}",
                "created_at": item["created_at"],
            }
            for idx, item in enumerate(adaptive[:5], start=1)
        ],
    )


@app.get("/api/strategy-profile")
def strategy_profile(_=Depends(require_session)):
    """Active strategy profile and which modules may affect a trade decision
    vs. observe-only. Config state, not a live probe."""
    from agent.strategy.profiles import get_profile
    p = get_profile(settings.strategy_profile)
    return {
        "profile": p.name,
        "decision_active": p.decision_active_modules,
        "observe_only": p.observe_only_modules,
    }


@app.get("/api/strategy")
def strategy(_=Depends(require_session)):
    """Live strategy configuration for the dashboard. This is intentionally
    assembled from settings/profile so the page follows .env changes after a
    service restart instead of becoming static documentation."""
    from agent.strategy.profiles import get_profile

    p = get_profile(settings.strategy_profile)
    fixed_majors = [s.strip() for s in settings.market_scan_fixed_majors.split(",") if s.strip()]
    excluded = [s.strip() for s in settings.market_scan_exclude_symbols.split(",") if s.strip()]

    def cfg(name, default=None):
        return getattr(settings, name, default)

    return {
        "profile": {
            "name": p.name,
            "decision_active": p.decision_active_modules,
            "observe_only": p.observe_only_modules,
        },
        "execution": {
            "exchange": settings.exchange,
            "testnet": settings.binance_testnet if settings.exchange == "binance" else settings.bybit_testnet,
            "timeframe": "1h",
            "evaluation": "once per fresh closed 1h candle per active coin",
            "mtf_timeframes": ["15m", "1h", "4h", "1d", "1w"],
        },
        "scanner": {
            "enabled": cfg("dynamic_market_scan", False),
            "top_n": cfg("market_scan_top_n", 15),
            "active_symbols": cfg("market_scan_active_symbols", cfg("market_scan_top_n", 15)),
            "refresh_minutes": cfg("market_scan_refresh_minutes", 60),
            "min_quote_volume": cfg("market_scan_min_quote_volume", 0),
            "max_spread_pct": cfg("market_scan_max_spread_pct", 0),
            "max_abs_24h_change_pct": cfg("market_scan_max_abs_24h_change_pct", 0),
            "use_mainnet_liquidity": cfg("market_scan_use_mainnet_liquidity", False),
            "require_market_cap_rank": cfg("market_scan_require_market_cap_rank", False),
            "min_market_cap_rank": cfg("market_scan_min_market_cap_rank", 0),
            "include_fixed_majors": cfg("market_scan_include_fixed_majors", False),
            "fixed_majors": fixed_majors,
            "excluded_symbols": excluded,
        },
        "signals": {
            "regime_rule": "ADX: trending vs ranging",
            "trend_following": [
                "EMA fast/slow alignment or fresh crossover",
                "MACD confirmation",
                "ADX trend strength",
                "volume confirmation",
            ],
            "mean_reversion": [
                "RSI extreme",
                "Bollinger Band touch",
                "volume confirmation for weaker single-condition setups",
            ],
            "hard_blocks": [
                "ATR shock filter",
                "MTF opposite bias",
                "EV below cost-aware floor",
                "thin reward versus estimated cost",
                "same-coin re-entry guard",
                "portfolio or same-direction risk cap",
            ],
        },
        "risk": {
            "bankroll_usdt": cfg("bankroll_usdt", 0),
            "bankroll_mode": cfg("bankroll_mode", "static"),
            "max_risk_per_trade_pct": cfg("max_risk_per_trade_pct", 0),
            "max_concurrent_positions": cfg("max_concurrent_positions", 0),
            "split_risk_across_slots": cfg("split_risk_across_slots", False),
            "max_portfolio_risk_pct": cfg("max_portfolio_risk_pct", 0),
            "max_same_direction_risk_pct": cfg("max_same_direction_risk_pct", 0),
            "min_entry_risk_pct": cfg("min_entry_risk_pct", 0),
            "default_leverage": cfg("default_leverage", 1),
            "max_leverage": cfg("max_leverage", 1),
            "confidence_risk_scaling": cfg("confidence_risk_scaling", False),
            "confidence_full_risk_at": cfg("confidence_full_risk_at", 0),
            "risk_tier_mode": cfg("risk_tier_mode", "fixed"),
            "risk_base_pct": cfg("risk_base_pct", 0),
            "risk_recovery_pct": cfg("risk_recovery_pct", 0),
            "risk_drawdown_pct": cfg("risk_drawdown_pct", 0),
            "risk_proven_pct": cfg("risk_proven_pct", 0),
            "daily_drawdown_pct": cfg("max_daily_drawdown_pct", 0),
        },
        "costs": {
            "taker_fee_pct": cfg("taker_fee_pct", 0),
            "slippage_pct": cfg("slippage_pct", 0),
            "min_live_ev_r": cfg("min_live_ev_r", 0),
            "min_edge_after_cost_r": cfg("min_edge_after_cost_r", 0),
            "max_estimated_cost_r": cfg("max_estimated_cost_r", 0),
            "min_net_ev_after_cost_r": cfg("min_net_ev_after_cost_r", 0),
            "min_expected_reward_cost_multiple": cfg("min_expected_reward_cost_multiple", 0),
            "min_stop_cost_multiple": cfg("min_stop_cost_multiple", 0),
        },
        "management": {
            "stop_loss": "exchange-side SL placed immediately after entry",
            "take_profit": "exchange-side TP placed immediately after entry",
            "regular_trailing": "enabled after +1R; trend trades use ATR trailing around 2.2x ATR",
            "trailing_take_profit": "runner mode can replace fixed TP after about +1.6R on strong trend trades",
            "max_hold": "force-close after 48h",
            "reentry": {
                "max_trades_per_symbol_per_day": cfg("reentry_max_trades_per_symbol_per_day", 0),
                "min_ev_multiplier": cfg("reentry_min_ev_multiplier", 0),
            },
        },
        "context": {
            "news_enabled": cfg("news_enabled", False),
            "news_provider": cfg("news_provider", "none"),
            "coin_digest_hour_ph": cfg("coin_digest_hour_ph", 21),
            "telegram_close_lessons": cfg("telegram_show_close_lessons", False),
        },
    }


@app.get("/api/changelog")
def changelog(_=Depends(require_session)):
    """Raw contents of the repo's CHANGELOG.md for the dashboard's Changelog page."""
    try:
        text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        text = "# Changelog\n\nNo changelog file found."
    return {"markdown": text}


@app.get("/api/open-positions-detail")
def open_positions_detail(session=Depends(db), _=Depends(require_session)):
    trades = (
        session.query(Trade)
        .filter(Trade.closed_at.is_(None))
        .order_by(Trade.opened_at.desc())
        .all()
    )
    result = []
    for t in trades:
        sentiment = cached_sentiment(session, t.symbol)
        result.append({
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
            }, session=session),
            "news": {"label": sentiment.label, "score": sentiment.score},
        })
    return result


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


@app.get("/api/live-positions", response_model=list[LivePositionOut])
def live_positions(_=Depends(require_session)):
    """Real exchange-reported unrealized P&L — accounts for fees and true mark
    price, unlike the frontend's (close - entry) * qty approximation."""
    try:
        adapter = BinanceFuturesAdapter()
        positions = adapter.get_open_positions()
    except Exception:
        return []
    out = []
    for p in positions:
        if float(p.get("contracts") or 0) == 0:
            continue
        mark = p.get("markPrice")
        raw_info = p.get("info") or {}
        break_even = raw_info.get("breakEvenPrice") or p.get("entryPrice")
        roi_pct = None
        if p.get("percentage") is not None:
            roi_pct = float(p["percentage"])
        out.append(LivePositionOut(
            symbol=p.get("symbol", ""),
            mark_price=float(mark) if mark is not None else None,
            unrealized_pnl=float(p.get("unrealizedPnl")) if p.get("unrealizedPnl") is not None else None,
            roi_pct=roi_pct,
            break_even_price=float(break_even) if break_even is not None else None,
        ))
    return out


@app.get("/api/coin-digests", response_model=list[CoinDigestOut])
def coin_digests(session=Depends(db), _=Depends(require_session)):
    """Latest daily digest per coin: 24h price action, what the agent is
    watching for, and free news sentiment. Refreshed once a day by the agent."""
    rows = session.query(CoinDigest).order_by(CoinDigest.created_at.desc()).all()
    latest_by_symbol: dict[str, CoinDigest] = {}
    for row in rows:
        if row.symbol not in latest_by_symbol:
            latest_by_symbol[row.symbol] = row
    return [
        CoinDigestOut(
            symbol=row.symbol,
            price_low_24h=row.price_low_24h,
            price_high_24h=row.price_high_24h,
            price_change_pct_24h=row.price_change_pct_24h,
            regime=row.regime,
            watching_side=row.watching_side,
            watch_low=row.watch_low,
            watch_high=row.watch_high,
            sentiment_score=row.sentiment_score,
            sentiment_label=row.sentiment_label,
            headlines=row.get_headlines(),
            summary=row.summary,
            created_at=row.created_at,
        )
        for row in sorted(latest_by_symbol.values(), key=lambda r: r.symbol)
    ]


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


_GATE_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}

# Human-friendly labels for the gate keys the agent writes.
_GATE_LABELS = {
    "no_signal":    "No signal (TA/regime/structure)",
    "mtf":          "Multi-timeframe confluence",
    "cost_edge":    "Cost / edge floor",
    "reentry":      "Re-entry cooldown/gate",
    "memory":       "Memory (past-loss)",
    "risk_cap":     "Risk / admission caps",
    "leg_disabled": "Strategy leg disabled",
}


@app.get("/api/gate-stats")
def gate_stats(window: str = "24h", session=Depends(db), _=Depends(require_session)):
    """Counts of candidate rejections per decision gate over a time window,
    so we can see which gate rejects the most trades and tune thresholds from
    data. Observability only — reads what the agent recorded."""
    delta = _GATE_WINDOWS.get(window, _GATE_WINDOWS["24h"])
    since = datetime.now(timezone.utc).replace(tzinfo=None) - delta
    rows = (
        session.query(SignalGateEvent)
        .filter(SignalGateEvent.created_at >= since)
        .all()
    )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.gate] = counts.get(r.gate, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "window": window if window in _GATE_WINDOWS else "24h",
        "total": sum(counts.values()),
        "gates": [
            {"gate": g, "label": _GATE_LABELS.get(g, g), "count": c}
            for g, c in ranked
        ],
    }


@app.get("/api/activity-log")
def activity_log(limit: int = 200, since: str | None = None, session=Depends(db), _=Depends(require_session)):
    """The agent's per-cycle decision notes (same content it logs to
    journalctl), newest first. Optional `since` is an ISO timestamp."""
    safe_limit = max(1, min(limit, 1000))
    q = session.query(AgentActivityLog)
    if since:
        try:
            ts = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            q = q.filter(AgentActivityLog.created_at > ts)
        except ValueError:
            pass
    rows = q.order_by(AgentActivityLog.id.desc()).limit(safe_limit).all()
    return [
        {
            "id": r.id,
            "cycle": r.cycle,
            "symbol": r.symbol,
            "level": r.level,
            "message": r.message,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.get("/api/roster")
def roster(session=Depends(db), _=Depends(require_session)):
    """Read-only view of the active/benched coin roster, plus the dynamic
    market scanner's last-run status. Benching/unbenching and the scan itself
    happen automatically in the agent process; this just reads what it wrote."""
    record = session.query(RosterState).first()
    if not record:
        return {
            "active": [], "benched": [], "last_review": None,
            "scan": {"enabled": settings.dynamic_market_scan, "status": "not_run_yet"},
        }
    try:
        scan_status = json.loads(record.scan_status) if record.scan_status else {
            "enabled": settings.dynamic_market_scan, "status": "not_run_yet",
        }
    except Exception:
        scan_status = {"enabled": settings.dynamic_market_scan, "status": "unknown"}
    return {
        "active": json.loads(record.active_symbols),
        "benched": [
            {"symbol": sym, "until": until}
            for sym, until in json.loads(record.benched_symbols).items()
        ],
        "last_review": record.last_review,
        "scan": scan_status,
    }


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
