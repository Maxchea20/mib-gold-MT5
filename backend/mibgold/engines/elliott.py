from .base import Engine
from .utils import zigzag, clamp
from ..contracts import Signal


class ElliottWaveEngine(Engine):
    """Heuristic impulse/correction counter. Deliberately LOW WEIGHT in consensus (subjective)."""
    key, name, min_bars = "elliott", "Elliott Wave", 100
    MAX_CONF = 0.6

    def _evaluate(self, df, ctx):
        zz = zigzag(df, k=4)
        if len(zz) < 6:
            return Signal.neutral("Fewer than 6 swings - no wave count")
        pts = zz[-6:]
        legs = [pts[i + 1][1] - pts[i][1] for i in range(5)]
        up_impulse = legs[0] > 0 and legs[2] > 0 and legs[4] > 0 and legs[1] < 0 and legs[3] < 0
        dn_impulse = legs[0] < 0 and legs[2] < 0 and legs[4] < 0 and legs[1] > 0 and legs[3] > 0
        raw = dict(legs=legs, points=[p[1] for p in pts])
        if not (up_impulse or dn_impulse):
            return Signal.neutral("Swing sequence not impulsive (no 5-3 alternation)", **raw)
        w1, w3, w5 = abs(legs[0]), abs(legs[2]), abs(legs[4])
        w3_ok = w3 >= min(w1, w5)
        overlap = (pts[4][1] < pts[1][1]) if up_impulse else (pts[4][1] > pts[1][1])
        if not w3_ok or overlap:
            return Signal.neutral("Wave-3 not dominant or wave-4 overlaps wave-1 - count invalid", **raw)
        # five waves complete -> expect ABC correction against the impulse
        d = "short" if up_impulse else "long"
        ext = w5 / max(w1, 1e-9)
        conf = clamp(0.35 + 0.15 * min(ext, 1.5) / 1.5, 0, self.MAX_CONF)
        return Signal(d, conf, f"5-wave {'up' if up_impulse else 'down'} impulse likely complete - expect corrective {d}", raw)
