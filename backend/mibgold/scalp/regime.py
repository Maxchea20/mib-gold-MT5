"""Observe-only gold regime. Does not fire or block."""
from __future__ import annotations
from typing import Dict, List


def _atr(rows: List[dict], n: int) -> float:
    if len(rows) < n + 1:
        return 0.0
    acc = 0.0
    for i in range(-n, 0):
        h, l, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        acc += tr
    return acc / n


def snapshot(m1: List[dict], n_mom: int = 5) -> Dict:
    if not m1 or len(m1) < 55:
        return {"volatility": "UNKNOWN", "atr_ratio": None}
    last = m1[-1]
    a14 = _atr(m1, 14)
    a50 = _atr(m1, 50)
    ratio = (a14 / a50) if a50 > 0 else 0.0
    if ratio < 0.75:
        vol = "COMPRESSED"
    elif ratio < 1.25:
        vol = "NORMAL"
    elif ratio < 1.75:
        vol = "EXPANDING"
    else:
        vol = "EXTREME"
    rng = last["high"] - last["low"]
    rng_atr = (rng / a14) if a14 > 0 else 0.0
    vols = [float(r.get("volume") or r.get("tick_volume") or 0) for r in m1[-21:-1]]
    med = sorted(vols)[len(vols) // 2] if vols else 0.0
    cur_v = float(last.get("volume") or last.get("tick_volume") or 0)
    rvol = (cur_v / med) if med > 0 else None
    prev = m1[-1 - n_mom] if len(m1) > n_mom else m1[0]
    mom = ((last["close"] - prev["close"]) / a14) if a14 > 0 else 0.0
    return {
        "volatility": vol,
        "atr14": round(a14, 4),
        "atr50": round(a50, 4),
        "atr_ratio": round(ratio, 4),
        "range_atr": round(rng_atr, 4),
        "relative_volume": None if rvol is None else round(rvol, 3),
        "momentum_atr": round(mom, 4),
    }
