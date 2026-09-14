"""Desk brain. After a fire, stay on the trade every minute with a thesis and follow-ups."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from .contracts import Layer


@dataclass
class Thesis:
    layer_id: str
    direction: str
    session: str
    entry: float
    sl: float
    tp: Optional[float]
    plan: str
    bias: str
    summary: str
    opened: datetime
    followups: List[dict] = field(default_factory=list)

    def note(self, now: datetime, msg: str, action: str = "hold") -> dict:
        rec = {"time": now.isoformat() if hasattr(now, "isoformat") else str(now), "msg": msg, "action": action}
        self.followups.append(rec)
        self.followups = self.followups[-40:]
        return rec

    def to_dict(self) -> dict:
        return {
            "layer_id": self.layer_id, "direction": self.direction, "session": self.session,
            "entry": self.entry, "sl": self.sl, "tp": self.tp, "plan": self.plan,
            "bias": self.bias, "summary": self.summary,
            "opened": self.opened.isoformat() if hasattr(self.opened, "isoformat") else str(self.opened),
            "followups": self.followups[-8:],
        }


class TradeBrain:
    """Watch open layers every minute. Kill dead fills. Leave runners to hard TP."""

    def __init__(self, dead_min: float = 20.0, dead_r: float = 0.15):
        self.dead_min = dead_min
        self.dead_r = dead_r
        self.theses: dict[str, Thesis] = {}

    def open_thesis(self, layer: Layer, analysis: dict) -> Thesis:
        tp = layer.tp
        plan = (
            f"L{layer.layer_number} {layer.direction} scalp. Risk to {layer.sl:.2f}. "
            f"Bank at {tp:.2f} if set else hold 2.5R. Manage every minute. No London/Fri/19:00."
            if tp else
            f"L{layer.layer_number} {layer.direction}. SL {layer.sl:.2f}. Manage every minute."
        )
        th = Thesis(
            layer_id=layer.id, direction=layer.direction, session=layer.session,
            entry=layer.entry, sl=layer.sl, tp=tp, plan=plan,
            bias=(layer.bias or {}).get("direction") or analysis.get("bias", {}).get("direction", ""),
            summary=layer.summary or analysis.get("summary", ""),
            opened=layer.open_time,
        )
        th.note(layer.open_time, f"FIRE {layer.direction} @ {layer.entry:.2f} | {th.summary}", "open")
        self.theses[layer.id] = th
        return th

    def review(self, layer: Layer, price: float, now: datetime, contract_size: float) -> dict:
        th = self.theses.get(layer.id)
        if th is None:
            th = self.open_thesis(layer, {})
        r = layer.r_multiple(price)
        pnl = layer.pnl_usd(price, contract_size)
        age = 0.0
        try:
            age = (now.replace(tzinfo=None) - layer.open_time.replace(tzinfo=None)).total_seconds() / 60.0
        except Exception:
            pass
        action = "hold"
        msg = f"{age:.0f}m r={r:+.2f} pnl={pnl:+.2f}"
        if r >= 1.0:
            msg += " | runner, leave TP"
        elif age >= self.dead_min and r < self.dead_r:
            action = "time_stop"
            msg += f" | dead fill {age:.0f}m under {self.dead_r}R — flatten"
        th.note(now, msg, action)
        return {"action": action, "r": round(r, 3), "age_min": round(age, 1), "pnl": round(pnl, 2), "thesis": th.to_dict()}

    def close(self, layer_id: str, now: datetime, reason: str) -> None:
        th = self.theses.pop(layer_id, None)
        if th:
            th.note(now, f"EXIT {reason}", "close")
