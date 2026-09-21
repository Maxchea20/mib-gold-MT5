"""LIQ-JOIN on 3-minute close-through. M3 is built from completed M1 only."""
from __future__ import annotations
from typing import Callable, Dict, List, Optional
from .liq_join import LiqJoinEngine, LiqConfig
from . import core
from . import hunt_tp_bind
from .regime import snapshot


def m3_from_m1(m1: List[dict]) -> List[dict]:
    if not m1:
        return []
    out = []
    bucket = None
    o = h = l = c = ts0 = None
    for r in m1:
        ts = int(r["ts"])
        b = ts - (ts % 180)
        if bucket is None:
            bucket, ts0, o, h, l, c = b, ts, r["open"], r["high"], r["low"], r["close"]
            continue
        if b != bucket:
            out.append({"ts": ts0, "open": o, "high": h, "low": l, "close": c})
            bucket, ts0, o, h, l, c = b, ts, r["open"], r["high"], r["low"], r["close"]
        else:
            if r["high"] > h:
                h = r["high"]
            if r["low"] < l:
                l = r["low"]
            c = r["close"]
    if bucket is not None:
        last_min = (int(m1[-1]["ts"]) // 60) % 3
        if last_min == 2:
            out.append({"ts": ts0, "open": o, "high": h, "low": l, "close": c})
    return out


class LiqJoinM3(LiqJoinEngine):
    def __init__(self, cfg: Optional[LiqConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "LIQ_JOIN_M3"

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        m1 = frames.get("M1")
        rows = m1 if isinstance(m1, list) else core.rows(m1) if m1 is not None else []
        m3 = m3_from_m1(rows)
        framed = dict(frames)
        framed["M5"] = m3
        d = super().evaluate(framed, now, spread)
        reg = snapshot(rows)
        d["market_regime"] = reg
        d["vol_bucket"] = reg.get("volatility") or d.get("vol_bucket")
        if d.get("fire"):
            meta = dict(d.get("meta") or {})
            meta["market_regime"] = reg
            meta["location_type"] = meta.get("location_type") or "15M_POOL"
            d["meta"] = meta
        return d
