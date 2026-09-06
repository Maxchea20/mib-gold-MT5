from .base import Engine
from .utils import safe_atr, clamp
from ..contracts import Signal


class FVGEngine(Engine):
    """3-candle imbalance, ATR-gated; gap value expressed per lot using gold contract size."""
    key, name, min_bars = "fvg", "Fair Value Gap", 40
    GATE_ATR = 1.0

    def _evaluate(self, df, ctx):
        a = safe_atr(df)
        h, l, o, c = (df[k].to_numpy() for k in ("high", "low", "open", "close"))
        price = float(c[-1])
        gaps = []
        for i in range(len(df) - 2, max(len(df) - 40, 2), -1):
            disp = abs(c[i - 1] - o[i - 1]) / a  # middle candle displacement
            if disp < self.GATE_ATR:
                continue
            if l[i] > h[i - 2]:  # bullish gap between candle i-2 high and candle i low
                lo, hi = h[i - 2], l[i]
                if l[i + 1:].min() < lo if i + 1 < len(df) else False:
                    continue  # already filled
                gaps.append(("long", lo, hi, i, disp))
            elif h[i] < l[i - 2]:
                lo, hi = h[i], l[i - 2]
                if h[i + 1:].max() > hi if i + 1 < len(df) else False:
                    continue
                gaps.append(("short", lo, hi, i, disp))
        if not gaps:
            return Signal.neutral(f"No unfilled FVG (>= {self.GATE_ATR:.1f} ATR displacement) in last 40 bars")
        d, lo, hi, idx, disp = gaps[0]
        gap_usd_lot = (hi - lo) * ctx.contract_size
        raw = dict(zone_low=lo, zone_high=hi, displacement_atr=disp, gap_usd_per_lot=gap_usd_lot, open_gaps=len(gaps))
        inside = lo <= price <= hi
        near = abs(price - (hi if d == "long" else lo)) <= a * 0.5
        if inside or near:
            conf = clamp(0.4 + 0.2 * min(disp, 2.5) / 2.5 + (0.15 if inside else 0.05))
            return Signal(d, conf, f"{'Bullish' if d=='long' else 'Bearish'} FVG {lo:.2f}-{hi:.2f} being {'tapped' if inside else 'approached'} ({disp:.1f} ATR disp, ${gap_usd_lot:.0f}/lot)", raw)
        return Signal.neutral(f"Open {d} FVG {lo:.2f}-{hi:.2f} not yet reached", **raw)
