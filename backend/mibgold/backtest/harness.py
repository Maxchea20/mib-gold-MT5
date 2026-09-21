"""Bar-by-bar walk-forward. C-Fast V2 door, 1:3 RR, Lab trail on."""
from __future__ import annotations
import threading
from typing import Callable, Dict, Optional
import numpy as np
import pandas as pd
from ..adapters.resample import all_frames, RULES
from ..book import PositionBook
from ..consensus import Consensus
from ..contracts import new_id, utcnow
from ..engines import EngineSuite
from ..engines.utils import atr as atr_series
from ..news.calendar import NewsGate
from ..risk import RiskManager, SymbolSpec, ClampedAllocation
from ..strategy import TopDownStrategy, StrategyConfig
from ..trailing import TrailingTP
from .attribution import attribution, summary_stats
from ..hunt.hunt_c_fast import frames_to_candles
from ..hunt.cfast_v2 import CFastV2
from ..session import session_for

TFS = ("M5", "M15", "H1", "H4", "D1")


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
        self.sl_dollars = sl_dollars
        self.tp_dollars = tp_dollars
        risk = RiskManager(spec, budget_pct=budget_pct, max_layers=max_layers,
                            allocation=ClampedAllocation(min_usd=min_risk_usd, max_usd=max_risk_usd))
        self.book = PositionBook(spec, risk, TrailingTP(), start_balance, mode="backtest")
        cfg = StrategyConfig()
        if bias_min_score is not None:
            cfg.bias_min_score = bias_min_score
        if struct_oppose_score is not None:
            cfg.struct_oppose_score = struct_oppose_score
        consensus = Consensus(weights, session_threshold=session_thresholds, session_min_aligned=session_min_aligned)
        self.strategy = TopDownStrategy(EngineSuite(), consensus, cfg)
        self.id = new_id("BT")
        self.progress = 0.0
        self.status = "pending"
        self.error: Optional[str] = None
        self.bars: list = []
        self.equity_curve: list = []
        self.result: Optional[dict] = None
        self._stop = False
        self.cfast = CFastV2()

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
        m5 = frames["M5"]
        ends = {tf: pd.DatetimeIndex(frames[tf]["time"] + pd.Timedelta(RULES[tf])) for tf in TFS[1:]}
        m5_atr = atr_series(m5)
        n = len(m5)
        half_spread = self.spec.spread_price / 2
        for i in range(self.warmup, n):
            if self._stop:
                break
            bar = m5.iloc[i]
            now = (bar["time"] + pd.Timedelta(minutes=5)).to_pydatetime()
            hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            a = float(m5_atr[i]) if not np.isnan(m5_atr[i]) else 1.0
            closed = self.book.on_bar(hi, lo, close, a, now, slippage=self.slippage)
            now_ts = int(pd.Timestamp(now).timestamp())
            for rec in closed:
                self.cfast.on_exit(rec, now_ts)
            window = {"M5": m5.iloc[max(0, i - 260):i + 1]}
            for tf in TFS[1:]:
                k = int(ends[tf].searchsorted(pd.Timestamp(now), side="right"))
                window[tf] = frames[tf].iloc[max(0, k - 400):k]
            session = session_for(now)
            hunt = {"action": "WAIT", "why_state": ["no hunt"]}
            try:
                c15 = frames_to_candles(window.get("M15"))
                c5 = frames_to_candles(window.get("M5"))
                c1 = frames_to_candles(window.get("H1"))
                c4 = frames_to_candles(window.get("H4"))
                if c15 and c5:
                    parent = c5[-1]["ts"] - (c5[-1]["ts"] % 900)
                    live5 = [b for b in c5 if b["ts"] >= parent] or [c5[-1]]
                    hunt = self.cfast.evaluate(c15, c5[-1], live_5ms=live5, candles_4h=c4, candles_1h=c1, candles_5m=c5)
            except Exception as e:
                hunt = {"action": "WAIT", "why_state": [f"hunt error: {e}"]}
            analysis = {"session": session, "bias": {"direction": (hunt.get("direction") or "neutral")},
                        "votes": {}, "entry": {"direction": hunt.get("direction"), "score": 0},
                        "summary": " | ".join(hunt.get("why_state") or []), "fire": hunt.get("action") == "FIRE",
                        "gate_reason": None if hunt.get("action") == "FIRE" else (hunt.get("why_state") or ["WAIT"])[0],
                        "hunt": hunt}
            gate = self.gate.check(now) if self.gate else {"blocked": False}
            opened = None
            blocked_reason = analysis["gate_reason"]
            if self.book.layers:
                blocked_reason = blocked_reason or "clip open"
            elif analysis["fire"] and gate["blocked"]:
                blocked_reason = f"News gate: {gate['event']['title']}"
            elif analysis["fire"]:
                direction = (hunt.get("direction") or "").lower()
                if direction in ("long", "short") and hunt.get("entry") and hunt.get("stop"):
                    raw_entry = float(hunt["entry"])
                    entry = raw_entry + self.slippage * (1 if direction == "long" else -1)
                    sl_dist = float(self.sl_dollars) if self.sl_dollars else abs(entry - float(hunt["stop"]))
                    sl, tp = self.cfast.apply_fixed_rr(entry, sl_dist, direction)
                    lots = float(self.fixed_lots) if self.fixed_lots else 0.02
                    sl_dist = abs(entry - sl)
                    if lots > 0 and sl_dist > 0:
                        risk_usd = lots * sl_dist * self.spec.contract_size
                        opened = self.book.open_layer(direction, entry, sl, lots, risk_usd, now,
                                                      {}, analysis["entry"], analysis["summary"],
                                                      session, analysis["bias"], tp=tp)
                else:
                    blocked_reason = (hunt.get("why_state") or ["no levels"])[0]
            snap = self.book.snapshot(close)
            self.equity_curve.append({"time": now.isoformat(), "equity": snap["equity"], "balance": snap["balance"]})
            self.bars.append({
                "i": i, "time": now.isoformat(), "o": float(bar["open"]), "h": hi, "l": lo, "c": close,
                "session": session, "fire": analysis["fire"], "gate": blocked_reason,
                "hunt": hunt.get("brain_version"), "setup_id": hunt.get("setup_id"),
                "opened": opened.id if opened else None, "equity": snap["equity"],
            })
            self.progress = (i - self.warmup + 1) / max(1, n - self.warmup)
            if on_progress and i % 50 == 0:
                on_progress(self.progress)
        if len(m5):
            last = m5.iloc[-1]
            for layer in list(self.book.layers):
                self.book.close_layer(layer, float(last["close"]), "END_OF_DATA", (last["time"] + pd.Timedelta(minutes=5)).to_pydatetime())
        trades = self.book.closed
        self.result = {
            "id": self.id, "status": "done", "created": utcnow().isoformat(),
            "range": {"start": m5["time"].iloc[0].isoformat(), "end": m5["time"].iloc[-1].isoformat(), "m5_bars": int(n)},
            "config": {"book": "C-Fast V2", "start_balance": self.book.start_balance, "max_layers": self.book.risk.max_layers,
                       "budget_pct": self.book.risk.budget_pct, "spread": self.spec.spread_price, "slippage": self.slippage,
                       "fixed_lots": self.fixed_lots, "sl_dollars": self.sl_dollars, "tp_dollars": self.tp_dollars, "rr": "1:3", "trail": True},
            "stats": summary_stats(trades, self.book.start_balance),
            "attribution": attribution(trades, self.strategy.consensus.weights),
            "trades": trades,
            "equity_curve": self.equity_curve[::max(1, len(self.equity_curve) // 1500)],
            "final_balance": round(self.book.balance, 2),
            "cfast_v2": dict(self.cfast.stats),
        }


class BacktestRunner:
    def __init__(self):
        self.runs: Dict[str, Backtest] = {}
        self.order: list = []

    def start(self, bt: Backtest, on_progress=None) -> str:
        self.runs[bt.id] = bt
        self.order.append(bt.id)
        for old in self.order[:-3]:
            self.runs.pop(old, None)
        self.order = self.order[-3:]
        threading.Thread(target=bt.run, args=(on_progress,), daemon=True, name=f"bt-{bt.id}").start()
        return bt.id
