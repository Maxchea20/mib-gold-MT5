"""Desktop Hunt V2 for gold. Pullback fill only.

Fresh 15m CHoCH/BOS arms.
Fill = FVG or the broken event price — never the live LL/HH.
M5 must tag and hold. Close-through / breakout print is WAIT.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from .weather import classify, side_allowed

LONG, SHORT, NEUTRAL = "LONG", "SHORT", "NEUTRAL"
SL_ATR, TP_ATR, BAND = 1.5, 2.5, 0.25
HUNT_VERSION_C_FAST = "OBSERVATION_HUNT_M5_V2"


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


def _fvgs(rows: List[dict]) -> List[Tuple[str, float]]:
    out = []
    for i in range(2, len(rows)):
        a, c = rows[i - 2], rows[i]
        if float(a["high"]) < float(c["low"]):
            out.append((LONG, (float(a["high"]) + float(c["low"])) / 2.0))
        if float(a["low"]) > float(c["high"]):
            out.append((SHORT, (float(a["low"]) + float(c["high"])) / 2.0))
    return out[-12:]


def _vol_ok(rows: List[dict], side: str) -> bool:
    if len(rows) < 20:
        return True
    last = rows[-1]
    vol = float(last.get("volume") or 0)
    avg = sum(float(b.get("volume") or 0) for b in rows[-21:-1]) / 20.0
    up = float(last["close"]) > float(last["open"])
    if avg <= 0:
        return True
    if vol > avg * 1.3 and side == SHORT and up:
        return False
    if vol > avg * 1.3 and side == LONG and not up:
        return False
    return True


def _fresh_trigger(rows: List[dict]) -> Dict:
    highs, lows = _swings(rows)
    if len(highs) < 2 or len(lows) < 2:
        return {"event": None, "side": None, "kind": None, "level": None, "extended": False}
    last_h, prev_h = highs[-1], highs[-2]
    last_l, prev_l = lows[-1], lows[-2]
    close = float(rows[-1]["close"])
    bos_up = close > float(last_h["high"]) and float(last_h["high"]) > float(prev_h["high"])
    bos_dn = close < float(last_l["low"]) and float(last_l["low"]) < float(prev_l["low"])
    choch_up = close > float(last_h["high"]) and float(last_l["low"]) < float(prev_l["low"])
    choch_dn = close < float(last_l["low"]) and float(last_h["high"]) > float(prev_h["high"])
    hh_run = sum(1 for a, b in zip(highs[-3:], highs[-2:]) if float(b["high"]) > float(a["high"]))
    if choch_up:
        return {"event": "CHoCH", "side": LONG, "kind": "structure", "level": float(last_h["high"]), "extended": False}
    if choch_dn:
        return {"event": "CHoCH", "side": SHORT, "kind": "structure", "level": float(last_l["low"]), "extended": False}
    if bos_up:
        return {"event": "BOS", "side": LONG, "kind": "structure", "level": float(last_h["high"]), "extended": hh_run >= 2}
    if bos_dn:
        return {"event": "BOS", "side": SHORT, "kind": "structure", "level": float(last_l["low"]), "extended": False}
    return {"event": None, "side": None, "kind": None, "level": None, "extended": False}


def _pick_level(side: str, price: float, atr15: float, rows: List[dict], fallback: float) -> float:
    """FVG on the side, else the broken event price. Never the live extreme."""
    cap = max(atr15, 0.5)
    cands = [px for s, px in _fvgs(rows) if s == side and abs(px - price) <= cap]
    if cands:
        return min(cands, key=lambda x: abs(x - price))
    return float(fallback)


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
    if not candles_15m or len(candles_15m) < 40 or not candle_5m:
        return _wait("Need more 15m/5m candles.")
    atr15 = _atr(candles_15m)
    if atr15 <= 0:
        return _wait("Invalid 15m ATR.")
    wx = classify(candles_4h or [], candles_1h) if candles_4h else None
    tr = _fresh_trigger(candles_15m)
    event, side = tr.get("event"), tr.get("side")
    if not event or side not in (LONG, SHORT):
        return _wait("No fresh 15m CHoCH/BOS. Waiting pullback, not the break print.")
    if tr.get("extended"):
        return _wait("15m BOS is extended continuation. Skip.")
    if wx and not side_allowed(wx.get("flag"), side) and event != "CHoCH":
        return _wait(f"4h trend {wx.get('flag')} opposes 15m {event}.")
    if not _vol_ok(candles_15m, side):
        return _wait("Volume contradicts 15m trigger.")
    price = float(candles_15m[-1]["close"])
    level = _pick_level(side, price, atr15, candles_15m, float(tr.get("level") or price))
    band = BAND * atr15
    hi, lo, c = float(candle_5m["high"]), float(candle_5m["low"]), float(candle_5m["close"])
    tagged = (side == LONG and lo <= level + band) or (side == SHORT and hi >= level - band)
    through = (c - level) if side == LONG else (level - c)
    on_side = (side == LONG and c >= level) or (side == SHORT and c <= level)
    near = abs(c - level) <= band
    if through > band:
        return _wait("M5 already through the level. Late. No chase.")
    if not tagged:
        return _wait(f"Waiting M5 pullback to {level:.2f}.")
    if not (on_side and near):
        return _wait("M5 tagged but did not hold.")
    if side == LONG:
        stop, target = level - SL_ATR * atr15, level + TP_ATR * atr15
    else:
        stop, target = level + SL_ATR * atr15, level - TP_ATR * atr15
    return {
        "action": "FIRE",
        "direction": side.lower(),
        "entry": level,
        "stop": stop,
        "target": target,
        "atr_15m": atr15,
        "event": event,
        "armed": True,
        "weather_flag": (wx or {}).get("flag"),
        "brain_version": HUNT_VERSION_C_FAST,
        "why_state": [f"15m {event}", f"pullback {level:.2f}", "M5 held"],
        "blocking_reasons": [],
        "hunt": {"armed": True, "level": level, "m5_path": "clean", "side": side, "event": event},
    }


def frames_to_candles(df) -> List[dict]:
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for t, o, h, l, c, v in zip(df["time"], df["open"], df["high"], df["low"], df["close"], df.get("tick_volume", df["close"])):
        ts = int(t.timestamp()) if hasattr(t, "timestamp") else int(t)
        out.append({"ts": ts, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
    return out
