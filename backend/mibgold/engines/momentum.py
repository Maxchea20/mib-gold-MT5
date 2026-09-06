from .base import Engine
from .utils import rsi, clamp
from ..contracts import Signal

# Asian session prints muted RSI excursions; scale deviations from 50 so thresholds stay comparable.
SESSION_GAIN = {"asian": 1.4, "london": 1.0, "ny_overlap": 0.9, "ny": 1.0, "off": 1.2}


class MomentumEngine(Engine):
    key, name, min_bars = "momentum", "Momentum", 40

    def _evaluate(self, df, ctx):
        r = rsi(df["close"].to_numpy(), 14)
        gain = SESSION_GAIN.get(ctx.session, 1.0)
        raw_now, raw_prev = float(r[-1]), float(r[-4])
        adj = 50 + (raw_now - 50) * gain
        adj_prev = 50 + (raw_prev - 50) * gain
        rising = adj > adj_prev
        raw = dict(rsi=raw_now, rsi_adj=adj, session_gain=gain, rising=rising)
        if adj >= 78:
            return Signal("short", clamp(0.3 + (adj - 78) / 40), f"RSI {raw_now:.0f} (adj {adj:.0f}) overbought - fade risk", raw)
        if adj <= 22:
            return Signal("long", clamp(0.3 + (22 - adj) / 40), f"RSI {raw_now:.0f} (adj {adj:.0f}) oversold - bounce risk", raw)
        if adj > 55 and rising:
            return Signal("long", clamp(0.3 + (adj - 55) / 40), f"RSI {raw_now:.0f} rising (session-adj {adj:.0f}) - bullish momentum", raw)
        if adj < 45 and not rising:
            return Signal("short", clamp(0.3 + (45 - adj) / 40), f"RSI {raw_now:.0f} falling (session-adj {adj:.0f}) - bearish momentum", raw)
        return Signal.neutral(f"RSI {raw_now:.0f} (adj {adj:.0f}) in neutral band", **raw)
