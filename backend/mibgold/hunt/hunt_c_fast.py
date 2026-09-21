"""Hunt C for MIB Gold.

Glue = the swing that was BROKEN (BOS/CHoCH price), not the latest LL/HH.
Short waits for a retest of that broken low from above.
Long waits for a retest of that broken high from below.
A new close-through moves glue to that new broken swing.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from .weather import classify, side_allowed

LONG, SHORT, NEUTRAL = "LONG", "SHORT", "NEUTRAL"
SL_ATR, TP_ATR = 1.5, 2.5
HUNT_VERSION_C_FAST = "OBSERVATION_HUNT_M5_C"


def parent_open(ts5: int) -> int:
    return int(ts5) - (int(ts5) % 900)


def slot_of(ts5: int) -> int:
    return int(((int(ts5) % 900) // 300) + 1)


def _atr(rows: List[dict], n: int = 14) -> float:
    if len(rows) < n + 1:
        return 0.0
    prev = None
    acc = k = 0.0
    for b in rows[-(n + 1):][1:]:
        tr = float(b["high"]) - float(b["low"])
        if prev is not None:
            tr = max(tr, abs(float(b["high"]) - prev), abs(float(b["low"]) - prev))
        acc += tr
        k += 1
        prev = float(b["close"])
    return acc / k if k else 0.0


def _swings(rows: List[dict], k: int = 2):
    highs, lows = [], []
    for i in range(k, len(rows) - k):
        w = rows[i - k:i + k + 1]
        p = rows[i]
        if all(float(p["high"]) >= float(x["high"]) for x in w):
            highs.append(p)
        if all(float(p["low"]) <= float(x["low"]) for x in w):
            lows.append(p)
    return highs, lows


def _ts(b: dict) -> int:
    return int(b.get("ts") or b.get("time") or 0)


def _structure(rows: List[dict]) -> Dict:
    highs, lows = _swings(rows)
    empty = {"event": None, "side": None, "extended": False, "level": None}
    if len(highs) < 2 or len(lows) < 2:
        return empty
    breaks = []
    for sl in lows:
        lvl, ts0 = float(sl["low"]), _ts(sl)
        for b in rows:
            if _ts(b) <= ts0:
                continue
            if float(b["close"]) < lvl:
                breaks.append(("SHORT", lvl, _ts(b)))
                break
    for sh in highs:
        lvl, ts0 = float(sh["high"]), _ts(sh)
        for b in rows:
            if _ts(b) <= ts0:
                continue
            if float(b["close"]) > lvl:
                breaks.append(("LONG", lvl, _ts(b)))
                break
    if not breaks:
        return empty
    breaks.sort(key=lambda x: x[2])
    side, level, _ = breaks[-1]
    prev_side = breaks[-2][0] if len(breaks) >= 2 else None
    event = "CHoCH" if prev_side and prev_side != side else "BOS"
    same = 0
    for s, _, _ in reversed(breaks):
        if s != side:
            break
        same += 1
    extended = same >= 3
    return {"event": event, "side": side, "extended": extended, "level": float(level)}


def structure_ok_fast(st: Dict) -> bool:
    ev = (st.get("event") or "").upper()
    if ev in ("CHOCH", "CHoCH"):
        return True
    if ev == "BOS" and not st.get("extended"):
        return True
    return False


def _wait(why: str, extra: Optional[Dict] = None) -> Dict:
    out = {
        "action": "WAIT", "direction": NEUTRAL, "entry_readiness": False,
        "why_state": [why], "blocking_reasons": [why],
        "brain_version": HUNT_VERSION_C_FAST,
        "hunt": {"armed": False, "m5_path": "waiting"},
    }
    if extra:
        out.update(extra)
        if extra.get("entry") is not None:
            out["entry"] = extra["entry"]
            out["direction"] = extra.get("direction") or out["direction"]
            out["hunt"] = {"armed": bool(extra.get("armed")), "level": extra["entry"],
                           "m5_path": "waiting", "event": extra.get("event")}
    return out


def evaluate_hunt_c_fast(
    candles_15m: List[dict],
    candle_5m: dict,
    live_5ms: Optional[List[dict]] = None,
    candles_4h: Optional[List[dict]] = None,
    candles_1h: Optional[List[dict]] = None,
    candles_5m: Optional[List[dict]] = None,
) -> Dict:
    if not candles_15m or len(candles_15m) < 30 or not candle_5m:
        return _wait("Need more candles before Hunt C can look.")
    live = live_5ms or [candle_5m]
    ts = int(candle_5m["ts"])
    slot = len(live) if live else slot_of(ts)
    wx = classify(candles_4h or [], candles_1h) if candles_4h else None
    st = _structure(candles_15m)
    event, side, level = st.get("event"), st.get("side"), st.get("level")
    atr15 = _atr(candles_15m)
    glue_extra = {
        "event": event, "weather_flag": (wx or {}).get("flag"), "slot": slot,
        "entry": float(level or 0), "direction": (side or "").lower(),
    }
    if not structure_ok_fast(st):
        return _wait(
            f"This 15-minute move is only a {event or 'poke'}, not a CHoCH or first break of structure. Skip.",
            extra={**glue_extra, "armed": False},
        )
    if side not in (LONG, SHORT):
        return _wait("Setup has no long or short side. Sitting out.", extra=glue_extra)
    if wx and not side_allowed(wx.get("flag"), side):
        way = "long" if side == LONG else "short"
        return _wait(f"4-hour weather is {wx.get('flag')}, so no {way} trade now.",
                     extra={**glue_extra, "armed": True})
    prior = candles_15m[-2] if len(candles_15m) >= 2 else candles_15m[-1]
    prior_high, prior_low = float(prior["high"]), float(prior["low"])
    c = float(candle_5m["close"])
    hi, lo = float(candle_5m["high"]), float(candle_5m["low"])
    lvl = float(level or (prior_high if side == LONG else prior_low))
    path = None
    if slot == 3:
        if side == LONG and c > prior_high:
            path = "impulse_3"
        elif side == SHORT and c < prior_low:
            path = "impulse_3"
        else:
            return _wait(
                f"Waiting retest of broken {event} {lvl:.2f}.",
                extra={**glue_extra, "armed": True, "entry": lvl},
            )
    else:
        band = 0.25 * atr15 if atr15 else 0.4
        tagged = (side == LONG and lo <= lvl + band) or (side == SHORT and hi >= lvl - band)
        if not tagged:
            return _wait(
                f"Waiting retest of broken {event} {lvl:.2f} ({side}).",
                extra={**glue_extra, "armed": True, "entry": lvl},
            )
        path = "v2_clean"
    if side == LONG:
        stop, target = lvl - SL_ATR * atr15, lvl + TP_ATR * atr15
    else:
        stop, target = lvl + SL_ATR * atr15, lvl - TP_ATR * atr15
    return {
        "action": "FIRE",
        "direction": side.lower(),
        "entry": lvl,
        "stop": stop,
        "target": target,
        "atr_15m": atr15,
        "event": event,
        "slot": slot,
        "armed": True,
        "weather_flag": (wx or {}).get("flag"),
        "brain_version": HUNT_VERSION_C_FAST,
        "why_state": ["Hunt C", f"15m {event}", path, f"retest {lvl:.2f}"],
        "blocking_reasons": [],
        "hunt": {"armed": True, "level": lvl, "m5_path": path, "side": side, "event": event, "slot": slot},
    }


def frames_to_candles(df) -> List[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for t, o, h, l, c, v in zip(df["time"], df["open"], df["high"], df["low"], df["close"], df.get("tick_volume", df["close"])):
        ts = int(t.timestamp()) if hasattr(t, "timestamp") else int(t)
        out.append({"ts": ts, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
    return out
