"""Plain C-Fast V2.1: Hunt fire, kill failed SETUP only, SL=1R TP=3R."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .hunt_h2 import HuntEngine, HuntConfig
from . import hunt_tp_bind


class CFastV21(HuntEngine):
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "CFAST_V21_1_3"
        self.dead_setups = set()

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        d = super().evaluate(frames, now, spread)
        if not d.get("fire"):
            return d
        side = d["direction"]
        lvl = round(float(d.get("level") or 0), 1)
        if (side, lvl) in self.dead_setups:
            return self._reject("Old setup re-fire blocked", "OLD_SETUP")
        entry = float(d["entry"])
        sl = float(d["stop"])
        risk = abs(entry - sl)
        if risk <= 0:
            return self._reject("No SL distance", "NO_SL")
        if side == "long":
            tp = entry + 3.0 * risk
        else:
            tp = entry - 3.0 * risk
        d["tp"] = tp
        d["reason"] = f"V21 1:3 {side} L{lvl}"
        meta = dict(d.get("meta") or {})
        meta.update({"tp": tp, "rr": "1:3"})
        d["meta"] = meta
        hunt_tp_bind.LAST_TP = float(tp)
        return d

    def on_exit(self, rec, ts=0):
        reason = str((rec or {}).get("exit_reason") or "").upper()
        if reason == "STRUCTURAL_SL" and self.thesis and isinstance(self.thesis, dict):
            side = self.thesis.get("direction")
            lvl = round(float(self.thesis.get("level") or 0), 1)
            if side:
                self.dead_setups.add((side, lvl))
        super().on_exit(rec, ts)
