"""V2.1: invalidate the failed 15M setup only. H3 $2.50 SL / $5 TP from fill."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .hunt_h2 import HuntEngine, HuntConfig
from . import hunt_tp_bind

SL_USD = 2.5
TP_USD = 5.0


class CFastV21H3(HuntEngine):
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "CFAST_V21_H3_2.5_5"
        self.dead_setups = set()  # (side, rounded 15M level)

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        decision = super().evaluate(frames, now, spread)
        if not decision.get("fire"):
            return decision
        side = decision["direction"]
        lvl = round(float(decision.get("level") or 0), 1)
        key = (side, lvl)
        if key in self.dead_setups:
            return self._reject("Old setup re-fire blocked", "OLD_SETUP")
        entry = float(decision["entry"])
        if side == "long":
            sl, tp = entry - SL_USD, entry + TP_USD
        else:
            sl, tp = entry + SL_USD, entry - TP_USD
        decision["stop"] = sl
        decision["tp"] = tp
        decision["reason"] = f"V21H3 {side} L{lvl} SL {SL_USD} TP {TP_USD}"
        meta = dict(decision.get("meta") or {})
        meta.update({"tp": tp, "setup_key": f"{side}|{lvl}", "sl_usd": SL_USD, "tp_usd": TP_USD})
        decision["meta"] = meta
        hunt_tp_bind.LAST_TP = float(tp)
        return decision

    def on_exit(self, rec, ts=0):
        reason = str((rec or {}).get("exit_reason") or "").upper()
        if reason == "STRUCTURAL_SL" and self.thesis and isinstance(self.thesis, dict):
            side = self.thesis.get("direction")
            lvl = round(float(self.thesis.get("level") or 0), 1)
            if side:
                self.dead_setups.add((side, lvl))
        super().on_exit(rec, ts)
