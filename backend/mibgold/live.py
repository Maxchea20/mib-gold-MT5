"""Live paper/real execution loop. Polls the adapter at ~10Hz, pushes to WebSocket subscribers, acts on M5 closes."""
from __future__ import annotations
import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
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
from .journal import close_record
from .bars_cache import load_m1, merge_live, upsert_m1

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
        min_risk_usd = float(os.environ.get("MIN_RISK_USD", "10.0"))
        max_risk_usd = float(os.environ.get("MAX_RISK_USD", "100.0"))
        allocation = ClampedAllocation(min_usd=min_risk_usd, max_usd=max_risk_usd)
        self.risk = RiskManager(self.spec, budget_pct=budget, max_layers=max_layers, allocation=allocation)
        # Hard TP book: do not let trail steal the $5 target.
        self.book = PositionBook(self.spec, self.risk, TrailingTP(TrailingConfig(activate_r=999)), float(acc["balance"]),
                                 mode="live" if adapter.name == "mt5" else "paper")
        self.fixed_lots = float(os.environ.get("FIXED_LOTS", "0.02"))
        self.sl_dollars = float(os.environ.get("SL_DOLLARS", "2"))
        self.tp_dollars = float(os.environ.get("TP_DOLLARS", "5"))
        self.brain = TradeBrain(dead_min=float(os.environ.get("DEAD_FILL_MIN", "20")),
                                dead_r=float(os.environ.get("DEAD_FILL_R", "0.15")))
        session_thr_env = os.environ.get("SESSION_THRESHOLDS")
        session_min_env = os.environ.get("SESSION_MIN_ALIGNED_OVERRIDE")
        session_thresholds = json.loads(session_thr_env) if session_thr_env else None
        session_min_aligned = json.loads(session_min_env) if session_min_env else None
        cfg = StrategyConfig()
        cfg.bias_min_score = float(os.environ.get("BIAS_MIN_SCORE", cfg.bias_min_score))
        cfg.struct_oppose_score = float(os.environ.get("STRUCT_OPPOSE_SCORE", cfg.struct_oppose_score))
        self.strategy = TopDownStrategy(EngineSuite(), Consensus(session_threshold=session_thresholds, session_min_aligned=session_min_aligned), cfg)
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
        log.info("m1 history rows=%s live=%s cached=%s symbol=%s",
                 0 if m1 is None else len(m1),
                 0 if live_m1 is None else len(live_m1),
                 0 if cached is None else len(cached),
                 self._symbol())
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
            "session": self.analysis.get("session"), "account": snap,
            "today_pnl": round(today, 2), "today_pnl_text": ("Floating +" if today >= 0 else "Floating -") + f"${abs(today):,.2f}",
            "news": self.gate_state, "advisory": self.interpreter.current(self.tick.time) if self.tick else None,
            "analysis": self.analysis, "m5_atr": round(self.m5_atr, 3), "last_m5": self.last_m5.isoformat() if self.last_m5 else None,
            "book_rules": {"layers": self.risk.max_layers, "lot": self.fixed_lots, "sl": self.sl_dollars, "tp": self.tp_dollars},
            "theses": [t.to_dict() for t in self.brain.theses.values()],
        }

    def _tick_payload(self) -> dict:
        price = self.tick.mid
        snap = self.book.snapshot(price)
        today = snap["balance"] - self.day_start_balance + snap["floating_pnl"]
        return {"type": "tick", "tick": self.tick.to_dict(), "equity": snap["equity"], "balance": snap["balance"],
                "floating_pnl": snap["floating_pnl"], "risk_used_pct": snap["risk_used_pct"], "risk_used_usd": snap["risk_used_usd"],
                "today_pnl": round(today, 2), "layers": snap["layers"], "news": self.gate_state,
                "theses": [t.to_dict() for t in self.brain.theses.values()]}

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
        prev_sl = {l.id: l.sl for l in self.book.layers}
        for rec in self.book.on_bar(tick.ask, tick.bid, tick.mid, self.m5_atr, now):
            await self._closed(rec)
        if self.adapter.name == "mt5":
            for l in self.book.layers:
                if l.ticket and prev_sl.get(l.id) != l.sl:
                    self.adapter.modify_sl(l.ticket, round(l.sl, self.spec.digits))
        await self.broadcast(self._tick_payload())

    async def _on_minute(self, minute: datetime, now: datetime):
        first = self.last_minute is None
        self.last_minute = minute
        self.gate_state = self.gate.check(now)
        await self.interpreter.poll(now)
        if self.book.layers or first or minute.minute % 5 == 0:
            self.rebuild_frames(minute)
        if self.book.layers and self.tick:
            await self._review_open(now)
        if first or minute.minute % 5 == 0:
            await self._on_m5_close(minute, now)
        await self.broadcast({"type": "bars", "bars": {tf: self.chart(tf, 2) for tf in TFS}, "news": self.gate_state})

    async def _review_open(self, now: datetime):
        price = self.tick.mid
        for layer in list(self.book.layers):
            rev = self.brain.review(layer, price, now, self.spec.contract_size)
            self._log(f"THESIS L{layer.layer_number} {rev['action']} {rev['age_min']}m r={rev['r']:+.2f}")
            if rev["action"] == "time_stop":
                px = self.tick.bid if layer.sign > 0 else self.tick.ask
                if self.adapter.name == "mt5" and layer.ticket:
                    self.adapter.close_position(layer.ticket, layer.lots, layer.direction)
                rec = self.book.close_layer(layer, px, "TIME_STOP", now)
                await self._closed(rec)
            await self.broadcast({"type": "thesis", "review": rev})

    async def _on_m5_close(self, minute: datetime, now: datetime):
        self.last_m5 = minute
        advisory = self.interpreter.current(now)
        self.analysis = self.strategy.analyze(self.frames, now, self.spec, advisory)
        blocked = self.analysis["gate_reason"]
        opened = None
        if self.analysis["fire"] and self.gate_state["blocked"]:
            blocked = f"News gate active: {self.gate_state['event']['title']}"
        elif self.analysis["fire"] and not self.auto_trade:
            blocked = "Auto-trade paused by operator"
        elif self.analysis["fire"] and self.tick:
            prop = self.strategy.propose_entry(self.analysis, self.frames, self.book, self.spec, self.tick.bid, self.tick.ask)
            if prop and (not prop.get("blocked") or self.fixed_lots):
                direction = prop.get("direction") or self.analysis.get("bias", {}).get("direction")
                entry = self.tick.ask if direction == "long" else self.tick.bid
                sl = entry - self.sl_dollars if direction == "long" else entry + self.sl_dollars
                tp = entry + self.tp_dollars if direction == "long" else entry - self.tp_dollars
                lots = self.fixed_lots
                risk_usd = lots * self.sl_dollars * self.spec.contract_size
                order = self.adapter.place_order(direction, lots, sl)
                if order.get("ok"):
                    entry = order.get("price") or entry
                    sl = entry - self.sl_dollars if direction == "long" else entry + self.sl_dollars
                    tp = entry + self.tp_dollars if direction == "long" else entry - self.tp_dollars
                    opened = self.book.open_layer(direction, entry, sl, lots, risk_usd, now,
                                                  self.analysis["votes"], self.analysis["entry"], self.analysis["summary"],
                                                  self.analysis["session"], self.analysis["bias"], ticket=order.get("ticket"), tp=tp)
                    self.brain.open_thesis(opened, self.analysis)
                    rec = self.book.open_records(self.tick.mid)[-1]
                    self._log(f"OPEN L{opened.layer_number} {opened.direction} {lots} @ {entry:.2f} SL {sl:.2f} TP {tp:.2f} | {self.analysis['summary']}")
                    await self.broadcast({"type": "trade_opened", "trade": rec, "thesis": self.brain.theses[opened.id].to_dict()})
                else:
                    blocked = f"Order rejected: {order}"
            elif prop:
                blocked = prop["blocked"]
        self.analysis["gate_reason"] = blocked
        self.analysis["executed"] = opened.id if opened else None
        await self.broadcast({"type": "analysis", "analysis": self.analysis, "layers": self.book.open_records(self.tick.mid if self.tick else 0)})

    async def _closed(self, rec: dict):
        self.brain.close(rec.get("id"), self.tick.time if self.tick else datetime.utcnow(), rec.get("exit_reason", ""))
        self._log(f"CLOSE L{rec['layer_number']} {rec['direction']} {rec['exit_reason']} @ {rec['exit_price']} -> {rec['r_text']} / {rec['pnl_text']}")
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
