"""LIQ-JOIN on M1. Fake-break filter: need a second M1 close still beyond the pool."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional
from . import core
from . import hunt_tp_bind


@dataclass
class Cfg:
    swing_k: int = 2
    sl_buffer_atr_1m: float = 0.20
    min_sl_atr_1m: float = 0.50
    cooldown_sec: int = 900
    frozen: bool = True
    version: str = "LIQ_JOIN_M1_HOLD"


def _cs(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return core.rows(x)


class LiqJoinM1:
    def __init__(self, cfg: Optional[Cfg] = None, log: Optional[Callable] = None):
        self.cfg = cfg or Cfg()
        self.log = log or (lambda m: None)
        self.events: List[Dict] = []
        self.seq = 0
        self.thesis = None
        self.last_fire_ts = 0
        self.dead = set()
        self.used = set()
        self.stats = {"scanned": 0, "rejected": 0, "fired": 0, "exits": 0, "reject_reasons": {}, "reject_codes": {}}
        self.funnel = {
            "locations_detected": 0, "sweeps_detected": 0, "reclaims_detected": 0,
            "bos_5m_detected": 0, "pullbacks_detected": 0, "continuations_detected": 0,
            "spread_passed": 0, "fires": 0,
        }
        hunt_tp_bind.bind()

    def _reject(self, reason: str, code: str = "OTHER") -> Dict:
        self.stats["rejected"] += 1
        self.stats["reject_reasons"][reason] = self.stats["reject_reasons"].get(reason, 0) + 1
        self.stats["reject_codes"][code] = self.stats["reject_codes"].get(code, 0) + 1
        return {"action": "WAIT", "fire": False, "reason": reason, "code": code}

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        self.stats["scanned"] += 1
        m1 = _cs(frames.get("M1"))
        m15 = _cs(frames.get("M15"))
        if len(m1) < 30 or len(m15) < 12:
            return self._reject("Need closed candles", "NO_CANDLES")
        brk, hold = m1[-2], m1[-1]
        hi, lo = core.swings(m15, self.cfg.swing_k)
        if not hi and not lo:
            return self._reject("No 15M pool", "NO_POOL")
        self.funnel["locations_detected"] += 1
        pool_hi = hi[-1]["high"] if hi else None
        pool_lo = lo[-1]["low"] if lo else None
        next_hi = hi[-2]["high"] if len(hi) >= 2 else (hi[-1]["high"] if hi else None)
        next_lo = lo[-2]["low"] if len(lo) >= 2 else (lo[-1]["low"] if lo else None)
        atr1 = core.atr(m1)
        if atr1 <= 0:
            return self._reject("No ATR", "NO_ATR")
        if hold["ts"] - self.last_fire_ts < self.cfg.cooldown_sec:
            return self._reject("Cooldown", "COOLDOWN")

        side = pool = tp = None
        # break candle closes through, hold candle must stay through
        if pool_hi is not None and brk["high"] > pool_hi and brk["close"] > pool_hi:
            if hold["close"] <= pool_hi:
                return self._reject("Fake break high (M1 closed back in)", "FAKE_BREAK")
            side, pool, tp = "long", pool_hi, next_hi
            self.funnel["sweeps_detected"] += 1
        elif pool_lo is not None and brk["low"] < pool_lo and brk["close"] < pool_lo:
            if hold["close"] >= pool_lo:
                return self._reject("Fake break low (M1 closed back in)", "FAKE_BREAK")
            side, pool, tp = "short", pool_lo, next_lo
            self.funnel["sweeps_detected"] += 1
        else:
            return self._reject("No M1 close through pool", "NO_SWEEP_CLOSE")

        key = (side, round(float(pool), 1))
        if key in self.dead:
            return self._reject("Pool already failed", "DEAD_POOL")
        if key in self.used:
            return self._reject("Pool already used", "USED_POOL")

        entry = hold["close"]
        if side == "long":
            wick = min(brk["low"], hold["low"])
            sl = wick - self.cfg.sl_buffer_atr_1m * atr1
            sl_dist = entry - sl
        else:
            wick = max(brk["high"], hold["high"])
            sl = wick + self.cfg.sl_buffer_atr_1m * atr1
            sl_dist = sl - entry
        if sl_dist < self.cfg.min_sl_atr_1m * atr1:
            return self._reject("SL still inside the hunt", "SL_TOO_TIGHT")
        if tp is None or (side == "long" and tp <= entry) or (side == "short" and tp >= entry):
            return self._reject("No opposing pool target", "NO_TP")

        hunt_tp_bind.LAST_TP = float(tp)
        self.used.add(key)
        self.funnel["fires"] += 1
        self.stats["fired"] += 1
        self.seq += 1
        self.last_fire_ts = hold["ts"]
        hour = datetime.utcfromtimestamp(hold["ts"]).hour
        sid = f"LM1-{side[0].upper()}-{hold['ts']}-{self.seq}"
        return {
            "action": "FIRE", "fire": True, "direction": side, "entry": entry, "stop": sl, "tp": tp,
            "invalid_px": wick, "level": pool, "level_name": "15M_POOL",
            "setup_id": sid, "structure_key": f"{side}|POOL|{round(pool,1)}",
            "session": core.session_name(hour), "vol_bucket": core.vol_bucket(1.0),
            "meta": {"location_type": "15M_POOL", "location_price": pool, "tp": tp, "wick": wick},
            "reason": f"LIQ_M1 {side} pool {pool:.2f} hold-close TP {tp:.2f}",
            "version": self.cfg.version,
        }

    def on_open(self, setup, fill, sl, ts):
        self.thesis = setup
        if setup.get("tp") is not None:
            hunt_tp_bind.LAST_TP = float(setup["tp"])

    def on_exit(self, rec, ts=0):
        self.stats["exits"] += 1
        reason = str((rec or {}).get("exit_reason") or "").upper()
        if reason == "STRUCTURAL_SL" and self.thesis and isinstance(self.thesis, dict):
            side = self.thesis.get("direction")
            lvl = round(float(self.thesis.get("level") or 0), 1)
            if side:
                self.dead.add((side, lvl))
        self.thesis = None
        hunt_tp_bind.LAST_TP = None

    def manage(self, bar, atr1=0):
        return {"action": "HOLD"}
