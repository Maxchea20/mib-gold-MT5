from typing import Dict, List
import pandas as pd
from .base import Engine
from .trend import TrendEngine
from .structure import MarketStructureEngine
from .sr import SupportResistanceEngine
from .breakout import BreakoutEngine
from .momentum import MomentumEngine
from .volume import VolumeEngine
from .fibonacci import FibonacciEngine
from .elliott import ElliottWaveEngine
from .fvg import FVGEngine
from .pattern import PatternEngine
from ..contracts import EngineContext

ENGINE_CLASSES = [TrendEngine, SupportResistanceEngine, BreakoutEngine, MomentumEngine, VolumeEngine,
                  FibonacciEngine, ElliottWaveEngine, FVGEngine, PatternEngine, MarketStructureEngine]

ENGINE_META = [{"key": e.key, "name": e.name} for e in ENGINE_CLASSES]


class EngineSuite:
    def __init__(self):
        self.engines: List[Engine] = [cls() for cls in ENGINE_CLASSES]

    def run(self, df: pd.DataFrame, ctx: EngineContext) -> Dict[str, dict]:
        return {e.key: e.evaluate(df, ctx).to_dict() for e in self.engines}
