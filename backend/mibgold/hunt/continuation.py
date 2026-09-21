"""M5 continuation. Not C-Fast.

H1+M5 trend same side, MACD same side, RSI not a fade extreme,
volume not against. Enter the last M5 LH (short) or HL (long).
No 15m tap. No slot-3 impulse at the low.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from ..engines.utils import ema, rsi

LONG, SHORT, NEUTRAL = "LONG", "SHORT", "NEUTRAL"


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


def _closes(rows: List[dict]):
    return [float(b["close"]) for b in rows]


def _macd_hist(closes: List[float]) -> float:
    if len(closes) < 35:
        return 0.0
    line = ema(closes, 12) - ema(closes, 26)
    sig = ema(line, 9)
    return float(line[-1] - sig[-1])


def _trend_side(rows: List[dict]) -> str:
    if len(rows) < 60:
        return NEUTRAL
    c = _closes(rows)
    e20, e50 = ema(c, 20), ema(c, 50)
    px = c[-1]
    slope = e20[-1] - e20[-6]
    if px < e20[-1] < e50[-1] and slope < 0:
        return SHORT
    if px > e20[-1] > e50[-1] and slope > 0:
        return LONG
    return NEUTRAL


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


def _wait(why: str) -> Dict:
    return {
        "action": "WAIT", "direction": "neutral", "entry_readiness": False,
        "why_state": [why], "blocking_reasons": [why],
        "brain_version": "M5_CONTINUATION",
        "hunt": {"armed": False, "m5_path": "wait"},
    }


def evaluate_continuation(
    candles_5m: List[dict],
    candles_1h: Optional[List[dict]] = None,
    candles_4h: Optional[List[dict]] = None,
    **_unused,
) -> Dict:
    m5 = candles_5m or []
    if len(m5) < 60:
        return _wait("Need 60 M5 bars for continuation.")
    h1_side = _trend_side(candles_1h or [])
    h4_side = _trend_side(candles_4h or [])
    m5_side = _trend_side(m5)
    if m5_side == NEUTRAL:
        return _wait(f"M5 no EMA stack. H1={h1_side} H4={h4_side}")
    if h1_side not in (NEUTRAL, m5_side):
        return _wait(f"H1 {h1_side} vs M5 {m5_side} - no fade.")
    if h4_side not in (NEUTRAL, m5_side):
        return _wait(f"H4 {h4_side} vs M5 {m5_side} - no fade.")

    closes = _closes(m5)
    hist = _macd_hist(closes)
    r = float(rsi(closes, 14)[-1])
    if m5_side == SHORT and hist > 0:
        return _wait(f"MACD hist {hist:+.3f} against short. RSI {r:.0f}")
    if m5_side == LONG and hist < 0:
        return _wait(f"MACD hist {hist:+.3f} against long. RSI {r:.0f}")
    if m5_side == SHORT and r <= 22:
        return _wait(f"RSI {r:.0f} oversold - no short into bounce.")
    if m5_side == LONG and r >= 78:
        return _wait(f"RSI {r:.0f} overbought - no long into fade.")

    last = m5[-1]
    vol = float(last.get("volume") or 0)
    avg_vol = sum(float(b.get("volume") or 0) for b in m5[-21:-1]) / 20 if len(m5) > 21 else vol
    down_bar = float(last["close"]) < float(last["open"])
    up_bar = float(last["close"]) > float(last["open"])
    if avg_vol > 0 and vol > avg_vol * 1.2:
        if m5_side == SHORT and up_bar:
            return _wait("Volume spike on up bar vs short.")
        if m5_side == LONG and down_bar:
            return _wait("Volume spike on down bar vs long.")

    highs, lows = _swings(m5, k=2)
    atr5 = _atr(m5)
    if m5_side == SHORT:
        if len(highs) < 2:
            return _wait("No M5 swing high for LH yet.")
        last_h, prev_h = highs[-1], highs[-2]
        if float(last_h["high"]) >= float(prev_h["high"]):
            return _wait(f"Last M5 high {float(last_h['high']):.2f} is not LH.")
        lvl = float(last_h["high"])
        # live must still be near that LH, not 8 points under it
        live = float(last["close"])
        if live < lvl - max(1.2, 0.6 * atr5):
            return _wait(f"Price {live:.2f} already left LH {lvl:.2f} - no chase low.")
        entry = lvl
        direction = "short"
        path = "M5_LH"
    else:
        if len(lows) < 2:
            return _wait("No M5 swing low for HL yet.")
        last_l, prev_l = lows[-1], lows[-2]
        if float(last_l["low"]) <= float(prev_l["low"]):
            return _wait(f"Last M5 low {float(last_l['low']):.2f} is not HL.")
        lvl = float(last_l["low"])
        live = float(last["close"])
        if live > lvl + max(1.2, 0.6 * atr5):
            return _wait(f"Price {live:.2f} already left HL {lvl:.2f} - no chase high.")
        entry = lvl
        direction = "long"
        path = "M5_HL"

    return {
        "action": "FIRE",
        "direction": direction,
        "entry": entry,
        "atr_15m": atr5,
        "atr_5m": atr5,
        "event": path,
        "armed": True,
        "brain_version": "M5_CONTINUATION",
        "why_state": [
            "M5 continuation",
            f"H4={h4_side} H1={h1_side} M5={m5_side}",
            f"MACD {hist:+.3f} RSI {r:.0f}",
            path,
        ],
        "blocking_reasons": [],
        "hunt": {"armed": True, "level": entry, "m5_path": path, "side": m5_side, "event": path},
    }
