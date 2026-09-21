"""CONT-H1: H1 trend + M15 pullback + RSI washout + M1 close. Separate from V1."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional
from . import core


@dataclass
class ContConfig:
    h1_ema: int = 20
    rsi_n: int = 14
    rsi_long: float = 35.0
    rsi_short: float = 65.0
    m15_lookback: int = 4
    sl_buffer_atr_1m: float = 0.15
    min_sl_atr_1m: float = 0.35
    max_spread_points: float = 40.0
    cooldown_sec: int = 1800
    london: tuple = (7, 12)
    ny: tuple = (16, 21)
    frozen: bool = True
    version: str = "CONT_H1"


def _hour(ts: int) -> int:
    return datetime.utcfromtimestamp(int(ts)).hour


def _cs(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return core.rows(x)


def _rsi(cs: List[dict], n: int = 14) -> Optional[float]:
    if len(cs) < n + 2:
        return None
    gains = losses = 0.0
    prev = cs[-(n + 1)]["close"]
    for b in cs[-n:]:
        d = b["close"] - prev
        if d >= 0:
            gains += d
        else:
            losses -= d
        prev = b["close"]
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - 100.0 / (1.0 + rs)


def _ema_last(cs: List[dict], n: int) -> Optional[float]:
    if len(cs) < n:
        return None
    k = 2.0 / (n + 1)
    e = cs[0]["close"]
    for b in cs[1:]:
        e = b["close"] * k + e * (1 - k)
    return e


class ContEngine:
    def __init__(self, cfg: Optional[ContConfig] = None, log: Optional[Callable[[str], None]] = None):
        self.cfg = cfg or ContConfig()
        self.log = log or (lambda m: None)
        self.events: List[Dict] = []
        self.seq = 0
        self.thesis = None
        self.last_fire_ts = 0
        self.failed_keys = set()
        self.stats = {"scanned": 0, "rejected": 0, "fired": 0, "exits": 0, "reject_reasons": {}, "reject_codes": {}}
        self.funnel = {
            "locations_detected": 0, "sweeps_detected": 0, "reclaims_detected": 0,
            "bos_5m_detected": 0, "pullbacks_detected": 0, "continuations_detected": 0,
            "spread_passed": 0, "fires": 0,
        }
        self.cfg_compat = self.cfg

    @property
    def cfg_version(self):
        return self.cfg.version

    def _reject(self, reason: str, code: str = "OTHER") -> Dict:
        self.stats["rejected"] += 1
        self.stats["reject_reasons"][reason] = self.stats["reject_reasons"].get(reason, 0) + 1
        self.stats["reject_codes"][code] = self.stats["reject_codes"].get(code, 0) + 1
        self.events.append({"kind": "SETUP_REJECTED", "reason": reason, "code": code})
        return {"action": "WAIT", "fire": False, "reason": reason, "code": code}

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        self.stats["scanned"] += 1
        m1 = _cs(frames.get("M1"))
        m5 = _cs(frames.get("M5"))
        m15 = _cs(frames.get("M15"))
        h1 = _cs(frames.get("H1"))
        if len(m1) < 30 or len(m5) < 16 or len(m15) < 8 or len(h1) < 25:
            return self._reject("Need more closed candles", "NO_CANDLES")
        last1, last5 = m1[-1], m5[-1]
        hour = _hour(last1["ts"])
        london = self.cfg.london[0] <= hour < self.cfg.london[1]
        ny = self.cfg.ny[0] <= hour < self.cfg.ny[1]
        if not (london or ny):
            return self._reject("Outside London/NY", "SESSION")
        ema = _ema_last(h1, self.cfg.h1_ema)
        if ema is None:
            return self._reject("H1 EMA not ready", "NO_H1")
        h1_close = h1[-1]["close"]
        r5 = _rsi(m5, self.cfg.rsi_n)
        r1 = _rsi(m1, self.cfg.rsi_n)
        if r5 is None or r1 is None:
            return self._reject("RSI not ready", "NO_RSI")
        sl15 = m15[-1]["close"] - m15[-self.cfg.m15_lookback]["close"]
        atr1 = core.atr(m1)
        if atr1 <= 0:
            return self._reject("ATR not ready", "NO_ATR")
        spr = spread if spread else 0.0
        # spread in price; CSV points ~0.01 * points if gold point=0.01. Use raw if large.
        spr_pts = spr if spr > 1 else spr / 0.01
        if spr_pts > self.cfg.max_spread_points:
            return self._reject("Spread too wide", "SPREAD_TOO_HIGH")
        self.funnel["spread_passed"] += 1
        side = None
        if h1_close > ema and sl15 < 0 and r5 <= self.cfg.rsi_long and r1 <= self.cfg.rsi_long:
            if last1["close"] > last1["low"]:
                side = "long"
        elif h1_close < ema and sl15 > 0 and r5 >= self.cfg.rsi_short and r1 >= self.cfg.rsi_short:
            if last1["close"] < last1["high"]:
                side = "short"
        if not side:
            return self._reject("No H1+LTF washout alignment", "NO_SETUP")
        if last1["ts"] - self.last_fire_ts < self.cfg.cooldown_sec:
            return self._reject("Cooldown after prior signal", "COOLDOWN")
        lows = [b["low"] for b in m5[-3:]] + [last1["low"]]
        highs = [b["high"] for b in m5[-3:]] + [last1["high"]]
        if side == "long":
            sl = min(lows) - self.cfg.sl_buffer_atr_1m * atr1
            sl_dist = last1["close"] - sl
            invalid = min(lows)
        else:
            sl = max(highs) + self.cfg.sl_buffer_atr_1m * atr1
            sl_dist = sl - last1["close"]
            invalid = max(highs)
        if sl_dist < self.cfg.min_sl_atr_1m * atr1:
            return self._reject("SL too tight", "SL_TOO_TIGHT")
        self.funnel["pullbacks_detected"] += 1
        self.funnel["continuations_detected"] += 1
        self.funnel["fires"] += 1
        self.stats["fired"] += 1
        self.seq += 1
        self.last_fire_ts = last1["ts"]
        sid = f"CH1-{side[0].upper()}-{last1['ts']}-{self.seq}"
        sess = core.session_name(hour)
        entry = last1["close"]
        self.events.append({"kind": "SETUP_ACCEPTED", "reason": sid, "setup_id": sid})
        return {
            "action": "FIRE", "fire": True, "direction": side, "entry": entry, "stop": sl,
            "invalid_px": invalid, "level": ema, "level_name": "H1_EMA20",
            "setup_id": sid, "structure_key": f"{side}|H1|{round(ema,1)}",
            "session": sess, "vol_bucket": core.vol_bucket(1.0),
            "meta": {"location_type": "H1_EMA", "location_price": ema, "r5": r5, "r1": r1},
            "reason": f"CONT-H1 {side} H1 {h1_close:.2f} vs EMA {ema:.2f}",
            "version": self.cfg.version,
        }

    def on_open(self, setup, fill, sl, ts):
        self.thesis = type("T", (), {"direction": setup["direction"], "entry": fill, "invalid_px": setup.get("invalid_px"), "setup_id": setup.get("setup_id"), "level_name": "H1_EMA20", "level": setup.get("level") or 0, "mfe": 0.0, "mae": 0.0})()

    def on_exit(self, rec, ts=0):
        self.stats["exits"] += 1
        self.thesis = None

    def manage(self, bar, atr1=0):
        t = self.thesis
        if not t:
            return {"action": "FLAT"}
        if t.direction == "long" and bar["close"] < t.invalid_px:
            return {"action": "EXIT", "reason": "THESIS_FAIL"}
        if t.direction == "short" and bar["close"] > t.invalid_px:
            return {"action": "EXIT", "reason": "THESIS_FAIL"}
        return {"action": "HOLD", "setup_id": t.setup_id}
