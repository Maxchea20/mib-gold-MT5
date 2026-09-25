"""Real MetaTrader5 adapter (Windows only)."""
from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
import pandas as pd
from .base import DataAdapter, Tick
from ..risk import SymbolSpec
from ..servertime import HOUR, detect_offset_hours, fixed_offset_hours, ny_close_offset_hours

log = logging.getLogger("mibgold.mt5")
ORDER_COMMENT = "mib-gold"
MAGIC = 20260601


def _mt5_path() -> Optional[str]:
    raw = (os.environ.get("MT5_PATH") or "").strip().strip('"').strip("'")
    if not raw:
        return None
    p = Path(raw.replace("\\", "/"))
    if p.is_file():
        return str(p)
    for g in (
        Path(r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
        Path(r"C:\\Program Files (x86)\\MetaTrader 5\\terminal64.exe"),
    ):
        if g.is_file():
            return str(g)
    return str(p)


class MT5Adapter(DataAdapter):
    name = "mt5"

    def __init__(self, symbol: str | None = None):
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.symbol = symbol or os.environ.get("MT5_SYMBOL", "GOLD")
        self.fixed_offset = fixed_offset_hours()
        self.detected_offset: Optional[int] = None
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
        self.tick()
        log.info("MT5 server clock: fixed=%s detected=%s -> now UTC%+g",
                 self.fixed_offset, self.detected_offset, self.offset_hours(datetime.now(timezone.utc)))
        info = self.mt5.terminal_info()._asdict()
        return {"connected": True, "mode": "mt5", "terminal": info.get("name"), "build": info.get("build"),
                "account": self.account(), "symbol": self.symbol_spec().to_dict()}

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

    def offset_hours(self, utc: datetime) -> float:
        """Server clock offset at `utc`. Env pin wins; else New York close rule unless the live clock disagrees."""
        if self.fixed_offset is not None:
            return self.fixed_offset
        rule_now = ny_close_offset_hours(datetime.now(timezone.utc))
        if self.detected_offset is None or self.detected_offset == rule_now:
            return ny_close_offset_hours(utc)
        return self.detected_offset

    def _server_delta(self, server_secs: float) -> timedelta:
        return timedelta(hours=self.offset_hours(datetime.fromtimestamp(server_secs - 3 * HOUR, tz=timezone.utc)))

    def _utc_to_server(self, utc: datetime) -> datetime:
        return utc + timedelta(hours=self.offset_hours(utc))

    def _to_utc(self, series: pd.Series) -> pd.Series:
        t = pd.to_datetime(series, unit="s", utc=True)
        days = t.dt.floor("D")
        off = {d: self.offset_hours(d.to_pydatetime()) for d in days.unique()}
        return t - pd.to_timedelta(days.map(off), unit="h")

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
        if self.fixed_offset is None:
            det = detect_offset_hours(t.time, time.time())
            if det is not None and det != self.detected_offset:
                log.info("MT5 server clock detected at UTC%+d (was %s)", det, self.detected_offset)
                self.detected_offset = det
        return Tick(self._server_ts(t.time), t.bid, t.ask)

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
        rates = self.mt5.copy_rates_range(self.symbol, self.mt5.TIMEFRAME_M1, self._utc_to_server(start), self._utc_to_server(end))
        return self._frame(rates)

    def place_order(self, direction: str, lots: float, sl: float, comment: str = ORDER_COMMENT, tp: float = 0.0) -> dict:
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "comment": "no tick", "retcode": None}
        buy = (direction or "").lower() in ("long", "buy")
        price = float(tick.ask if buy else tick.bid)
        sl_dist = float(os.environ.get("SL_DOLLARS", "2.5"))
        tp_dist = float(os.environ.get("TP_DOLLARS", "5.0"))
        if sl is None:
            sl = price - sl_dist if buy else price + sl_dist
        sl = float(sl)
        if not tp:
            tp = price + tp_dist if buy else price - tp_dist
        tp = float(tp)
        digits = self.symbol_spec().digits
        sl, tp, price = round(sl, digits), round(tp, digits), round(price, digits)
        fillings = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
        last = {"ok": False}
        for filling in fillings:
            req = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": float(lots),
                "type": mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL,
                "price": price, "sl": sl, "tp": tp,
                "deviation": int(os.environ.get("MT5_DEVIATION_POINTS", "50")), "magic": MAGIC,
                "comment": (comment or ORDER_COMMENT)[:31], "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            r = mt5.order_send(req)
            last = {
                "ok": r is not None and r.retcode == mt5.TRADE_RETCODE_DONE,
                "ticket": getattr(r, "order", None) or getattr(r, "deal", None),
                "price": getattr(r, "price", None) or price,
                "retcode": getattr(r, "retcode", None),
                "comment": getattr(r, "comment", None),
                "last_error": self.mt5.last_error(),
                "sl": sl, "tp": tp,
            }
            log.info("order_send %s lots=%s sl=%s tp=%s filling=%s -> %s", direction, lots, sl, tp, filling, last)
            if last["ok"]:
                return last
        return last

    def close_position(self, ticket, lots: float, direction: str) -> dict:
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {"ok": False, "retcode": None, "comment": "no tick"}
        buy = direction == "long"
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": float(lots), "position": int(ticket),
               "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "price": tick.bid if buy else tick.ask,
               "deviation": 50, "magic": MAGIC, "comment": "mib-gold close", "type_filling": mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req)
        return {"ok": r is not None and r.retcode == mt5.TRADE_RETCODE_DONE, "retcode": getattr(r, "retcode", None),
                "price": getattr(r, "price", None), "comment": getattr(r, "comment", None)}

    def modify_sl(self, ticket, sl: float, tp: float = 0.0) -> dict:
        mt5 = self.mt5
        req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": self.symbol, "position": int(ticket), "sl": float(sl)}
        if tp:
            req["tp"] = float(tp)
        r = mt5.order_send(req)
        return {"ok": r is not None and r.retcode == mt5.TRADE_RETCODE_DONE, "retcode": getattr(r, "retcode", None)}

    def positions(self) -> List[dict]:
        pos = self.mt5.positions_get(symbol=self.symbol) or []
        return [p._asdict() for p in pos]

    def _server_ts(self, secs) -> datetime:
        return datetime.fromtimestamp(int(secs), tz=timezone.utc) - self._server_delta(secs)

    def own_positions(self) -> Optional[List[dict]]:
        pos = self.mt5.positions_get(symbol=self.symbol)
        if pos is None:
            log.warning("positions_get failed: %s", self.mt5.last_error())
            return None
        out = []
        for p in pos:
            if p.magic != MAGIC:
                continue
            out.append({"ticket": int(p.ticket), "direction": "long" if p.type == self.mt5.POSITION_TYPE_BUY else "short",
                        "lots": float(p.volume), "entry": float(p.price_open), "sl": float(p.sl) or None,
                        "tp": float(p.tp) or None, "time": self._server_ts(p.time)})
        return out

    def closed_deal(self, ticket) -> Optional[dict]:
        deals = self.mt5.history_deals_get(position=int(ticket))
        if not deals:
            return None
        exits = [d for d in deals if d.entry in (self.mt5.DEAL_ENTRY_OUT, self.mt5.DEAL_ENTRY_OUT_BY)]
        if not exits:
            return None
        d = exits[-1]
        reason = {getattr(self.mt5, "DEAL_REASON_SL", -1): "SL", getattr(self.mt5, "DEAL_REASON_TP", -1): "STRUCTURE_TP",
                  getattr(self.mt5, "DEAL_REASON_SO", -1): "STOP_OUT"}.get(d.reason, "BROKER_CLOSE")
        return {"price": float(d.price), "reason": reason, "time": self._server_ts(d.time),
                "profit": float(d.profit + d.commission + d.swap)}

    def realized_since(self, since: datetime) -> Optional[float]:
        deals = self.mt5.history_deals_get(self._utc_to_server(since), self._utc_to_server(datetime.now(timezone.utc)) + timedelta(days=1))
        if deals is None:
            return None
        return float(sum(d.profit + d.commission + d.swap for d in deals
                         if d.magic == MAGIC and d.entry in (self.mt5.DEAL_ENTRY_OUT, self.mt5.DEAL_ENTRY_OUT_BY)))

    def shutdown(self):
        self.mt5.shutdown()
