from datetime import datetime
from typing import Optional
from .contracts import Layer, money_text, r_text
from .session import SESSION_LABEL


def open_record(layer: Layer, price: float, contract_size: float, mode: str) -> dict:
    pnl = layer.pnl_usd(price, contract_size)
    r = layer.r_multiple(price)
    return {
        "id": layer.id, "group_id": layer.group_id, "layer_number": layer.layer_number,
        "mode": mode, "status": "open",
        "timestamp": layer.open_time.isoformat(), "direction": layer.direction,
        "entry": round(layer.entry, 2), "sl": round(layer.sl, 2), "initial_sl": round(layer.initial_sl, 2),
        "tp_mode": "trailing", "trail_level": None if layer.trail_level is None else round(layer.trail_level, 2),
        "trail_active": layer.trail_active, "lots": layer.lots, "risk_usd": round(layer.risk_usd, 2),
        "sl_distance": round(abs(price - layer.sl), 2),
        "session": layer.session, "session_label": SESSION_LABEL.get(layer.session, layer.session),
        "agent_votes": layer.agent_votes, "consensus": layer.consensus, "summary": layer.summary,
        "bias": layer.bias, "current_price": round(price, 2),
        "pnl_usd": round(pnl, 2), "pnl_text": money_text(pnl, closed=False),
        "r_multiple": round(r, 3), "r_text": r_text(r),
    }


def close_record(layer: Layer, exit_price: float, exit_reason: str, exit_time: datetime,
                 contract_size: float, mode: str) -> dict:
    rec = open_record(layer, exit_price, contract_size, mode)
    pnl = layer.pnl_usd(exit_price, contract_size)
    r = layer.r_multiple(exit_price)
    rec.update({
        "status": "closed", "exit_price": round(exit_price, 2), "exit_reason": exit_reason,
        "exit_time": exit_time.isoformat(), "pnl_usd": round(pnl, 2), "pnl_text": money_text(pnl, closed=True),
        "r_multiple": round(r, 3), "r_text": r_text(r), "outcome": "win" if pnl > 0 else "loss" if pnl < 0 else "flat",
        "strongest_engine": _strongest(layer),
    })
    return rec


def _strongest(layer: Layer) -> Optional[str]:
    contrib = layer.consensus.get("contributions") or {}
    if not contrib:
        return None
    return max(contrib, key=lambda k: abs(contrib[k]))
