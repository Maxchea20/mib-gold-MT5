from abc import ABC, abstractmethod
import pandas as pd
from ..contracts import Signal, EngineContext


class Engine(ABC):
    """Broker/time-agnostic analysis engine. Takes OHLCV, returns a Signal. Never touches MT5."""
    key: str = "engine"
    name: str = "Engine"
    min_bars: int = 60

    def evaluate(self, df: pd.DataFrame, ctx: EngineContext) -> Signal:
        if df is None or len(df) < self.min_bars:
            return Signal.neutral(f"{self.name}: insufficient bars ({0 if df is None else len(df)}/{self.min_bars})")
        try:
            return self._evaluate(df, ctx)
        except Exception as e:  # engine failure must never break the pipeline
            return Signal.neutral(f"{self.name}: evaluation error ({type(e).__name__})", error=str(e))

    @abstractmethod
    def _evaluate(self, df: pd.DataFrame, ctx: EngineContext) -> Signal: ...
