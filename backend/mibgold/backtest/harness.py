"""Bar-by-bar walk-forward harness. Same engines, consensus, risk, trailing and book as live."""
from __future__ import annotations
import threading
from datetime import timedelta
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

TFS = ("M5", "M15", "H1", "H4", "D1")


class Backtest:
    def __init__(self, m1: pd.DataFrame, spec: SymbolSpec, start_balance: float = 100.0, max_layers: int = 3,
                 budget_pct: float = 0.10, slippage_points: float = 5.0, warmup_bars: int = 300,
                 news_gate: Optional[NewsGate] = None, weights: Optional[dict] = None,
                 bias_min_score: Optional[float] = None, struct_oppose_score: Optional[float] = None,
                 session_thresholds: Optional[dict] = None, session_min_aligned: Optional[dict] = None,
                 min_risk_usd: float = 10.0, max_risk_usd: float = 100.0):
        self.m1, self.spec = m1, spec
        self.slippage = slippage_points * spec.point
        self.warmup = warmup_bars
        self.gate = news_gate
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
        self.bars: list = []          # per-bar replay frames for scrubbing
        self.equity_curve: list = []
        self.result: Optional[dict] = None
        self._stop = False

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
            window = {"M5": m5.iloc[max(0, i - 260):i + 1]}
            for tf in TFS[1:]:
                k = int(ends[tf].searchsorted(pd.Timestamp(now), side="right"))
                window[tf] = frames[tf].iloc[max(0, k - 260):k]
            analysis = self.strategy.analyze(window, now, self.spec)
            gate = self.gate.check(now) if self.gate else {"blocked": False}
            bid, ask = close - half_spread, close + half_spread
            opened = None
            blocked_reason = analysis["gate_reason"]
            if analysis["fire"] and gate["blocked"]:
                blocked_reason = f"News gate: {gate['event']['title']}"
            elif analysis["fire"]:
                prop = self.strategy.propose_entry(analysis, window, self.book, self.spec, bid, ask)
                if prop and not prop.get("blocked"):
                    entry = prop["entry"] + self.slippage * (1 if prop["direction"] == "long" else -1)
                    d = prop["decision"]
                    opened = self.book.open_layer(prop["direction"], entry, prop["sl"], d.lots, d.risk_usd, now,
                                                  analysis["votes"], analysis["entry"], analysis["summary"],
                                                  analysis["session"], analysis["bias"])
                elif prop:
                    blocked_reason = prop["blocked"]
            snap = self.book.snapshot(close)
            self.equity_curve.append({"time": now.isoformat(), "equity": snap["equity"], "balance": snap["balance"]})
            self.bars.append({
                "i": i, "time": now.isoformat(), "o": float(bar["open"]), "h": hi, "l": lo, "c": close, "v": int(bar["tick_volume"]),
                "session": analysis["session"], "bias": analysis["bias"]["direction"],
                "votes": {k: [v["signal"], v["confidence"], v["reason"]] for k, v in analysis["votes"].items()},
                "score": analysis["entry"].get("score", 0), "fire": analysis["fire"], "gate": blocked_reason,
                "opened": opened.id if opened else None, "closed": [c["id"] for c in closed],
                "layers": [{"id": l.id, "dir": l.direction, "entry": l.entry, "sl": l.sl, "trail": l.trail_level} for l in self.book.layers],
                "equity": snap["equity"],
            })
            self.progress = (i - self.warmup + 1) / max(1, n - self.warmup)
            if on_progress and i % 50 == 0:
                on_progress(self.progress)
        # flatten remaining layers at last close
        if len(m5):
            last = m5.iloc[-1]
            for layer in list(self.book.layers):
                self.book.close_layer(layer, float(last["close"]), "END_OF_DATA", (last["time"] + pd.Timedelta(minutes=5)).to_pydatetime())
        trades = self.book.closed
        self.result = {
            "id": self.id, "status": "done", "created": utcnow().isoformat(),
            "range": {"start": m5["time"].iloc[0].isoformat(), "end": m5["time"].iloc[-1].isoformat(), "m5_bars": int(n)},
            "config": {"start_balance": self.book.start_balance, "max_layers": self.book.risk.max_layers,
                       "budget_pct": self.book.risk.budget_pct, "spread": self.spec.spread_price, "slippage": self.slippage},
            "stats": summary_stats(trades, self.book.start_balance),
            "attribution": attribution(trades, self.strategy.consensus.weights),
            "trades": trades,
            "equity_curve": self.equity_curve[::max(1, len(self.equity_curve) // 1500)],
            "final_balance": round(self.book.balance, 2),
        }


class BacktestRunner:
    """Runs backtests in a background thread and keeps the last N in memory."""

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