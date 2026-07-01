from sqlalchemy import Column, Integer, Boolean, String, DateTime
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


def get_or_create_state(session) -> AgentState:
    state = session.query(AgentState).first()
    if state is None:
        state = AgentState(kill_switch_active=False)
        session.add(state)
        session.commit()
    return state
