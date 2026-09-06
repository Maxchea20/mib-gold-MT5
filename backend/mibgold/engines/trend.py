import numpy as np
from .base import Engine
from .utils import ema, safe_atr, clamp
from ..contracts import Signal


class TrendEngine(Engine):
    key, name, min_bars = "trend", "Trend", 60

    def _evaluate(self, df, ctx):
        c = df["close"].to_numpy()
        e20, e50 = ema(c, 20), ema(c, 50)
        a = safe_atr(df)
        price = c[-1]
        slope = (e20[-1] - e20[-6]) / a  # ATR-normalized 5-bar slope of fast MA
        sep = (e20[-1] - e50[-1]) / a
        raw = dict(ema20=e20[-1], ema50=e50[-1], slope_atr=slope, sep_atr=sep, atr=a)
        if price > e20[-1] > e50[-1] and slope > 0:
            conf = clamp(0.35 + 0.25 * min(sep, 2) + 0.2 * min(slope, 1.5))
            return Signal("long", conf, f"Bullish stack: price > EMA20 > EMA50, slope {slope:+.2f} ATR/5b", raw)
        if price < e20[-1] < e50[-1] and slope < 0:
            conf = clamp(0.35 + 0.25 * min(-sep, 2) + 0.2 * min(-slope, 1.5))
            return Signal("short", conf, f"Bearish stack: price < EMA20 < EMA50, slope {slope:+.2f} ATR/5b", raw)
        if abs(sep) < 0.3:
            return Signal.neutral(f"EMAs compressed ({sep:+.2f} ATR apart) - no trend", **raw)
        return Signal.neutral("Mixed MA alignment - trend unconfirmed", **raw)
