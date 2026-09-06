import numpy as np
from .base import Engine
from .utils import pivots, safe_atr, clamp
from ..contracts import Signal


class SupportResistanceEngine(Engine):
    """Key level clustering; gold mean-reverts hard at levels so we fade touches with rejection."""
    key, name, min_bars = "sr", "Support/Resistance", 80

    def _levels(self, df, a):
        pts = sorted(p[1] for p in pivots(df, k=4))
        clusters = []
        for p in pts:
            if clusters and abs(p - clusters[-1][-1]) <= a * 0.6:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return [(float(np.mean(c)), len(c)) for c in clusters if len(c) >= 2]

    def _evaluate(self, df, ctx):
        a = safe_atr(df)
        levels = self._levels(df, a)
        if not levels:
            return Signal.neutral("No clustered S/R levels in lookback")
        o, h, l, c = (float(df[k].iloc[-1]) for k in ("open", "high", "low", "close"))
        near = min(levels, key=lambda lv: abs(lv[0] - c))
        dist = (c - near[0]) / a
        strength = min(near[1], 5) / 5
        raw = dict(level=near[0], touches=near[1], dist_atr=dist, levels=[lv[0] for lv in levels][-8:])
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        body = abs(c - o) + 1e-9
        if abs(dist) <= 0.5 and l <= near[0] + a * 0.2 and c > o and lower_wick > body * 0.8:
            conf = clamp(0.4 + 0.3 * strength + 0.15 * min(lower_wick / a, 1))
            return Signal("long", conf, f"Rejection off support {near[0]:.2f} ({near[1]} touches)", raw)
        if abs(dist) <= 0.5 and h >= near[0] - a * 0.2 and c < o and upper_wick > body * 0.8:
            conf = clamp(0.4 + 0.3 * strength + 0.15 * min(upper_wick / a, 1))
            return Signal("short", conf, f"Rejection off resistance {near[0]:.2f} ({near[1]} touches)", raw)
        if dist > 0.3 and dist < 1.5:
            return Signal("long", clamp(0.25 + 0.2 * strength), f"Holding above level {near[0]:.2f} (+{dist:.1f} ATR)", raw)
        if dist < -0.3 and dist > -1.5:
            return Signal("short", clamp(0.25 + 0.2 * strength), f"Holding below level {near[0]:.2f} ({dist:.1f} ATR)", raw)
        return Signal.neutral(f"Nearest level {near[0]:.2f} at {dist:+.1f} ATR - no reaction", **raw)
