"""Point-in-time location helpers. Bar timestamps are UTC after MT5 offset."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .config import ASIA, LONDON, NY

Candle = Dict
PREV_DAY_NOTE = "PDH/PDL = high/low of the last completed daily bar (UTC after MT5_SERVER_UTC_OFFSET)."


def rows(df) -> List[Candle]:
    if df is None:
        return []
    if isinstance(df, list):
        return df
    if getattr(df, "empty", True):
        return []
    out = []
    for r in df.itertuples(index=False):
        t = r.time
        ts = int(t.timestamp()) if hasattr(t, "timestamp") else int(t)
        vol = float(getattr(r, "tick_volume", 0) or getattr(r, "volume", 0) or 0)
        out.append({
            "ts": ts, "time": t,
            "open": float(r.open), "high": float(r.high),
            "low": float(r.low), "close": float(r.close), "vol": vol,
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
    if 12 <= hour < 16:
        return "LONDON_NY"
    if LONDON[0] <= hour < 12:
        return "LONDON"
    if NY[0] <= hour < NY[1]:
        return "NEW_YORK"
    if hour >= 21:
        return "LATE_NY"
    return "ASIA"


def vol_bucket(ratio: float) -> str:
    if ratio < 0.70:
        return "LOW"
    if ratio < 1.30:
        return "NORMAL"
    if ratio < 2.00:
        return "EXPANSION"
    return "EXTREME"


def _utc(ts: int) -> datetime:
    return datetime.utcfromtimestamp(int(ts))


def session_hl(cs: List[Candle], now_ts: int, start_h: int, end_h: int) -> Optional[Dict]:
    now = _utc(now_ts)
    past = [c for c in cs if c["ts"] < now_ts]
    if not past:
        return None

    def in_sess(c):
        return start_h <= _utc(c["ts"]).hour < end_h

    today = [c for c in past if _utc(c["ts"]).date() == now.date() and in_sess(c)]
    if today:
        return {"high": max(c["high"] for c in today), "low": min(c["low"] for c in today)}
    yday = now.date() - timedelta(days=1)
    prev = [c for c in past if _utc(c["ts"]).date() == yday and in_sess(c)]
    if prev:
        return {"high": max(c["high"] for c in prev), "low": min(c["low"] for c in prev)}
    return None


def session_vwap(cs: List[Candle], now_ts: int) -> Optional[float]:
    now = _utc(now_ts)
    bars = [c for c in cs if c["ts"] < now_ts and _utc(c["ts"]).date() == now.date()]
    den = sum(c["vol"] for c in bars)
    if den <= 0:
        return None
    num = sum(((c["high"] + c["low"] + c["close"]) / 3.0) * c["vol"] for c in bars)
    return num / den


def locations(m15, d1, m5, m1=None, k: int = 2, now_ts: Optional[int] = None) -> List[Dict]:
    out = []
    if d1:
        prev = d1[-1]
        out.append({"name": "PDH", "side": "res", "price": prev["high"]})
        out.append({"name": "PDL", "side": "sup", "price": prev["low"]})
    if m1:
        ts = now_ts or m1[-1]["ts"]
        asia = session_hl(m1, ts, ASIA[0], ASIA[1])
        lon = session_hl(m1, ts, LONDON[0], LONDON[1])
        if asia:
            out.append({"name": "ASIA_H", "side": "res", "price": asia["high"]})
            out.append({"name": "ASIA_L", "side": "sup", "price": asia["low"]})
        if lon:
            out.append({"name": "LONDON_H", "side": "res", "price": lon["high"]})
            out.append({"name": "LONDON_L", "side": "sup", "price": lon["low"]})
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
