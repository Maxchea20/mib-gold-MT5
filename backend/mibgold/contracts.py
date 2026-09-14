from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid

Direction = Literal["long", "short", "neutral"]


@dataclass
class Signal:
    signal: Direction
    confidence: float
    reason: str
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.confidence = float(min(max(self.confidence, 0.0), 1.0))
        if self.signal not in ("long", "short", "neutral"):
            self.signal = "neutral"
        if self.signal == "neutral":
            self.confidence = min(self.confidence, 0.5)

    @staticmethod
    def neutral(reason: str, **raw) -> "Signal":
        return Signal("neutral", 0.0, reason, raw)

    def to_dict(self) -> dict:
        return {"signal": self.signal, "confidence": round(self.confidence, 4),
                "reason": self.reason, "raw_data": _clean(self.raw_data)}


@dataclass
class EngineContext:
    timeframe: str = "M5"
    session: str = "london"
    contract_size: float = 100.0
    advisory: Optional[dict] = None
    now: Optional[datetime] = None


@dataclass
class Layer:
    id: str
    group_id: str
    layer_number: int
    direction: str
    entry: float
    sl: float
    initial_sl: float
    lots: float
    risk_usd: float
    open_time: datetime
    trail_level: Optional[float] = None
    trail_active: bool = False
    peak: float = 0.0
    agent_votes: Dict[str, dict] = field(default_factory=dict)
    consensus: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    session: str = ""
    bias: Dict[str, Any] = field(default_factory=dict)
    ticket: Optional[int] = None
    tp: Optional[float] = None

    @property
    def sign(self) -> int:
        return 1 if self.direction == "long" else -1

    def pnl_usd(self, price: float, contract_size: float) -> float:
        return (price - self.entry) * self.sign * self.lots * contract_size

    def r_multiple(self, price: float) -> float:
        risk_dist = abs(self.entry - self.initial_sl)
        return 0.0 if risk_dist == 0 else (price - self.entry) * self.sign / risk_dist

    def worst_case_loss(self, contract_size: float) -> float:
        return max(0.0, (self.entry - self.sl) * self.sign * self.lots * contract_size)


def money_text(pnl: float, closed: bool) -> str:
    amt = f"${abs(pnl):,.2f}"
    if closed:
        return f"Profited {amt}" if pnl >= 0 else f"Lost {amt}"
    return f"Floating +{amt}" if pnl >= 0 else f"Floating -{amt}"


def r_text(r: float) -> str:
    return f"{r:+.2f}R"


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean(obj):
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else round(float(obj), 5)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return round(obj, 5)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
