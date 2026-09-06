from __future__ import annotations
from dataclasses import dataclass
from typing import List, Protocol
import math
from .contracts import Layer


@dataclass
class SymbolSpec:
    symbol: str = "XAUUSD"
    contract_size: float = 100.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 50.0
    digits: int = 2
    spread_points: float = 30.0  # XM gold typically ~0.30 = 30 points at 2 digits
    point: float = 0.01

    @property
    def spread_price(self) -> float:
        return self.spread_points * self.point

    def to_dict(self):
        return self.__dict__ | {"spread_price": self.spread_price}


class AllocationModel(Protocol):
    def risk_for_next_layer(self, equity: float, budget_pct: float, max_layers: int, open_layers: List[Layer]) -> float: ...


class EqualSplitAllocation:
    """Default: budget split evenly across max layers (3 layers -> ~3.33% each). Swap for adaptive later."""
    name = "equal_split"

    def risk_for_next_layer(self, equity, budget_pct, max_layers, open_layers):
        return equity * budget_pct / max_layers


class ClampedAllocation:
    """Equal-split of the equity-based budget, but hard-clamped to [min_usd, max_usd] per layer no matter
    how large or small equity has grown. This is the key defense against runaway compounding: without it,
    a hot streak inflates equity, which inflates the 10%-of-equity budget, which inflates position size right
    when a reversal is most costly. Clamping keeps the dollar risk on any single trade bounded and predictable,
    e.g. never less than $10 (below which min-lot rejects most setups) and never more than $100 (so a lucky
    spike in equity can't silently 8x your exposure)."""
    name = "clamped"

    def __init__(self, min_usd: float = 10.0, max_usd: float = 100.0):
        self.min_usd = min_usd
        self.max_usd = max_usd

    def risk_for_next_layer(self, equity, budget_pct, max_layers, open_layers):
        raw = equity * budget_pct / max_layers
        return max(self.min_usd, min(raw, self.max_usd))


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    lots: float = 0.0
    risk_usd: float = 0.0
    risk_pct: float = 0.0
    used_pct_after: float = 0.0


class RiskManager:
    """Shared 10% capital stop across ALL open hedged layers combined. Not 10% per layer."""

    def __init__(self, spec: SymbolSpec, budget_pct: float = 0.10, max_layers: int = 3,
                 allocation: AllocationModel | None = None):
        self.spec = spec
        self.budget_pct = budget_pct
        self.max_layers = max_layers
        self.allocation = allocation or EqualSplitAllocation()

    def used_risk_usd(self, layers: List[Layer]) -> float:
        return sum(l.worst_case_loss(self.spec.contract_size) for l in layers)

    def used_risk_pct(self, layers: List[Layer], equity: float) -> float:
        return self.used_risk_usd(layers) / equity if equity > 0 else 1.0

    def floating_pnl(self, layers: List[Layer], price: float) -> float:
        return sum(l.pnl_usd(price, self.spec.contract_size) for l in layers)

    def round_lots(self, lots: float) -> float:
        steps = math.floor(lots / self.spec.lot_step + 1e-9)
        return round(max(0.0, min(steps * self.spec.lot_step, self.spec.max_lot)), 2)

    def size_new_layer(self, equity: float, entry: float, sl: float, layers: List[Layer], direction: str) -> RiskDecision:
        same_dir = [l for l in layers if l.direction == direction]
        if len(same_dir) >= self.max_layers:
            return RiskDecision(False, f"Max {self.max_layers} layers already open for {direction}")
        sl_dist = abs(entry - sl)
        if sl_dist <= 0:
            return RiskDecision(False, "Invalid stop distance")
        budget_usd = equity * self.budget_pct
        used = self.used_risk_usd(layers)
        remaining = budget_usd - used
        target = self.allocation.risk_for_next_layer(equity, self.budget_pct, self.max_layers, layers)
        risk_usd = min(target, remaining)
        if risk_usd <= 0:
            return RiskDecision(False, f"Risk budget exhausted ({used/equity:.1%} of {self.budget_pct:.0%} used)")
        lots = self.round_lots(risk_usd / (sl_dist * self.spec.contract_size))
        if lots < self.spec.min_lot:
            need = self.spec.min_lot * sl_dist * self.spec.contract_size
            return RiskDecision(False, f"Min lot {self.spec.min_lot} would risk ${need:.2f} > allowed ${risk_usd:.2f}; stop too wide for capital")
        actual_risk = lots * sl_dist * self.spec.contract_size
        if used + actual_risk > budget_usd + 1e-9:
            return RiskDecision(False, f"Entry would push exposure to {(used+actual_risk)/equity:.1%} > {self.budget_pct:.0%} cap")
        return RiskDecision(True, "ok", lots=lots, risk_usd=round(actual_risk, 2),
                            risk_pct=actual_risk / equity, used_pct_after=(used + actual_risk) / equity)