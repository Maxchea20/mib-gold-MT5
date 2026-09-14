"""Real MetaTrader5 adapter (Windows only). Imports the mt5 package lazily so the rest of the system runs anywhere."""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
import pandas as pd
from .base import DataAdapter, Tick
from ..risk import SymbolSpec

ORDER_COMMENT = "mib-gold"


def _mt5_path() -> Optional[str]:
    raw = os.environ.get("MT5_PATH") or ""
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        return None
    raw = raw.replace("\\", "/")
    p = Path(raw)
    if p.is_file():
        return str(p)
    guesses = [
        Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe"),
    ]
    for g in guesses:
        if g.is_file():
            return str(g)
    return str(p)


class MT5Adapter(DataAdapter):
    name = "mt5"

    def __init__(self, symbol: str | None = None):
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.symbol = symbol or os.environ.get("MT5_SYMBOL", "GOLD")
        self.server_offset = timedelta(hours=float(os.environ.get("MT5_SERVER_UTC_OFFSET_HOURS", "0")))
        self._spec: Optional[SymbolSpec] = None

    def connect(self) -> dict:
        kwargs = {}
        path = _mt5_path()
        if path:
            kwargs["path"] = path
        if os.environ.get("MT5_LOGIN"):
            kwargs.update(login=int(os.environ["MT5_LOGIN"]), password=os.environ.get("MT5_PASSWORD", ""),
                          server=os.environ.get("MT5_SERVER", ""))
        if not self.mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {self.mt5.last_error()} path={kwargs.get('path')}")
        if not self.mt5.symbol_select(self.symbol, True):
            raise RuntimeError(f"symbol_select({self.symbol}) failed: {self.mt5.last_error()}")
        info = self.mt5.terminal_info()._asdict()
        acc = self.account()
        return {"connected": True, "mode": "mt5", "terminal": info.get("name"), "build": info.get("build"),
                "account": acc, "symbol": self.symbol_spec().to_dict()}

    def symbol_spec(self) -> SymbolSpec:
        if self._spec is None:
            si = self.mt5.symbol_info(self.symbol)
            if si is None:
                raise RuntimeError(f"symbol_info({self.symbol}) is None")
            self._spec = SymbolSpec(symbol=self.symbol, contract_size=si.trade_contract_size, min_lot=si.volume_min,
                                    lot_step=si.volume_step, max_lot=si.volume_max, digits=si.digits,
                                    spread_points=si.spread, point=si.point)
        return self._spec

    def account(self) -> dict:
        a = self.mt5.account_info()
        if a is None:
            raise RuntimeError("account_info() is None")
        return {"login": a.login, "server": a.server, "currency": a.currency, "balance": a.balance, "equity": a.equity,
                "leverage": a.leverage, "hedging": a.margin_mode == self.mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING}

    def _to_utc(self, series: pd.Series) -> pd.Series:
        return pd.to_datetime(series, unit="s", utc=True) - self.server_offset

    def _frame(self, rates) -> pd.DataFrame:
        if rates is None or len(rates) == 0:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])
        df = pd.DataFrame(rates)
        df["time"] = self._to_utc(df["time"])
        return df[["time", "open", "high", "low", "close", "tick_volume"]]

    def tick(self) -> Optional[Tick]:
        t = self.mt5.symbol_info_tick(self.symbol)
        if t is None:
            return None
        return Tick(datetime.fromtimestamp(t.time, tz=timezone.utc) - self.server_offset, t.bid, t.ask)

    def m1_history(self, bars: int) -> pd.DataFrame:
        want = max(200, min(int(bars or 8000), 100000))
        rates = self.mt5.copy_rates_from_pos(self.symbol, self.mt5.TIMEFRAME_M1, 1, want)
        if rates is None or len(rates) == 0:
            for n in (20000, 8000, 2000, 500):
                rates = self.mt5.copy_rates_from_pos(self.symbol, self.mt5.TIMEFRAME_M1, 1, n)
                if rates is not None and len(rates) > 0:
                    break
        return self._frame(rates)

    def m1_range(self, start: datetime, end: datetime) -> pd.DataFrame:
        rates = self.mt5.copy_rates_range(self.symbol, self.mt5.TIMEFRAME_M1, start + self.server_offset, end + self.server_offset)
        return self._frame(rates)

    def place_order(self, direction: str, lots: float, sl: float, comment: str = ORDER_COMMENT) -> dict:
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(self.symbol)
        buy = direction == "long"
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": float(lots),
            "type": mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if buy else tick.bid, "sl": float(sl), "tp": 0.0,
            "deviation": int(os.environ.get("MT5_DEVIATION_POINTS", "30")), "magic": 20260601,
            "comment": comment[:31], "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        ok = r is not None and r.retcode == mt5.TRADE_RETCODE_DONE
        return {"ok": ok, "ticket": getattr(r, "order", None), "price": getattr(r, "price", None),
                "retcode": getattr(r, "retcode", None), "comment": getattr(r, "comment", None)}

    def close_position(self, ticket, lots: float, direction: str) -> dict:
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(self.symbol)
        buy = direction == "long"
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": float(lots), "position": int(ticket),
               "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "price": tick.bid if buy else tick.ask,
               "deviation": 30, "magic": 20260601, "comment": "mib-gold close", "type_filling": mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req)
        return {"ok": r is not None and r.retcode == mt5.TRADE_RETCODE_DONE, "retcode": getattr(r, "retcode", None)}

    def modify_sl(self, ticket, sl: float) -> dict:
        mt5 = self.mt5
        r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": self.symbol, "position": int(ticket), "sl": float(sl), "tp": 0.0})
        return {"ok": r is not None and r.retcode == mt5.TRADE_RETCODE_DONE, "retcode": getattr(r, "retcode", None)}

    def positions(self) -> List[dict]:
        pos = self.mt5.positions_get(symbol=self.symbol) or []
        return [p._asdict() for p in pos]

    def shutdown(self):
        self.mt5.shutdown()
