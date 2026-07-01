from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class Signal:
    side: Side
    confidence: float  # 0-1
    reasoning: list[str] = field(default_factory=list)
    indicator_snapshot: dict = field(default_factory=dict)
    strategy_name: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.side != Side.NONE
