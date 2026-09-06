import numpy as np
from .base import Engine
from .utils import clamp
from ..contracts import Signal


class VolumeEngine(Engine):
    """MT5 gives tick volume only - treated strictly as a tick-activity proxy, not real volume."""
    key, name, min_bars = "volume", "Volume (tick proxy)", 60

    def _evaluate(self, df, ctx):
        v = df["tick_volume"].to_numpy().astype(float)
        o, c = df["open"].to_numpy(), df["close"].to_numpy()
        base = v[-51:-1]
        mu, sd = base.mean(), base.std() + 1e-9
        z = float((v[-1] - mu) / sd)
        z3 = float((v[-3:].mean() - mu) / sd)
        up_vol = v[-10:][(c[-10:] > o[-10:])].sum()
        dn_vol = v[-10:][(c[-10:] < o[-10:])].sum()
        bias = (up_vol - dn_vol) / max(up_vol + dn_vol, 1e-9)
        raw = dict(tick_vol=v[-1], z=z, z3=z3, updown_bias=bias, note="tick activity proxy")
        bullish_bar = c[-1] > o[-1]
        if z > 1.0 and bullish_bar and bias > 0:
            return Signal("long", clamp(0.3 + 0.15 * min(z, 3) + 0.2 * bias), f"Tick activity {z:+.1f}σ on up bar, up/down bias {bias:+.2f}", raw)
        if z > 1.0 and not bullish_bar and bias < 0:
            return Signal("short", clamp(0.3 + 0.15 * min(z, 3) - 0.2 * bias), f"Tick activity {z:+.1f}σ on down bar, up/down bias {bias:+.2f}", raw)
        if z3 < -0.8:
            return Signal.neutral(f"Tick activity drying up ({z3:+.1f}σ) - low participation", **raw)
        if abs(bias) > 0.35:
            d = "long" if bias > 0 else "short"
            return Signal(d, clamp(0.2 + 0.3 * abs(bias)), f"Activity skew {bias:+.2f} favours {d}s (no spike)", raw)
        return Signal.neutral(f"Tick activity normal ({z:+.1f}σ), no skew", **raw)
