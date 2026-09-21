from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
from .contracts import Layer, new_id
from .risk import RiskManager, SymbolSpec
from .trailing import TrailingTP
from .journal import open_record, close_record


class PositionBook:
    def __init__(self, spec: SymbolSpec, risk: RiskManager, trailing: TrailingTP, balance: float, mode: str):
        self.spec, self.risk, self.trailing, self.mode = spec, risk, trailing, mode
        self.balance = balance
        self.start_balance = balance
        self.layers: List[Layer] = []
        self.closed: List[dict] = []
        self.rejections: List[dict] = []

    def equity(self, price: float) -> float:
        return self.balance + self.risk.floating_pnl(self.layers, price)

    def group_for(self, direction: str) -> List[Layer]:
        return [l for l in self.layers if l.direction == direction]

    def open_layer(self, direction: str, entry: float, sl: float, lots: float, risk_usd: float, ts: datetime,
                   votes: dict, consensus: dict, summary: str, session: str, bias: dict, ticket=None, tp=None) -> Layer:
        group = self.group_for(direction)
        gid = group[0].group_id if group else new_id("G")
        if tp is None and isinstance(consensus, dict):
            tp = consensus.get("tp")
        if tp is None and isinstance(votes, dict):
            tp = votes.get("tp")
        if group and group[0].tp is not None:
            tp = group[0].tp
        layer = Layer(id=new_id("L"), group_id=gid, layer_number=len(group) + 1, direction=direction,
                      entry=entry, sl=sl, initial_sl=sl, lots=lots, risk_usd=risk_usd, open_time=ts, peak=entry,
                      agent_votes=votes, consensus=consensus, summary=summary, session=session, bias=bias,
                      ticket=ticket, tp=tp)
        self.layers.append(layer)
        return layer

    def close_layer(self, layer: Layer, exit_price: float, reason: str, ts: datetime) -> dict:
        pnl = layer.pnl_usd(exit_price, self.spec.contract_size)
        self.balance += pnl
        self.layers.remove(layer)
        rec = close_record(layer, exit_price, reason, ts, self.spec.contract_size, self.mode)
        self.closed.append(rec)
        return rec

    def on_bar(self, high: float, low: float, close: float, atr: float, ts: datetime, slippage: float = 0.0) -> List[dict]:
        closed = []
        for layer in list(self.layers):
            if layer.tp is not None:
                if layer.sign > 0 and high >= layer.tp:
                    closed.append(self.close_layer(layer, layer.tp, "STRUCTURE_TP", ts))
                    continue
                if layer.sign < 0 and low <= layer.tp:
                    closed.append(self.close_layer(layer, layer.tp, "STRUCTURE_TP", ts))
                    continue
            hit = self.trailing.check_exit(layer, high, low)
            if hit:
                reason, px = hit
                px -= slippage * layer.sign
                closed.append(self.close_layer(layer, px, reason, ts))
                continue
            self.trailing.update(layer, close, atr)
        return closed

    def open_records(self, price: float) -> List[dict]:
        return [open_record(l, price, self.spec.contract_size, self.mode) for l in self.layers]

    def snapshot(self, price: float) -> dict:
        eq = self.equity(price)
        used = self.risk.used_risk_usd(self.layers)
        return {
            "balance": round(self.balance, 2), "equity": round(eq, 2),
            "floating_pnl": round(self.risk.floating_pnl(self.layers, price), 2),
            "risk_used_usd": round(used, 2), "risk_used_pct": round(used / eq, 4) if eq > 0 else 1.0,
            "risk_budget_pct": self.risk.budget_pct, "max_layers": self.risk.max_layers,
            "open_layers": len(self.layers), "closed_trades": len(self.closed),
            "layers": self.open_records(price),
        }
