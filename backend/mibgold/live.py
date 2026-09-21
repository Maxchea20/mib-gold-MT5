"""Live: Hunt C + C-Fast V2.1 keys. Gold collar SL 2.5 / TP 5. No trail."""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime
from typing import Callable, Awaitable, Dict, Optional
import pandas as pd
from .adapters.base import DataAdapter, Tick
from .adapters.resample import all_frames, completed_only
from .book import PositionBook
from .brain import TradeBrain
from .consensus import Consensus
from .engines import EngineSuite
from .engines.utils import safe_atr
from .news import NewsGate, NewsInterpreter
from .risk import RiskManager, ClampedAllocation
from .strategy import TopDownStrategy, StrategyConfig
from .trailing import TrailingTP, TrailingConfig
from .bars_cache import load_m1, merge_live, upsert_m1
from .hunt.hunt_c_fast import frames_to_candles
from .hunt.cfast_v2 import CFastV2

log = logging.getLogger("mibgold.live")
TFS = ("M5", "M15", "H1", "H4", "D1")


class LiveEngine:
    def __init__(self, adapter: DataAdapter, gate: NewsGate, interpreter: NewsInterpreter,
                 broadcast: Callable[[dict], Awaitable[None]], persist: Callable[[dict], Awaitable[None]]):
        self.adapter, self.gate, self.interpreter = adapter, gate, interpreter
        self.broadcast, self.persist = broadcast, persist
        self.connection = adapter.connect()
        self.spec = adapter.symbol_spec()
        acc = adapter.account()
        max_layers = int(os.environ.get("MAX_LAYERS", "1"))
        budget = float(os.environ.get("RISK_BUDGET_PCT", "0.10"))
        allocation = ClampedAllocation(
            min_usd=float(os.environ.get("MIN_RISK_USD", "10.0")),
            max_usd=float(os.environ.get("MAX_RISK_USD", "100.0")),
        )
        self.risk = RiskManager(self.spec, budget_pct=budget, max_layers=max_layers, allocation=allocation)
        self.book = PositionBook(self.spec, self.risk, TrailingTP(TrailingConfig(activate_r=999)), float(acc["balance"]),
                                 mode="live" if adapter.name == "mt5" else "paper")
        self.fixed_lots = float(os.environ.get("FIXED_LOTS", "0.01"))
        self.sl_dollars = float(os.environ.get("SL_DOLLARS", "2.5"))
        self.tp_dollars = float(os.environ.get("TP_DOLLARS", "5.0"))
        self.brain = TradeBrain(dead_min=float(os.environ.get("DEAD_FILL_MIN", "2")),
                                dead_r=float(os.environ.get("DEAD_FILL_R", "0.15")))
        self.cfast = CFastV2(log=lambda m: self._log(m))
        self.last_exit_at: Optional[datetime] = None
        self.strategy = TopDownStrategy(EngineSuite(), Consensus(), StrategyConfig())
        self.auto_trade = os.environ.get("AUTO_TRADE", "true").lower() == "true"
        self.history_bars = int(os.environ.get("HISTORY_M1_BARS", "50000"))
        self.tick: Optional[Tick] = None
        self.frames: Dict[str, pd.DataFrame] = {}
        self.analysis: dict = {}
        self.gate_state: dict = {"blocked": False}
        self.last_minute: Optional[datetime] = None
        self.last_m5: Optional[datetime] = None
        self.m5_atr: float = 1.0
        self.day_start_balance = self.book.balance
        self.day: Optional[datetime.date] = None
        self.events: list = []
        self.started = False

    def _symbol(self) -> str:
        return getattr(self.adapter, "symbol", None) or self.spec.symbol

    def rebuild_frames(self, now: datetime) -> None:
        live_m1 = self.adapter.m1_history(self.history_bars)
        cached = load_m1(self._symbol(), self.history_bars)
        m1 = merge_live(cached, live_m1)
        if m1 is None or m1.empty:
            self.frames = {}
            return
        try:
            upsert_m1(self._symbol(), live_m1.tail(3000) if live_m1 is not None and not live_m1.empty else m1.tail(0))
        except Exception:
            log.exception("bar cache write failed")
        frames = all_frames(m1, TFS)
        cut = pd.Timestamp(now.replace(second=0, microsecond=0))
        if cut.tzinfo is None:
            cut = cut.tz_localize("UTC")
        self.frames = {tf: completed_only(df, tf, cut) if tf != "M1" else df for tf, df in frames.items()}
        if len(self.frames.get("M5", [])) > 20:
            self.m5_atr = safe_atr(self.frames["M5"].tail(60))

    def chart(self, tf: str, n: int = 400) -> list:
        df = self.frames.get(tf)
        if df is None or df.empty:
            return []
        rows = df.tail(n)
        return [{"time": int(t.timestamp()), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": int(v)}
                for t, o, h, l, c, v in zip(rows["time"], rows["open"], rows["high"], rows["low"], rows["close"], rows["tick_volume"])]

    def status(self) -> dict:
        price = self.tick.mid if self.tick else 0.0
        snap = self.book.snapshot(price)
        today = snap["balance"] - self.day_start_balance + snap["floating_pnl"]
        return {
            "connection": self.connection, "mode": self.book.mode, "auto_trade": self.auto_trade,
            "symbol": self.spec.to_dict(), "tick": self.tick.to_dict() if self.tick else None,
            "session": self.analysis.get("session"), "account": snap, "today_pnl": round(today, 2),
            "news": self.gate_state, "analysis": self.analysis, "m5_atr": round(self.m5_atr, 3),
            "last_m5": self.last_m5.isoformat() if self.last_m5 else None,
            "book_rules": {"layers": self.risk.max_layers, "lot": self.fixed_lots,
                           "sl": self.sl_dollars, "tp": self.tp_dollars, "trail": False},
            "theses": [t.to_dict() for t in self.brain.theses.values()],
        }

    def _tick_payload(self) -> dict:
        price = self.tick.mid
        snap = self.book.snapshot(price)
        today = snap["balance"] - self.day_start_balance + snap["floating_pnl"]
        return {"type": "tick", "tick": self.tick.to_dict(), "equity": snap["equity"], "balance": snap["balance"],
                "floating_pnl": snap["floating_pnl"], "today_pnl": round(today, 2), "layers": snap["layers"],
                "news": self.gate_state, "theses": [t.to_dict() for t in self.brain.theses.values()]}

    async def run(self):
        self.started = True
        poll = float(os.environ.get("TICK_POLL_MS", "100")) / 1000
        while True:
            try:
                await self.step()
            except Exception as e:
                log.exception("live step failed: %s", e)
                await self.broadcast({"type": "error", "message": str(e)})
                await asyncio.sleep(1)
            await asyncio.sleep(poll)

    async def step(self):
        tick = self.adapter.tick()
        if tick is None:
            return
        self.tick = tick
        now = tick.time
        if self.day != now.date():
            self.day, self.day_start_balance = now.date(), self.book.balance
        minute = now.replace(second=0, microsecond=0)
        if self.last_minute is None or minute > self.last_minute:
            await self._on_minute(minute, now)
        for rec in self.book.on_bar(tick.ask, tick.bid, tick.mid, self.m5_atr, now):
            if self.adapter.name == "mt5" and rec.get("ticket"):
                try:
                    self.adapter.close_position(rec["ticket"], rec.get("lots") or self.fixed_lots, rec.get("direction"))
                except Exception:
                    log.exception("mt5 close after book exit")
            await self._closed(rec)
        await self.broadcast(self._tick_payload())

    async def _on_minute(self, minute: datetime, now: datetime):
        self.last_minute = minute
        self.last_m5 = minute
        self.gate_state = self.gate.check(now)
        await self.interpreter.poll(now)
        self.rebuild_frames(minute)
        await self._decide(now)
        await self.broadcast({"type": "bars", "bars": {tf: self.chart(tf, 2) for tf in TFS}, "news": self.gate_state})

    def _run_hunt(self):
        c15 = frames_to_candles(self.frames.get("M15"))
        c5 = frames_to_candles(self.frames.get("M5"))
        c1 = frames_to_candles(self.frames.get("H1"))
        c4 = frames_to_candles(self.frames.get("H4"))
        if not c15 or not c5:
            return {"action": "WAIT", "why_state": ["Hunt C needs M15/M5"]}
        parent = c5[-1]["ts"] - (c5[-1]["ts"] % 900)
        live = [b for b in c5 if b["ts"] >= parent]
        return self.cfast.evaluate(c15, c5[-1], live_5ms=live or [c5[-1]], candles_4h=c4, candles_1h=c1, candles_5m=c5)

    def _sl_tp(self, fill: float, direction: str):
        if direction == "long":
            return fill - self.sl_dollars, fill + self.tp_dollars
        return fill + self.sl_dollars, fill - self.tp_dollars

    async def _decide(self, now: datetime):
        self.analysis = self.strategy.analyze(self.frames, now, self.spec, self.interpreter.current(now))
        hunt = self._run_hunt()
        self.analysis["hunt"] = hunt
        if hunt.get("action") == "FIRE":
            self.analysis["fire"] = True
            self.analysis["gate_reason"] = None
            self.analysis["summary"] = " | ".join(hunt.get("why_state") or ["Hunt C"])
            self.analysis.setdefault("bias", {})["direction"] = hunt.get("direction")
        else:
            self.analysis["fire"] = False
            self.analysis["gate_reason"] = (hunt.get("why_state") or ["WAIT"])[0]
        blocked = self.analysis["gate_reason"]
        opened = None
        if self.book.layers:
            blocked = blocked or "clip already open"
        elif hunt.get("action") == "FIRE" and self.gate_state.get("blocked"):
            blocked = f"News gate: {self.gate_state.get('event', {}).get('title')}"
        elif hunt.get("action") == "FIRE" and not self.auto_trade:
            blocked = "Auto-trade paused by operator"
        elif hunt.get("action") == "FIRE" and self.tick:
            direction = (hunt.get("direction") or "").lower()
            level = float(hunt.get("entry") or 0)
            live_px = float(self.tick.ask if direction == "long" else self.tick.bid)
            band = max(0.40, float(hunt.get("atr_15m") or 0) * 0.25)
            if abs(live_px - level) > band:
                blocked = f"live {live_px:.2f} left 15m level {level:.2f} (band {band:.2f}) - no chase"
                self._log(blocked)
                self.cfast.active = None
            elif direction in ("long", "short") and level:
                sl, tp = self._sl_tp(level, direction)
                lots = self.fixed_lots
                try:
                    order = self.adapter.place_order(direction, lots, sl, tp=tp)
                except Exception as e:
                    order = {"ok": False, "comment": str(e)}
                    self.cfast.active = None
                if order.get("ok"):
                    fill = float(order.get("price") or level)
                    sl, tp = self._sl_tp(fill, direction)
                    risk_usd = lots * self.sl_dollars * self.spec.contract_size
                    opened = self.book.open_layer(direction, fill, sl, lots, risk_usd, now,
                                                  {}, {"direction": direction}, "Hunt C + V2.1",
                                                  self.analysis.get("session"), self.analysis.get("bias") or {},
                                                  ticket=order.get("ticket"), tp=tp)
                    self.brain.open_thesis(opened, self.analysis)
                    rec = self.book.open_records(self.tick.mid)[-1]
                    self._log(
                        f"OPEN HuntC+V21 {hunt.get('setup_id') or hunt.get('event')} {direction} {lots} "
                        f"@ LVL {level:.2f} FILL {fill:.2f} SL {sl:.2f} TP {tp:.2f} "
                        f"path={(hunt.get('hunt') or {}).get('m5_path')}"
                    )
                    await self.broadcast({"type": "trade_opened", "trade": rec, "thesis": self.brain.theses[opened.id].to_dict()})
                else:
                    self.cfast.active = None
                    blocked = f"Order rejected: {order}"
                    self._log(blocked)
            else:
                blocked = (hunt.get("why_state") or ["no Hunt C setup"])[0]
        self.analysis["gate_reason"] = blocked
        self.analysis["executed"] = opened.id if opened else None
        await self.broadcast({"type": "analysis", "analysis": self.analysis,
                              "layers": self.book.open_records(self.tick.mid if self.tick else 0)})

    async def _closed(self, rec: dict):
        self.last_exit_at = self.tick.time if self.tick else datetime.utcnow()
        ts = int(self.last_exit_at.timestamp()) if self.last_exit_at else 0
        self.cfast.on_exit(rec, ts)
        self.brain.close(rec.get("id"), self.last_exit_at, rec.get("exit_reason", ""))
        self._log(f"CLOSE L{rec.get('layer_number')} {rec.get('direction')} {rec.get('exit_reason')} @ {rec.get('exit_price')}")
        await self.persist(rec)
        await self.broadcast({"type": "trade_closed", "trade": rec})

    async def close_layer_manual(self, layer_id: str) -> Optional[dict]:
        for layer in self.book.layers:
            if layer.id == layer_id and self.tick:
                px = self.tick.bid if layer.sign > 0 else self.tick.ask
                if self.adapter.name == "mt5" and layer.ticket:
                    self.adapter.close_position(layer.ticket, layer.lots, layer.direction)
                rec = self.book.close_layer(layer, px, "MANUAL", self.tick.time)
                await self._closed(rec)
                return rec
        return None

    def _log(self, msg: str):
        log.info(msg)
        self.events.append({"time": self.tick.time.isoformat() if self.tick else None, "msg": msg})
        self.events = self.events[-200:]
