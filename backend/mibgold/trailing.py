from dataclasses import dataclass
from typing import Optional, Tuple
from .contracts import Layer


@dataclass
class TrailingConfig:
    activate_r: float = 1.0        # start trailing once trade reaches +1R
    breakeven_r: float = 1.0       # move SL to entry at activation
    trail_atr_mult: float = 1.5    # trail distance in ATRs
    min_trail_r: float = 0.5       # never trail tighter than this many R


class TrailingTP:
    """Trailing take-profit: no fixed target; the exit level ratchets behind the peak."""

    def __init__(self, cfg: TrailingConfig | None = None):
        self.cfg = cfg or TrailingConfig()

    def update(self, layer: Layer, price: float, atr: float) -> None:
        risk_dist = abs(layer.entry - layer.initial_sl)
        if layer.peak == 0.0:
            layer.peak = price
        layer.peak = max(layer.peak, price) if layer.sign > 0 else min(layer.peak, price)
        r_now = layer.r_multiple(price)
        if not layer.trail_active and r_now >= self.cfg.activate_r:
            layer.trail_active = True
            be = layer.entry
            layer.sl = max(layer.sl, be) if layer.sign > 0 else min(layer.sl, be)
        if layer.trail_active:
            dist = max(self.cfg.trail_atr_mult * atr, self.cfg.min_trail_r * risk_dist)
            candidate = layer.peak - dist * layer.sign
            if layer.trail_level is None or (candidate - layer.trail_level) * layer.sign > 0:
                layer.trail_level = candidate
            if (layer.trail_level - layer.sl) * layer.sign > 0:
                layer.sl = layer.trail_level  # protective stop follows the trail

    def check_exit(self, layer: Layer, bar_high: float, bar_low: float) -> Optional[Tuple[str, float]]:
        """Returns (exit_reason, exit_price) if the bar takes out SL or trailing TP."""
        if layer.sign > 0:
            if bar_low <= layer.sl:
                return ("TRAIL_TP" if layer.trail_active and layer.sl > layer.initial_sl else "SL", layer.sl)
        else:
            if bar_high >= layer.sl:
                return ("TRAIL_TP" if layer.trail_active and layer.sl < layer.initial_sl else "SL", layer.sl)
        return None
