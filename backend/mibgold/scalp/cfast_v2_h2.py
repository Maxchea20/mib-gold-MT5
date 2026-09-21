"""C-Fast V2 lifecycle on Hunt H2 execution.
After SL, that direction is locked until a NEW 15M swing prints.
TP remains next opposing 15M. No 1:3. No V1 sweep.
"""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .hunt_h2 import HuntEngine, HuntConfig, _cs
from . import core


class CFastV2Hunt(HuntEngine):
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "CFAST_V2_H2"
        self.lock = {"long": None, "short": None}  # last 15M swing price that failed

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        m15 = _cs(frames.get("M15"))
        res = sup = None
        if len(m15) >= 8:
            hi, lo = core.swings(m15, self.cfg.swing_k)
            res = hi[-1]["high"] if hi else None
            sup = lo[-1]["low"] if lo else None
            # unlock when a new swing appears beyond the failed level
            if self.lock["short"] is not None and res is not None and abs(res - self.lock["short"]) > 1e-6:
                if res != self.lock["short"]:
                    self.lock["short"] = None
            if self.lock["long"] is not None and sup is not None and abs(sup - self.lock["long"]) > 1e-6:
                if sup != self.lock["long"]:
                    self.lock["long"] = None
        decision = super().evaluate(frames, now, spread)
        if not decision.get("fire"):
            return decision
        side = decision["direction"]
        if self.lock.get(side):
            return self._reject(f"{side} locked until new 15M structure", "DIR_LOCK")
        return decision

    def on_exit(self, rec, ts=0):
        reason = str((rec or {}).get("exit_reason") or "").upper()
        side = (rec or {}).get("direction") or (rec or {}).get("side")
        if reason == "STRUCTURAL_SL" and side in ("long", "short"):
            lvl = None
            if self.thesis and isinstance(self.thesis, dict):
                lvl = self.thesis.get("level")
            self.lock[side] = lvl if lvl is not None else True
        super().on_exit(rec, ts)
