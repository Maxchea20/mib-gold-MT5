"""Same-side tape check. Veto only if an engine is hard against the hunt side."""
from __future__ import annotations
from typing import Dict, Optional, Tuple
import pandas as pd
from ..engines.utils import ema, rsi

NEED = ("trend", "momentum", "volume")


def _macd_side(df: pd.DataFrame) -> Tuple[str, float]:
    if df is None or len(df) < 35:
        return "neutral", 0.0
    c = df["close"].to_numpy()
    line = ema(c, 12) - ema(c, 26)
    sig = ema(line, 9)
    hist = float(line[-1] - sig[-1])
    if hist > 0:
        return "long", hist
    if hist < 0:
        return "short", hist
    return "neutral", 0.0


def tape_ok(direction: str, votes: Dict, m5: Optional[pd.DataFrame]) -> Tuple[bool, str]:
    side = (direction or "").lower()
    if side not in ("long", "short"):
        return False, "tape: no side"
    notes = []
    for key in NEED:
        v = (votes or {}).get(key) or {}
        sig = (v.get("signal") or "neutral").lower()
        reason = v.get("reason") or key
        notes.append(f"{key}={sig}")
        if sig in ("long", "short") and sig != side:
            return False, f"tape: {key} {sig} vs hunt {side} | {reason}"
    macd_side, hist = _macd_side(m5)
    notes.append(f"macd={macd_side} hist={hist:+.3f}")
    if macd_side in ("long", "short") and macd_side != side:
        return False, f"tape: MACD {macd_side} vs hunt {side} hist={hist:+.3f}"
    if m5 is not None and len(m5) >= 20:
        r = float(rsi(m5["close"].to_numpy(), 14)[-1])
        notes.append(f"rsi={r:.0f}")
        if side == "short" and r <= 22:
            return False, f"tape: RSI {r:.0f} oversold fade risk vs short"
        if side == "long" and r >= 78:
            return False, f"tape: RSI {r:.0f} overbought fade risk vs long"
    return True, "tape ok " + " ".join(notes)
