from .base import Engine
from .utils import zigzag, safe_atr, clamp
from ..contracts import Signal


class MarketStructureEngine(Engine):
    """Swing HH/HL/LH/LL tracking with break-of-structure detection."""
    key, name, min_bars = "structure", "Market Structure", 60

    def _evaluate(self, df, ctx):
        zz = zigzag(df, k=3)
        if len(zz) < 4:
            return Signal.neutral("Not enough swings to label structure")
        highs = [p for p in zz if p[2] == "H"][-3:]
        lows = [p for p in zz if p[2] == "L"][-3:]
        labels = []
        if len(highs) >= 2:
            labels.append("HH" if highs[-1][1] > highs[-2][1] else "LH")
        if len(lows) >= 2:
            labels.append("HL" if lows[-1][1] > lows[-2][1] else "LL")
        price = float(df["close"].iloc[-1])
        a = safe_atr(df)
        bull = labels.count("HH") + labels.count("HL")
        bear = labels.count("LH") + labels.count("LL")
        bos_up = price > highs[-1][1] if highs else False
        bos_dn = price < lows[-1][1] if lows else False
        raw = dict(labels=labels, last_high=highs[-1][1] if highs else None,
                   last_low=lows[-1][1] if lows else None, bos_up=bos_up, bos_dn=bos_dn)
        if bull == 2 or (bull == 1 and bos_up):
            conf = clamp(0.45 + 0.15 * bull + (0.2 if bos_up else 0))
            tag = "BOS up" if bos_up else "/".join(labels)
            return Signal("long", conf, f"Bullish structure ({tag}); last HL {lows[-1][1]:.2f}", raw)
        if bear == 2 or (bear == 1 and bos_dn):
            conf = clamp(0.45 + 0.15 * bear + (0.2 if bos_dn else 0))
            tag = "BOS down" if bos_dn else "/".join(labels)
            return Signal("short", conf, f"Bearish structure ({tag}); last LH {highs[-1][1]:.2f}", raw)
        rng = (highs[-1][1] - lows[-1][1]) / a if highs and lows else 0
        return Signal.neutral(f"Mixed swings {'/'.join(labels)} - ranging ({rng:.1f} ATR box)", **raw)
