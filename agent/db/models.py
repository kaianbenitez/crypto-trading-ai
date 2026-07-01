import json
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
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
    qty = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)

    entry_reasoning = Column(Text, nullable=False)       # JSON list[str]
    indicator_snapshot = Column(Text, nullable=False)    # JSON dict
    params_snapshot = Column(Text, nullable=False)       # JSON dict, strategy params at entry time

    pnl_usdt = Column(Float, nullable=True)
    outcome = Column(String, nullable=True)              # "win" | "loss" | "breakeven"
    exit_reason = Column(String, nullable=True)           # "stop_loss" | "take_profit" | "manual" | "kill_switch"
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


def get_session(db_path: str = "sqlite:///trading_agent.db"):
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
