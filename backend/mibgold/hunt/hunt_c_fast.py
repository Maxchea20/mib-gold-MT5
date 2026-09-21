"""Hunt C-fast for MIB Gold.

Early door only:
  15m CHoCH or first BOS arms the hunt
  FIRE only when a 5m tap hits the 15m level
  Never fire on slot-3 close-through (that is the late impulse)
  4h weather must allow the side
  fill at the 15m level
"""
from __future__ import annotations
from typing import Dict, List, Optional
from .weather import classify, side_allowed

LONG, SHORT, NEUTRAL = "LONG", "SHORT", "NEUTRAL"
SL_ATR, TP_ATR = 1.5, 2.5
HUNT_VERSION_C_FAST = "OBSERVATION_HUNT_M5_C_FAST_EARLY"


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


def _structure(rows: List[dict]) -> Dict:
    highs, lows = _swings(rows)
    if len(highs) < 2 or len(lows) < 2:
        return {"event": None, "side": None, "extended": False, "level": None}
    last_h, prev_h = highs[-1], highs[-2]
    last_l, prev_l = lows[-1], lows[-2]
    close = float(rows[-1]["close"])
    bos_up = close > float(last_h["high"]) and float(last_h["high"]) > float(prev_h["high"])
    bos_dn = close < float(last_l["low"]) and float(last_l["low"]) < float(prev_l["low"])
    choch_up = close > float(last_h["high"]) and float(last_l["low"]) < float(prev_l["low"])
    choch_dn = close < float(last_l["low"]) and float(last_h["high"]) > float(prev_h["high"])
    hh_count = sum(1 for a, b in zip(highs[-3:], highs[-2:]) if float(b["high"]) > float(a["high"]))
    extended = hh_count >= 2 and bos_up
    if choch_up:
        return {"event": "CHoCH", "side": LONG, "extended": False, "level": float(last_h["high"])}
    if choch_dn:
        return {"event": "CHoCH", "side": SHORT, "extended": False, "level": float(last_l["low"])}
    if bos_up:
        return {"event": "BOS", "side": LONG, "extended": extended, "level": float(last_h["high"])}
    if bos_dn:
        return {"event": "BOS", "side": SHORT, "extended": False, "level": float(last_l["low"])}
    return {"event": None, "side": None, "extended": False, "level": float(rows[-2]["high"])}


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
    if not structure_ok_fast(st):
        return _wait(
            f"This 15-minute move is only a {event or 'poke'}, not a CHoCH or first break of structure. Skip.",
            extra={"event": event, "weather_flag": (wx or {}).get("flag"), "slot": slot, "armed": False},
        )
    if side not in (LONG, SHORT):
        return _wait("Setup has no long or short side. Sitting out.")
    if wx and not side_allowed(wx.get("flag"), side):
        way = "long" if side == LONG else "short"
        return _wait(f"4-hour weather is {wx.get('flag')}, so no {way} trade now.",
                     extra={"event": event, "weather_flag": wx.get("flag"), "slot": slot, "armed": True})
    prior = candles_15m[-2] if len(candles_15m) >= 2 else candles_15m[-1]
    prior_high, prior_low = float(prior["high"]), float(prior["low"])
    hi, lo = float(candle_5m["high"]), float(candle_5m["low"])
    lvl = float(level or (prior_high if side == LONG else prior_low))
    band = 0.25 * atr15 if atr15 else 0.4
    tagged = (side == LONG and lo <= lvl + band) or (side == SHORT and hi >= lvl - band)
    if not tagged:
        return _wait(
            f"Early hunt: waiting for tap of 15m level {lvl:.2f}. No impulse-3 chase.",
            extra={"event": event, "slot": slot, "armed": True, "weather_flag": (wx or {}).get("flag"),
                   "entry": lvl, "direction": side.lower()},
        )
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
        "why_state": ["Hunt C-fast EARLY", f"15m {event}", "v2_clean tap", "fill at 15m level"],
        "blocking_reasons": [],
        "hunt": {"armed": True, "level": lvl, "m5_path": "v2_clean", "side": side, "event": event, "slot": slot},
    }


def frames_to_candles(df) -> List[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for t, o, h, l, c, v in zip(df["time"], df["open"], df["high"], df["low"], df["close"], df.get("tick_volume", df["close"])):
        ts = int(t.timestamp()) if hasattr(t, "timestamp") else int(t)
        out.append({"ts": ts, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
    return out
