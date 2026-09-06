from .base import Engine
from .utils import safe_atr, clamp, zigzag
from ..contracts import Signal


class PatternEngine(Engine):
    """Candlestick + simple chart patterns (engulfing, pin bar, inside-bar break, double top/bottom)."""
    key, name, min_bars = "pattern", "Pattern Recognition", 60

    def _evaluate(self, df, ctx):
        a = safe_atr(df)
        o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
        found = []
        body = abs(c[-1] - o[-1])
        rng = h[-1] - l[-1] + 1e-9
        upper = h[-1] - max(o[-1], c[-1])
        lower = min(o[-1], c[-1]) - l[-1]
        # engulfing
        if c[-1] > o[-1] and c[-2] < o[-2] and c[-1] > o[-2] and o[-1] < c[-2] and body > a * 0.5:
            found.append(("long", 0.55, "Bullish engulfing"))
        if c[-1] < o[-1] and c[-2] > o[-2] and c[-1] < o[-2] and o[-1] > c[-2] and body > a * 0.5:
            found.append(("short", 0.55, "Bearish engulfing"))
        # pin bars
        if lower > rng * 0.6 and body < rng * 0.3 and rng > a * 0.8:
            found.append(("long", 0.5, "Bullish pin bar"))
        if upper > rng * 0.6 and body < rng * 0.3 and rng > a * 0.8:
            found.append(("short", 0.5, "Bearish pin bar"))
        # inside bar breakout
        if h[-2] <= h[-3] and l[-2] >= l[-3]:
            if c[-1] > h[-3]:
                found.append(("long", 0.45, "Inside-bar breakout up"))
            elif c[-1] < l[-3]:
                found.append(("short", 0.45, "Inside-bar breakdown"))
        # double top / bottom from swings
        zz = zigzag(df, k=3)
        hs = [p for p in zz if p[2] == "H"][-2:]
        ls = [p for p in zz if p[2] == "L"][-2:]
        if len(hs) == 2 and abs(hs[0][1] - hs[1][1]) < a * 0.4 and c[-1] < hs[1][1] - a * 0.5 and len(df) - hs[1][0] < 12:
            found.append(("short", 0.5, f"Double top at {hs[1][1]:.2f}"))
        if len(ls) == 2 and abs(ls[0][1] - ls[1][1]) < a * 0.4 and c[-1] > ls[1][1] + a * 0.5 and len(df) - ls[1][0] < 12:
            found.append(("long", 0.5, f"Double bottom at {ls[1][1]:.2f}"))
        raw = dict(patterns=[f[2] for f in found])
        if not found:
            return Signal.neutral("No actionable candlestick/chart pattern", **raw)
        longs = [f for f in found if f[0] == "long"]
        shorts = [f for f in found if f[0] == "short"]
        if longs and shorts:
            return Signal.neutral("Conflicting patterns: " + ", ".join(f[2] for f in found), **raw)
        side = longs or shorts
        conf = clamp(max(f[1] for f in side) + 0.1 * (len(side) - 1))
        return Signal(side[0][0], conf, " + ".join(f[2] for f in side), raw)
