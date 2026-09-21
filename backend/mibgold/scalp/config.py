"""Frozen V1 parameters. Do not tune until the first raw backtest is reviewed."""
from dataclasses import dataclass

SWING_K = 2
MIN_SWEEP_ATR = 0.15
MAX_SWEEP_ATR = 1.20
RECLAIM_MAX_BARS = 8
MAX_PULLBACK_FRAC = 0.62
MIN_RVOL = 0.80
SL_BUFFER_ATR_1M = 0.15
MIN_SL_ATR_1M = 0.35
MAX_SPREAD_ATR_5M = 0.40
LEVEL_TOUCH_ATR = 0.35
ASIA = (0, 8)
LONDON = (7, 16)
NY = (12, 21)


@dataclass
class ScalpConfig:
    swing_k: int = SWING_K
    min_sweep_atr: float = MIN_SWEEP_ATR
    max_sweep_atr: float = MAX_SWEEP_ATR
    reclaim_max_bars: int = RECLAIM_MAX_BARS
    max_pullback_frac: float = MAX_PULLBACK_FRAC
    min_rvol: float = MIN_RVOL
    sl_buffer_atr_1m: float = SL_BUFFER_ATR_1M
    min_sl_atr_1m: float = MIN_SL_ATR_1M
    max_spread_atr_5m: float = MAX_SPREAD_ATR_5M
    level_touch_atr: float = LEVEL_TOUCH_ATR
    frozen: bool = True
    version: str = "SCALP_V1_SWEEP_RECLAIM"
