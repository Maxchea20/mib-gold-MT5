"""LIQ-JOIN M3 entry, V2.1 1:3 target. Setup/pool still dies after SL."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .liq_join_m3 import LiqJoinM3
from .liq_join import LiqConfig
from . import hunt_tp_bind


class LiqM3V21(LiqJoinM3):
    def __init__(self, cfg: Optional[LiqConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "LIQ_M3_V21_1_3"

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        d = super().evaluate(frames, now, spread)
        if not d.get("fire"):
            return d
        entry = float(d["entry"])
        sl = float(d["stop"])
        risk = abs(entry - sl)
        if risk <= 0:
            return self._reject("No SL distance", "NO_SL")
        side = d["direction"]
        tp = entry + 3.0 * risk if side == "long" else entry - 3.0 * risk
        d["tp"] = tp
        d["reason"] = f"LIQ_M3 1:3 {side}"
        meta = dict(d.get("meta") or {})
        meta["tp"] = tp
        meta["rr"] = "1:3"
        d["meta"] = meta
        hunt_tp_bind.LAST_TP = float(tp)
        return d
