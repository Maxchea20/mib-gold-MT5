"""Post-FIRE Brain: HOLD / TRAIL / EXIT. Port of desktop lifecycle.py V1b."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

LONG, SHORT = "LONG", "SHORT"
HOLD, TRAIL, EXIT = "HOLD", "TRAIL", "EXIT"
LIFECYCLE_VERSION = "BRAIN_LIFECYCLE_V1B"


@dataclass
class Thesis:
    side: str
    event: Optional[str]
    level: Optional[float]
    reasons: List[str] = field(default_factory=list)
    story_tf: str = "15m"
    valid: bool = True
    invalid_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    trade_id: str
    side: str
    entry: float
    sl: float
    tp: Optional[float]
    qty: float
    risk_usd: float
    equity_at_entry: float
    atr: float
    thesis: Thesis
    opened_ts: Optional[int] = None
    trail_sl: Optional[float] = None
    best: Optional[float] = None
    r_now: float = 0.0
    protected: bool = False

    def hard_sl(self) -> float:
        t = self.trail_sl
        if t is None:
            return self.sl
        if self.side == LONG:
            return max(self.sl, t)
        return min(self.sl, t)


def position_from_layer(layer, equity: float = 1000.0) -> Position:
    side = (layer.direction or "").upper()
    if side == "LONG":
        side = LONG
    elif side == "SHORT":
        side = SHORT
    entry = float(layer.entry)
    sl = float(layer.sl)
    tp = float(layer.tp) if getattr(layer, "tp", None) else None
    atr = abs(entry - sl)
    th = Thesis(side=side, event=None, level=entry, reasons=["open position"])
    opened = getattr(layer, "open_time", None)
    ts = int(opened.timestamp()) if opened is not None and hasattr(opened, "timestamp") else None
    return Position(
        trade_id=str(layer.id), side=side, entry=entry, sl=sl, tp=tp,
        qty=float(getattr(layer, "lots", 0) or 0), risk_usd=float(getattr(layer, "risk_usd", 0) or 0),
        equity_at_entry=float(equity), atr=atr, thesis=th, opened_ts=ts, best=entry,
    )


def _r_multiple(pos: Position, price: float) -> float:
    risk = abs(pos.entry - pos.sl)
    if risk <= 0:
        return 0.0
    if pos.side == LONG:
        return (price - pos.entry) / risk
    return (pos.entry - price) / risk


def reevaluate(pos: Position, *, price: float, high: Optional[float] = None, low: Optional[float] = None,
               structure_event: Optional[str] = None, structure_dir: Optional[str] = None,
               level_lost: bool = False, now_ts: Optional[int] = None) -> Dict[str, Any]:
    hi = high if high is not None else price
    lo = low if low is not None else price
    if pos.side == LONG:
        pos.best = max(pos.best or pos.entry, hi)
    else:
        pos.best = min(pos.best or pos.entry, lo)
    pos.r_now = _r_multiple(pos, price)
    log = {"lifecycle_version": LIFECYCLE_VERSION, "trade_id": pos.trade_id, "price": price,
           "r_now": pos.r_now, "thesis": pos.thesis.to_dict(), "now_ts": now_ts}
    ev = (structure_event or "").upper()
    sd = (structure_dir or "").upper()
    against = (pos.side == LONG and sd in ("BEARISH", "SHORT", "DOWN")) or (
        pos.side == SHORT and sd in ("BULLISH", "LONG", "UP")
    )
    if ev in ("CHOCH", "CHoCH") and against:
        return {**log, "action": EXIT, "reason": "15m CHoCH against thesis", "exit_kind": "THESIS_FAILURE"}
    if level_lost:
        return {**log, "action": EXIT, "reason": "originating structure lost", "exit_kind": "STRUCTURAL_INVALIDATION"}
    sl = pos.hard_sl()
    if pos.side == LONG and lo <= sl:
        return {**log, "action": EXIT, "reason": "hard SL", "exit_kind": "HARD_SL", "exit_px": sl}
    if pos.side == SHORT and hi >= sl:
        return {**log, "action": EXIT, "reason": "hard SL", "exit_kind": "HARD_SL", "exit_px": sl}
    if pos.tp is not None:
        if pos.side == LONG and hi >= pos.tp:
            return {**log, "action": EXIT, "reason": "target reached", "exit_kind": "TARGET_REACHED", "exit_px": pos.tp}
        if pos.side == SHORT and lo <= pos.tp:
            return {**log, "action": EXIT, "reason": "target reached", "exit_kind": "TARGET_REACHED", "exit_px": pos.tp}
    moved = False
    if pos.r_now >= 1.0 and pos.atr > 0:
        if pos.side == LONG:
            new_sl = max(pos.sl, pos.entry, (pos.best or pos.entry) - pos.atr)
            if pos.trail_sl is None or new_sl > pos.trail_sl:
                pos.trail_sl = new_sl
                moved = True
        else:
            new_sl = min(pos.sl, pos.entry, (pos.best or pos.entry) + pos.atr)
            if pos.trail_sl is None or new_sl < pos.trail_sl:
                pos.trail_sl = new_sl
                moved = True
    if moved:
        return {**log, "action": TRAIL, "reason": "protect profit / structure trail", "sl": pos.hard_sl(), "protected": True}
    return {**log, "action": HOLD, "reason": "thesis still valid", "sl": pos.hard_sl()}
