"""LIQ-JOIN M3 but skip if next pool is closer than 1R."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .liq_join import LiqConfig
from .liq_join_m3 import LiqJoinM3


class LiqJoinM3R1(LiqJoinM3):
    def __init__(self, cfg: Optional[LiqConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "LIQ_JOIN_M3_R1"

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        d = super().evaluate(frames, now, spread)
        if not d.get("fire"):
            return d
        entry = float(d["entry"])
        sl = float(d["stop"])
        tp = float(d["tp"])
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0 or reward < risk:
            # undo used-pool so a later wider target can still arm this pool
            key = (d.get("direction"), round(float(d.get("level") or 0), 1))
            self.used.discard(key)
            self.stats["fired"] = max(0, self.stats.get("fired", 1) - 1)
            self.funnel["fires"] = max(0, self.funnel.get("fires", 1) - 1)
            return self._reject("Target < 1R", "TP_LT_1R")
        d["reason"] = f"{d.get('reason','')} min1R"
        return d
