from sqlalchemy import Column, Integer, Boolean, String, DateTime, Float
from sqlalchemy.orm import declarative_base
from datetime import datetime

from agent.db.models import Base, get_session

# Reuses the same Base/engine as trade models so it lives in the same SQLite file.


class AgentState(Base):
    __tablename__ = "agent_state"

    id = Column(Integer, primary_key=True)
    kill_switch_active = Column(Boolean, default=False)
    kill_switch_reason = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
    # Daily-drawdown state, persisted so a service restart mid-day doesn't
    # reset the loss counter or clear an auto-triggered kill switch.
    risk_day = Column(String, nullable=True)             # ISO date the counters belong to
    daily_loss_usdt = Column(Float, nullable=True)       # gross losses today
    daily_net_pnl_usdt = Column(Float, nullable=True)    # net realized PnL today
    auto_kill_active = Column(Boolean, default=False)    # drawdown-triggered halt


def get_or_create_state(session) -> AgentState:
    state = session.query(AgentState).first()
    if state is None:
        state = AgentState(kill_switch_active=False)
        session.add(state)
        session.commit()
    return state
