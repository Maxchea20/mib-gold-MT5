"""Completed-M1 walk-forward. Same scalp.Engine as live."""
from __future__ import annotations
import threading
from typing import Callable, Dict, Optional
import pandas as pd
from ..adapters.resample import all_frames, RULES
from ..book import PositionBook
from ..contracts import new_id, utcnow
from ..news.calendar import NewsGate
from ..risk import RiskManager, SymbolSpec, ClampedAllocation
from ..trailing import TrailingTP
from .attribution import attribution, summary_stats
from ..session import session_for
from ..scalp import Engine, ScalpConfig

TFS = ("M1", "M5", "M15", "H1", "H4", "D1")


class Backtest:
    def __init__(self, m1: pd.DataFrame, spec: SymbolSpec, start_balance: float = 100.0, max_layers: int = 3,
                 budget_pct: float = 0.10, slippage_points: float = 5.0, warmup_bars: int = 300,
                 news_gate: Optional[NewsGate] = None, weights: Optional[dict] = None,
                 bias_min_score: Optional[float] = None, struct_oppose_score: Optional[float] = None,
                 session_thresholds: Optional[dict] = None, session_min_aligned: Optional[dict] = None,
                 min_risk_usd: float = 10.0, max_risk_usd: float = 100.0,
                 fixed_lots: Optional[float] = None, sl_dollars: Optional[float] = None, tp_dollars: Optional[float] = None):
        self.m1, self.spec = m1, spec
        self.slippage = slippage_points * spec.point
        self.warmup = warmup_bars
        self.gate = news_gate
        self.fixed_lots = fixed_lots
        risk = RiskManager(spec, budget_pct=budget_pct, max_layers=max_layers,
                           allocation=ClampedAllocation(min_usd=min_risk_usd, max_usd=max_risk_usd))
        self.book = PositionBook(spec, risk, TrailingTP(), start_balance, mode="backtest")
        self.id = new_id("BT")
        self.progress = 0.0
        self.status = "pending"
        self.error: Optional[str] = None
        self.bars: list = []
        self.equity_curve: list = []
        self.result: Optional[dict] = None
        self._stop = False
        self.engine = Engine(ScalpConfig())

    def stop(self):
        self._stop = True

    def run(self, on_progress: Optional[Callable[[float], None]] = None) -> dict:
        self.status = "running"
        try:
            self._run(on_progress)
            self.status = "done" if not self._stop else "stopped"
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"
            raise
        return self.result

    def _run(self, on_progress):
        frames = all_frames(self.m1, TFS)
        m1 = frames["M1"]
        ends = {tf: pd.DatetimeIndex(frames[tf]["time"] + pd.Timedelta(RULES[tf])) for tf in TFS if tf != "M1"}
        n = len(m1)
        warm = max(self.warmup, 400)
        event_log = []
        for i in range(warm, n):
            if self._stop:
                break
            bar = m1.iloc[i]
            now = (bar["time"] + pd.Timedelta(minutes=1)).to_pydatetime()
            hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            a = abs(hi - lo) or 0.3
            closed = self.book.on_bar(hi, lo, close, a, now, slippage=self.slippage)
            now_ts = int(pd.Timestamp(now).timestamp())
            for rec in closed:
                self.engine.on_exit(rec, now_ts)
            window = {"M1": m1.iloc[max(0, i - 400):i + 1]}
            for tf in TFS:
                if tf == "M1":
                    continue
                k = int(ends[tf].searchsorted(pd.Timestamp(now), side="right"))
                window[tf] = frames[tf].iloc[max(0, k - 400):k]
            session = session_for(now)
            decision = self.engine.evaluate(window, now, spread=self.spec.spread_price)
            event_log.append({"t": now.isoformat(), "action": decision.get("action"), "reason": decision.get("reason")})
            if len(event_log) > 8000:
                event_log = event_log[-4000:]
            gate = self.gate.check(now) if self.gate else {"blocked": False}
            opened = None
            blocked = None if decision.get("fire") else decision.get("reason")
            if self.book.layers:
                advice = decision.get("manage") or {}
                if advice.get("action") == "EXIT":
                    layer = self.book.layers[0]
                    self.book.close_layer(layer, close, "THESIS_FAIL", now)
                    self.engine.on_exit({"exit_reason": "THESIS_FAIL"}, now_ts)
                blocked = blocked or "clip open"
            elif decision.get("fire") and gate.get("blocked"):
                blocked = "News gate"
            elif decision.get("fire"):
                direction = decision["direction"]
                entry = float(decision["entry"]) + self.slippage * (1 if direction == "long" else -1)
                sl = float(decision["stop"])
                lots = float(self.fixed_lots) if self.fixed_lots else 0.02
                sl_dist = abs(entry - sl)
                if lots > 0 and sl_dist > 0:
                    risk_usd = lots * sl_dist * self.spec.contract_size
                    opened = self.book.open_layer(direction, entry, sl, lots, risk_usd, now,
                                                  {}, {"direction": direction}, decision.get("reason") or "SCALP_V1",
                                                  session, {"direction": direction}, tp=None)
                    self.engine.on_open(decision, entry, sl, now_ts)
            snap = self.book.snapshot(close)
            self.equity_curve.append({"time": now.isoformat(), "equity": snap["equity"], "balance": snap["balance"]})
            if opened or decision.get("fire") or i % 20 == 0:
                self.bars.append({
                    "i": i, "time": now.isoformat(), "h": hi, "l": lo, "c": close,
                    "session": session, "fire": bool(decision.get("fire")), "gate": blocked,
                    "setup_id": decision.get("setup_id"), "opened": opened.id if opened else None,
                    "equity": snap["equity"],
                })
            self.progress = (i - warm + 1) / max(1, n - warm)
            if on_progress and i % 400 == 0:
                on_progress(self.progress)
        if len(m1):
            last = m1.iloc[-1]
            for layer in list(self.book.layers):
                self.book.close_layer(layer, float(last["close"]), "END_OF_DATA",
                                      (last["time"] + pd.Timedelta(minutes=1)).to_pydatetime())
        trades = self.book.closed
        self.result = {
            "id": self.id, "status": "done", "created": utcnow().isoformat(),
            "range": {"start": str(m1["time"].iloc[0]), "end": str(m1["time"].iloc[-1]), "m1_bars": int(n)},
            "config": {"book": "Scalp V1 sweep-reclaim", "start_balance": self.book.start_balance,
                       "spread": self.spec.spread_price, "slippage": self.slippage,
                       "fixed_lots": self.fixed_lots, "params": dict(self.engine.cfg.__dict__)},
            "stats": summary_stats(trades, self.book.start_balance),
            "attribution": attribution(trades, {}),
            "trades": trades,
            "equity_curve": self.equity_curve[::max(1, len(self.equity_curve) // 1500)],
            "final_balance": round(self.book.balance, 2),
            "scalp_v1": dict(self.engine.stats),
            "reject_reasons": dict(self.engine.stats.get("reject_reasons") or {}),
            "event_tail": event_log[-500:],
        }


class BacktestRunner:
    def __init__(self):
        self.runs: Dict[str, Backtest] = {}
        self.order: list = []

    def start(self, bt: Backtest, on_progress=None) -> str:
        self.runs[bt.id] = bt
        self.order.append(bt.id)
        for old in self.order[:-8]:
            self.runs.pop(old, None)
        self.order = self.order[-8:]
        threading.Thread(target=bt.run, args=(on_progress,), daemon=True, name=f"bt-{bt.id}").start()
        return bt.id
