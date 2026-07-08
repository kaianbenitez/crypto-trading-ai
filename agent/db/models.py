import json
from datetime import datetime

from sqlalchemy import Boolean, create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    strategy_name = Column(String, nullable=False)
    regime = Column(String, nullable=False)

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    qty = Column(Float, nullable=False)          # current/remaining size — mutated on partial fills
    original_qty = Column(Float, nullable=True)  # full size at entry — used for realized PnL so a
                                                  # partial TP fill's profit isn't dropped at final close
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)

    entry_reasoning = Column(Text, nullable=False)       # JSON list[str]
    indicator_snapshot = Column(Text, nullable=False)    # JSON dict
    params_snapshot = Column(Text, nullable=False)       # JSON dict, strategy params at entry time

    pnl_usdt = Column(Float, nullable=True)
    outcome = Column(String, nullable=True)              # "win" | "loss" | "breakeven"
    exit_reason = Column(String, nullable=True)           # "stop_loss" | "take_profit" | "trailing_stop" | "trailing_take_profit" | "max_hold_timeout" | "manual" | "kill_switch"
    postmortem = Column(Text, nullable=True)              # JSON list[str], filled on close

    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    def set_entry_reasoning(self, reasoning: list[str]):
        self.entry_reasoning = json.dumps(reasoning)

    def get_entry_reasoning(self) -> list[str]:
        return json.loads(self.entry_reasoning) if self.entry_reasoning else []

    def set_indicator_snapshot(self, snapshot: dict):
        self.indicator_snapshot = json.dumps(snapshot, default=str)

    def get_indicator_snapshot(self) -> dict:
        return json.loads(self.indicator_snapshot) if self.indicator_snapshot else {}

    def set_params_snapshot(self, params: dict):
        self.params_snapshot = json.dumps(params, default=str)

    def get_params_snapshot(self) -> dict:
        return json.loads(self.params_snapshot) if self.params_snapshot else {}

    def set_postmortem(self, notes: list[str]):
        self.postmortem = json.dumps(notes)

    def get_postmortem(self) -> list[str]:
        return json.loads(self.postmortem) if self.postmortem else []


class IndicatorWeight(Base):
    """Per-symbol, per-regime learned indicator weights."""
    __tablename__ = "indicator_weights"

    id          = Column(Integer, primary_key=True)
    symbol      = Column(String, nullable=False, index=True)
    regime      = Column(String, nullable=False)
    weights     = Column(Text, nullable=False)   # JSON dict {indicator: weight}
    trade_count = Column(Integer, default=0)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RosterState(Base):
    """Coin roster state — active and benched symbols."""
    __tablename__ = "roster_state"

    id             = Column(Integer, primary_key=True)
    active_symbols = Column(Text, nullable=False)   # JSON list
    benched_symbols= Column(Text, nullable=False)   # JSON dict {symbol: bench_until_iso}
    last_review    = Column(DateTime, nullable=True)
    scan_status    = Column(Text, nullable=True)    # JSON dict — dynamic market scanner status, for webapi to read


class TradeMemory(Base):
    __tablename__ = "trade_memory"

    id         = Column(Integer, primary_key=True)
    symbol     = Column(String, nullable=False, index=True)
    trade_id   = Column(Integer, nullable=False)
    text       = Column(Text, nullable=False)       # human-readable lesson
    patterns   = Column(Text, nullable=False)        # JSON list of pattern tags
    regime     = Column(String, nullable=True)
    outcome    = Column(String, nullable=True)       # win | loss | breakeven
    created_at = Column(DateTime, default=datetime.utcnow)


class PerCoinBrainState(Base):
    """Isolated adaptive state for one coin only."""
    __tablename__ = "per_coin_brain_state"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, unique=True, index=True)
    params = Column(Text, nullable=False)                 # JSON dict
    leg_stats = Column(Text, nullable=False)              # JSON dict {leg: stats}
    regime_stats = Column(Text, nullable=False)           # JSON dict {leg|regime: stats}
    disabled_legs = Column(Text, nullable=False)          # JSON list[str]
    version = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ParamChangeLog(Base):
    """Auditable parameter changes made by adaptive modules."""
    __tablename__ = "param_change_log"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False)
    old_params = Column(Text, nullable=False)
    new_params = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrailingStopEvent(Base):
    """Every exchange-side trailing stop change."""
    __tablename__ = "trailing_stop_events"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    old_stop = Column(Float, nullable=False)
    new_stop = Column(Float, nullable=False)
    mode = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    exchange_order_id = Column(String, nullable=True)
    is_major = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CommandAudit(Base):
    """Telegram command audit trail."""
    __tablename__ = "command_audit"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    command = Column(String, nullable=False)
    args = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SelfMonitorReport(Base):
    """Hourly/daily self-diagnosis reports."""
    __tablename__ = "self_monitor_reports"

    id = Column(Integer, primary_key=True)
    report_type = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    warning_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class RiskSnapshot(Base):
    """Risk profile chosen by the bankroll manager."""
    __tablename__ = "risk_snapshots"

    id = Column(Integer, primary_key=True)
    effective_bankroll_usdt = Column(Float, nullable=False)
    configured_bankroll_usdt = Column(Float, nullable=False)
    account_equity_usdt = Column(Float, nullable=True)
    risk_pct = Column(Float, nullable=False)
    tier = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    drawdown_pct = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramBotState(Base):
    """Small key-value store for Telegram polling/report schedules."""
    __tablename__ = "telegram_bot_state"

    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CoinDigest(Base):
    """Daily plain-English digest per coin: price action, what the agent is
    watching for, and free keyword-scored news sentiment."""
    __tablename__ = "coin_digests"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)

    price_low_24h = Column(Float, nullable=True)
    price_high_24h = Column(Float, nullable=True)
    price_change_pct_24h = Column(Float, nullable=True)

    regime = Column(String, nullable=True)
    watching_side = Column(String, nullable=True)   # "long" | "short" | None
    watch_low = Column(Float, nullable=True)
    watch_high = Column(Float, nullable=True)

    sentiment_score = Column(Float, nullable=True)   # -1..1, 0 = neutral/no data
    sentiment_label = Column(String, nullable=True)  # positive | negative | neutral | no data
    headlines = Column(Text, nullable=True)          # JSON list[str]

    summary = Column(Text, nullable=False)           # plain-English paragraph
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def set_headlines(self, headlines: list[str]):
        self.headlines = json.dumps(headlines)

    def get_headlines(self) -> list[str]:
        return json.loads(self.headlines) if self.headlines else []


class SignalGateEvent(Base):
    """One row per candidate rejected at a decision gate in the main loop.

    Pure observability — written alongside the existing per-cycle
    `signal_summary` lines, never used to make a trading decision. Lets us
    see which gate rejects the most trades so thresholds can be tuned from
    data rather than guesswork.
    """
    __tablename__ = "signal_gate_events"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    # gate: leg_disabled | mtf | memory | cost_edge | reentry | risk_cap | no_signal
    # (regime/context/smc rejections fold into the `no_signal` reason text,
    #  since they're internal to signal generation, not separate loop stages)
    gate = Column(String, nullable=False, index=True)
    reason = Column(Text, nullable=True)
    side = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AgentActivityLog(Base):
    """Persisted copy of every per-cycle `signal_summary` line — the same
    content the agent already logs to journalctl, but queryable over the API
    so the dashboard can show why the bot "looks idle." Pruned to a rolling
    window; additive and safe to drop/recreate."""
    __tablename__ = "agent_activity_log"

    id = Column(Integer, primary_key=True)
    cycle = Column(Integer, nullable=True)
    symbol = Column(String, nullable=True, index=True)
    level = Column(String, nullable=True)   # open | candidate | block | info
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


def _run_lightweight_migrations(engine) -> None:
    """create_all() only creates brand-new tables — it never ALTERs existing
    ones. Any column added to an existing model after the table was first
    created on a live DB needs to be added here too, or reads/writes to it
    raise 'no such column' on deployments with existing data."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "roster_state" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("roster_state")}
        if "scan_status" not in existing_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE roster_state ADD COLUMN scan_status TEXT"))

    if "agent_state" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("agent_state")}
        new_cols = {
            "risk_day": "TEXT",
            "daily_loss_usdt": "REAL",
            "daily_net_pnl_usdt": "REAL",
            "auto_kill_active": "BOOLEAN",
            "validation_started_at": "DATETIME",
        }
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE agent_state ADD COLUMN {col} {col_type}"))

    if "trades" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("trades")}
        if "original_qty" not in existing_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN original_qty REAL"))
                # Best-effort backfill: for already-closed trades this can't
                # recover the true original size (qty was already reduced by
                # any partial fill before this column existed), but it's still
                # strictly better than NULL, and any still-open trade at
                # migration time has its correct, un-reduced qty.
                conn.execute(text("UPDATE trades SET original_qty = qty WHERE original_qty IS NULL"))


_migrations_done = False


def get_session(db_path: str = "sqlite:///trading_agent.db"):
    global _migrations_done
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    if not _migrations_done:
        try:
            _run_lightweight_migrations(engine)
        except Exception:
            pass  # best-effort; a fresh DB (create_all just made it) already has the column
        _migrations_done = True
    return sessionmaker(bind=engine)()
