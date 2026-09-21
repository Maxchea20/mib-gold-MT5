"""Hunt H2: 15M level, 5M tag arm, M1-close fire, SL past 5M wick, TP next opposing 15M."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from . import core


@dataclass
class HuntConfig:
    swing_k: int = 2
    sl_buffer_atr_1m: float = 0.15
    min_sl_atr_1m: float = 0.35
    cooldown_sec: int = 900
    frozen: bool = True
    version: str = "HUNT_H2"


def _cs(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return core.rows(x)


class HuntEngine:
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable[[str], None]] = None):
        self.cfg = cfg or HuntConfig()
        self.log = log or (lambda m: None)
        self.events: List[Dict] = []
        self.seq = 0
        self.thesis = None
        self.arm = None
        self.last_fire_ts = 0
        self.stats = {"scanned": 0, "rejected": 0, "fired": 0, "exits": 0, "reject_reasons": {}, "reject_codes": {}}
        self.funnel = {
            "locations_detected": 0, "sweeps_detected": 0, "reclaims_detected": 0,
            "bos_5m_detected": 0, "pullbacks_detected": 0, "continuations_detected": 0,
            "spread_passed": 0, "fires": 0,
        }

    def _reject(self, reason: str, code: str = "OTHER") -> Dict:
        self.stats["rejected"] += 1
        self.stats["reject_reasons"][reason] = self.stats["reject_reasons"].get(reason, 0) + 1
        self.stats["reject_codes"][code] = self.stats["reject_codes"].get(code, 0) + 1
        return {"action": "WAIT", "fire": False, "reason": reason, "code": code}

    def _levels(self, m15):
        k = self.cfg.swing_k
        hi, lo = core.swings(m15, k)
        res = hi[-1]["high"] if hi else None
        sup = lo[-1]["low"] if lo else None
        # next opposing: previous swing the other way
        next_sup = lo[-2]["low"] if len(lo) >= 2 else (lo[-1]["low"] if lo else None)
        next_res = hi[-2]["high"] if len(hi) >= 2 else (hi[-1]["high"] if hi else None)
        return res, sup, next_res, next_sup

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        self.stats["scanned"] += 1
        m1 = _cs(frames.get("M1"))
        m5 = _cs(frames.get("M5"))
        m15 = _cs(frames.get("M15"))
        if len(m1) < 20 or len(m5) < 8 or len(m15) < 12:
            return self._reject("Need closed M1/M5/M15", "NO_CANDLES")
        last1, last5 = m1[-1], m5[-1]
        res, sup, next_res, next_sup = self._levels(m15)
        if res:
            self.funnel["locations_detected"] += 1
        atr1 = core.atr(m1)
        if atr1 <= 0:
            return self._reject("ATR not ready", "NO_ATR")

        # ARM on completed 5M tag of 15M level, close back
        if res is not None and last5["high"] >= res and last5["close"] < res:
            self.arm = {"side": "short", "level": res, "wick": last5["high"], "tp": next_sup, "ts": last5["ts"]}
            self.funnel["sweeps_detected"] += 1
        elif sup is not None and last5["low"] <= sup and last5["close"] > sup:
            self.arm = {"side": "long", "level": sup, "wick": last5["low"], "tp": next_res, "ts": last5["ts"]}
            self.funnel["sweeps_detected"] += 1

        if not self.arm:
            return self._reject("No 5M tag of 15M level", "NO_ARM")
        arm = self.arm
        if last1["ts"] - arm["ts"] > 6 * 3600:
            self.arm = None
            return self._reject("Arm expired", "ARM_EXPIRED")
        if last1["ts"] - self.last_fire_ts < self.cfg.cooldown_sec:
            return self._reject("Cooldown", "COOLDOWN")

        side = arm["side"]
        lvl = arm["level"]
        tagged = (last1["low"] <= lvl <= last1["high"]) or (
            side == "long" and last1["close"] >= lvl
        ) or (
            side == "short" and last1["close"] <= lvl
        )
        if not tagged:
            return self._reject("M1 has not tagged armed level", "NO_M1_TAG")

        entry = last1["close"]
        if side == "long":
            sl = min(arm["wick"], last1["low"]) - self.cfg.sl_buffer_atr_1m * atr1
            tp = arm.get("tp")
            sl_dist = entry - sl
        else:
            sl = max(arm["wick"], last1["high"]) + self.cfg.sl_buffer_atr_1m * atr1
            tp = arm.get("tp")
            sl_dist = sl - entry
        if sl_dist < self.cfg.min_sl_atr_1m * atr1:
            return self._reject("SL too tight", "SL_TOO_TIGHT")
        if tp is None or (side == "long" and tp <= entry) or (side == "short" and tp >= entry):
            return self._reject("No opposing 15M target", "NO_TP")

        self.funnel["fires"] += 1
        self.stats["fired"] += 1
        self.seq += 1
        self.last_fire_ts = last1["ts"]
        sid = f"H2-{side[0].upper()}-{last1['ts']}-{self.seq}"
        hour = __import__("datetime").datetime.utcfromtimestamp(last1["ts"]).hour
        self.arm = None
        return {
            "action": "FIRE", "fire": True, "direction": side, "entry": entry, "stop": sl, "tp": tp,
            "invalid_px": arm["wick"], "level": lvl, "level_name": "15M",
            "setup_id": sid, "structure_key": f"{side}|15M|{round(lvl,1)}",
            "session": core.session_name(hour), "vol_bucket": core.vol_bucket(1.0),
            "meta": {"location_type": "15M", "location_price": lvl, "tp": tp, "wick": arm["wick"]},
            "reason": f"HUNT_H2 {side} 15M {lvl:.2f} TP {tp:.2f}",
            "version": self.cfg.version,
        }

    def on_open(self, setup, fill, sl, ts):
        self.thesis = setup

    def on_exit(self, rec, ts=0):
        self.stats["exits"] += 1
        self.thesis = None

    def manage(self, bar, atr1=0):
        return {"action": "HOLD"}
