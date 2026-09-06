import os
from .base import DataAdapter, Tick
from .sim import SimAdapter


def make_adapter() -> DataAdapter:
    mode = os.environ.get("BROKER_MODE", "sim").lower()
    if mode == "mt5":
        from .mt5_adapter import MT5Adapter
        return MT5Adapter()
    return SimAdapter()
