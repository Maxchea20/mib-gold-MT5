import numpy as np
from .base import Engine
from .utils import atr, safe_atr, clamp
from ..contracts import Signal


class BreakoutEngine(Engine):
    """Donchian range break confirmed by volatility expansion after compression."""
    key, name, min_bars = "breakout", "Breakout/Breakdown", 60

    def _evaluate(self, df, ctx):
        n = 20
        h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
        prior_hi, prior_lo = h[-n - 1:-1].max(), l[-n - 1:-1].min()
        a_series = atr(df)
        a = safe_atr(df)
        expansion = float((h[-1] - l[-1]) / a)
        compression = float(a_series[-2] / max(np.mean(a_series[-40:-2]), 1e-9))
        rng_atr = (prior_hi - prior_lo) / a
        raw = dict(range_high=prior_hi, range_low=prior_lo, expansion=expansion,
                   compression=compression, range_atr=rng_atr)
        sq = 0.15 if compression < 0.85 else 0.0
        if c[-1] > prior_hi:
            conf = clamp(0.4 + 0.2 * min(expansion, 2) / 2 + sq + (0.1 if rng_atr < 6 else 0))
            return Signal("long", conf, f"Breakout above {n}-bar high {prior_hi:.2f}, bar {expansion:.1f}x ATR", raw)
        if c[-1] < prior_lo:
            conf = clamp(0.4 + 0.2 * min(expansion, 2) / 2 + sq + (0.1 if rng_atr < 6 else 0))
            return Signal("short", conf, f"Breakdown below {n}-bar low {prior_lo:.2f}, bar {expansion:.1f}x ATR", raw)
        pos = (c[-1] - prior_lo) / max(prior_hi - prior_lo, 1e-9)
        if compression < 0.8:
            return Signal.neutral(f"Volatility squeeze ({compression:.2f}x) inside {prior_lo:.2f}-{prior_hi:.2f}", **raw)
        return Signal.neutral(f"Inside range ({pos:.0%} of box), no break", **raw)
