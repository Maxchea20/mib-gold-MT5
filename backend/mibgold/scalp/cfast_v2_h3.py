"""Hunt H2 entry + V2 direction lock + fixed $2.50 SL / $5.00 TP from fill."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .cfast_v2_h2 import CFastV2Hunt
from .hunt_h2 import HuntConfig
from . import hunt_tp_bind

SL_USD = 2.5
TP_USD = 5.0


class CFastV2H3(CFastV2Hunt):
    def __init__(self, cfg: Optional[HuntConfig] = None, log: Optional[Callable] = None):
        super().__init__(cfg, log)
        self.cfg.version = "CFAST_V2_H3_2.5_5"

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        decision = super().evaluate(frames, now, spread)
        if not decision.get("fire"):
            return decision
        entry = float(decision["entry"])
        side = decision["direction"]
        if side == "long":
            sl, tp = entry - SL_USD, entry + TP_USD
        else:
            sl, tp = entry + SL_USD, entry - TP_USD
        decision["stop"] = sl
        decision["tp"] = tp
        decision["reason"] = f"V2H3 {side} SL {SL_USD} TP {TP_USD}"
        meta = dict(decision.get("meta") or {})
        meta["tp"] = tp
        meta["sl_usd"] = SL_USD
        meta["tp_usd"] = TP_USD
        decision["meta"] = meta
        hunt_tp_bind.LAST_TP = float(tp)
        return decision
