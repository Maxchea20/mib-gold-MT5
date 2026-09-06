from .base import Engine
from .utils import zigzag, safe_atr, clamp
from ..contracts import Signal

RETRACE = (0.382, 0.5, 0.618, 0.786)


class FibonacciEngine(Engine):
    """Retracement zone detection on the last completed swing; golden-pocket bias."""
    key, name, min_bars = "fibonacci", "Fibonacci", 60

    def _evaluate(self, df, ctx):
        zz = zigzag(df, k=3)
        if len(zz) < 2:
            return Signal.neutral("No swing to anchor Fibonacci")
        a = safe_atr(df)
        p1, p2 = zz[-2], zz[-1]
        price = float(df["close"].iloc[-1])
        swing = p2[1] - p1[1]
        if abs(swing) < a * 2:
            return Signal.neutral(f"Last swing too small ({abs(swing)/a:.1f} ATR) for fib zones")
        up_swing = swing > 0
        retr = (p2[1] - price) / swing if up_swing else (price - p2[1]) / -swing
        levels = {f"{r:.3f}": (p2[1] - swing * r) for r in RETRACE}
        raw = dict(swing_from=p1[1], swing_to=p2[1], retracement=retr, levels=levels, up_swing=up_swing)
        if 0.45 <= retr <= 0.72:
            d = "long" if up_swing else "short"
            conf = clamp(0.45 + 0.2 * (1 - abs(retr - 0.618) / 0.17))
            return Signal(d, conf, f"Price in golden pocket ({retr:.1%}) of {'up' if up_swing else 'down'} swing", raw)
        if 0.3 <= retr < 0.45:
            d = "long" if up_swing else "short"
            return Signal(d, clamp(0.3), f"Shallow retrace {retr:.1%} - {d} continuation possible", raw)
        if retr > 0.85:
            d = "short" if up_swing else "long"
            return Signal(d, clamp(0.3 + 0.2 * min(retr - 0.85, 0.3) / 0.3), f"Swing failing (retr {retr:.0%}) - {d} bias", raw)
        if retr < 0:
            return Signal.neutral(f"Price extending beyond swing ({retr:.0%}) - no retrace zone", **raw)
        return Signal.neutral(f"Retrace {retr:.0%} outside key fib zones", **raw)
