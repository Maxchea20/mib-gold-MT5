"""Deterministic bar helpers for Scalp V1. Closed candles only."""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .config import ASIA, LONDON, NY

Candle = Dict


def rows(df) -> List[Candle]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for _, r in df.iterrows():
        t = r["time"]
        ts = int(t.timestamp()) if hasattr(t, "timestamp") else int(t)
        out.append({
            "ts": ts, "time": t,
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "vol": float(r.get("tick_volume") or r.get("volume") or 0),
        })
    return out


def atr(cs: List[Candle], n: int = 14) -> float:
    if len(cs) < n + 1:
        return 0.0
    prev = None
    acc = k = 0.0
    for b in cs[-(n + 1):][1:]:
        tr = b["high"] - b["low"]
        if prev is not None:
            tr = max(tr, abs(b["high"] - prev), abs(b["low"] - prev))
        acc += tr
        k += 1
        prev = b["close"]
    return acc / k if k else 0.0


def rvol(cs: List[Candle], n: int = 20) -> float:
    if len(cs) < n + 1:
        return 1.0
    avg = sum(c["vol"] for c in cs[-(n + 1):-1]) / n
    if avg <= 0:
        return 1.0
    return cs[-1]["vol"] / avg


def swings(cs: List[Candle], k: int = 2):
    highs, lows = [], []
    for i in range(k, len(cs) - k):
        w = cs[i - k:i + k + 1]
        p = cs[i]
        if all(p["high"] >= x["high"] for x in w):
            highs.append(p)
        if all(p["low"] <= x["low"] for x in w):
            lows.append(p)
    return highs, lows


def last_swing_high(cs, k=2):
    h, _ = swings(cs, k)
    return h[-1] if h else None


def last_swing_low(cs, k=2):
    _, l = swings(cs, k)
    return l[-1] if l else None


def session_name(hour: int) -> str:
    if ASIA[0] <= hour < ASIA[1] and not (LONDON[0] <= hour < LONDON[1]):
        return "ASIA"
    if LONDON[0] <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NY"
    if NY[0] <= hour < NY[1]:
        return "NEW_YORK"
    if hour >= 21:
        return "LATE_NY"
    return "ASIA"


def locations(m15, d1, m5, k: int = 2):
    out = []
    if len(d1) >= 2:
        prev = d1[-2]
        out.append({"name": "PDH", "side": "res", "price": prev["high"]})
        out.append({"name": "PDL", "side": "sup", "price": prev["low"]})
    sh = last_swing_high(m15, k)
    sl = last_swing_low(m15, k)
    if sh:
        out.append({"name": "15M_SH", "side": "res", "price": sh["high"]})
    if sl:
        out.append({"name": "15M_SL", "side": "sup", "price": sl["low"]})
    sh5 = last_swing_high(m5, k)
    sl5 = last_swing_low(m5, k)
    if sh5:
        out.append({"name": "5M_SH", "side": "res", "price": sh5["high"]})
    if sl5:
        out.append({"name": "5M_SL", "side": "sup", "price": sl5["low"]})
    return out


def bos(cs, side: str, k: int = 2):
    if len(cs) < k * 2 + 3:
        return None
    last = cs[-1]
    if side == "long":
        sh = last_swing_high(cs[:-1], k)
        if sh and last["close"] > sh["high"]:
            return {"event": "BOS", "side": "long", "level": sh["high"]}
    else:
        sl = last_swing_low(cs[:-1], k)
        if sl and last["close"] < sl["low"]:
            return {"event": "BOS", "side": "short", "level": sl["low"]}
    return None
