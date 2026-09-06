from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List
import pandas as pd
from ..risk import SymbolSpec


class Tick:
    __slots__ = ("time", "bid", "ask")

    def __init__(self, time: datetime, bid: float, ask: float):
        self.time, self.bid, self.ask = time, bid, ask

    @property
    def mid(self):
        return (self.bid + self.ask) / 2

    def to_dict(self):
        return {"time": self.time.isoformat(), "bid": round(self.bid, 2), "ask": round(self.ask, 2), "mid": round(self.mid, 2)}


class DataAdapter(ABC):
    """Thin broker boundary. Engines never see this - they only get DataFrames."""
    name = "base"

    @abstractmethod
    def connect(self) -> dict: ...

    @abstractmethod
    def symbol_spec(self) -> SymbolSpec: ...

    @abstractmethod
    def account(self) -> dict: ...

    @abstractmethod
    def tick(self) -> Optional[Tick]: ...

    @abstractmethod
    def m1_history(self, bars: int) -> pd.DataFrame: ...

    @abstractmethod
    def m1_range(self, start: datetime, end: datetime) -> pd.DataFrame: ...

    def place_order(self, direction: str, lots: float, sl: float, comment: str = "") -> dict:
        return {"ok": True, "ticket": None, "paper": True}

    def close_position(self, ticket, lots: float, direction: str) -> dict:
        return {"ok": True, "paper": True}

    def modify_sl(self, ticket, sl: float) -> dict:
        return {"ok": True, "paper": True}

    def positions(self) -> List[dict]:
        return []

    def shutdown(self):
        pass
