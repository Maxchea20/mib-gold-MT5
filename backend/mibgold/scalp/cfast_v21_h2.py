"""V2.1: dead 15M setup only. H2 wick SL + next 15M TP."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .hunt_h2 import HuntEngine, HuntConfig
from . import hunt_tp_bind


class CFastV21H2(HuntEngine):
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "CFAST_V21_H2"
        self.dead_setups = set()

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        decision = super().evaluate(frames, now, spread)
        if not decision.get("fire"):
            return decision
        side = decision["direction"]
        lvl = round(float(decision.get("level") or 0), 1)
        if (side, lvl) in self.dead_setups:
            return self._reject("Old setup re-fire blocked", "OLD_SETUP")
        if decision.get("tp") is not None:
            hunt_tp_bind.LAST_TP = float(decision["tp"])
        decision["reason"] = f"V21H2 {side} L{lvl}"
        return decision

    def on_exit(self, rec, ts=0):
        reason = str((rec or {}).get("exit_reason") or "").upper()
        if reason == "STRUCTURAL_SL" and self.thesis and isinstance(self.thesis, dict):
            side = self.thesis.get("direction")
            lvl = round(float(self.thesis.get("level") or 0), 1)
            if side:
                self.dead_setups.add((side, lvl))
        super().on_exit(rec, ts)
