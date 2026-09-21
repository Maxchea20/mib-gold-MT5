"""Research harness. V1 or CONT-H1 via book=."""
from __future__ import annotations
import bisect
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional
import pandas as pd
from ..adapters.resample import all_frames, RULES
from ..book import PositionBook
from ..contracts import new_id, utcnow
from ..news.calendar import NewsGate
from ..risk import RiskManager, SymbolSpec, ClampedAllocation
from ..session import session_for
from ..scalp.core import rows
from .pick import make_engine
from .research_stats import summarize, breakdown, conversions, realized

TFS = ("M1", "M5", "M15", "H1", "H4", "D1")
EVENT_DIR = Path(os.environ.get("MIBGOLD_EVENT_DIR", "backend/data"))
TF_SEC = {tf: int(pd.Timedelta(RULES[tf]).total_seconds()) for tf in TFS if tf != "M1"}


class StructuralOnly:
    def update(self, layer, price, atr):
        return None

    def check_exit(self, layer, high, low):
        if layer.sign > 0 and low <= layer.sl:
            return ("STRUCTURAL_SL", layer.sl)
        if layer.sign < 0 and high >= layer.sl:
            return ("STRUCTURAL_SL", layer.sl)
        return None


def _ts(x):
    if x is None:
        return None
    return pd.Timestamp(x)


class Backtest:
    def __init__(self, m1: pd.DataFrame, spec: SymbolSpec, start_balance: float = 100.0, max_layers: int = 1,
                 budget_pct: float = 0.10, slippage_points: float = 5.0, warmup_bars: int = 300,
                 news_gate: Optional[NewsGate] = None, weights=None, bias_min_score=None, struct_oppose_score=None,
                 session_thresholds=None, session_min_aligned=None, min_risk_usd: float = 10.0, max_risk_usd: float = 100.0,
                 fixed_lots: Optional[float] = None, sl_dollars=None, tp_dollars=None, test_cutoff=None,
                 book: str = "scalp_v1"):
        self.m1, self.spec = m1, spec
        self.slippage = slippage_points * spec.point
        self.warmup = warmup_bars
        self.gate = news_gate
        self.fixed_lots = fixed_lots
        self.test_cutoff = _ts(test_cutoff) if test_cutoff is not None else None
        self.book_key = book or "scalp_v1"
        risk = RiskManager(spec, budget_pct=budget_pct, max_layers=max_layers,
                           allocation=ClampedAllocation(min_usd=min_risk_usd, max_usd=max_risk_usd))
        self.book = PositionBook(spec, risk, StructuralOnly(), start_balance, mode="backtest")
        self.id = new_id("BT")
        self.progress = 0.0
        self.status = "pending"
        self.error: Optional[str] = None
        self.bars: list = []
        self.equity_curve: list = []
        self.result: Optional[dict] = None
        self._stop = False
        self.engine, self.book_label = make_engine(self.book_key)
        self._path = {}
        self._meta = {}
        self.processed_m1 = 0
        self.total_m1 = 0
        self.current_ts = None
        self.started_at = None
        self.runtime_sec = None
        self.warmup_fires = 0
        self.test_fires = 0

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

    def _in_test(self, now) -> bool:
        if self.test_cutoff is None:
            return True
        return pd.Timestamp(now) >= self.test_cutoff

    def _run(self, on_progress):
        t0 = time.time()
        self.started_at = t0
        frames = all_frames(self.m1, TFS)
        candles = {tf: rows(frames[tf]) for tf in TFS}
        ends = {tf: [c["ts"] + TF_SEC[tf] for c in candles[tf]] for tf in TF_SEC}
        m1c = candles["M1"]
        n = len(m1c)
        warm = max(int(self.warmup or 0), 400)
        if warm >= n:
            warm = max(400, n // 4)
        self.total_m1 = max(0, n - warm)
        first_eval = None
        EVENT_DIR.mkdir(parents=True, exist_ok=True)
        ev_path = EVENT_DIR / f"{self.id}_events.jsonl"
        ev_f = open(ev_path, "w", encoding="utf-8")
        buf = []
        try:
            for i in range(warm, n):
                if self._stop:
                    break
                bar = m1c[i]
                now_ts = int(bar["ts"] + 60)
                now = pd.Timestamp(now_ts, unit="s", tz="UTC").to_pydatetime()
                if first_eval is None:
                    first_eval = now
                hi, lo, close = bar["high"], bar["low"], bar["close"]
                a = abs(hi - lo) or 0.3
                for layer in self.book.layers:
                    st = self._path.setdefault(layer.id, {"mfe": 0.0, "mae": 0.0})
                    if layer.direction == "long":
                        st["mfe"] = max(st["mfe"], hi - layer.entry)
                        st["mae"] = max(st["mae"], layer.entry - lo)
                    else:
                        st["mfe"] = max(st["mfe"], layer.entry - lo)
                        st["mae"] = max(st["mae"], hi - layer.entry)
                closed = self.book.on_bar(hi, lo, close, a, now, slippage=self.slippage)
                for rec in closed:
                    self._stamp(rec, now)
                    self.engine.on_exit(rec, now_ts)
                window = {"M1": m1c[max(0, i - 400):i + 1]}
                for tf, endlist in ends.items():
                    k = bisect.bisect_right(endlist, now_ts)
                    window[tf] = candles[tf][max(0, k - 400):k]
                session = session_for(now)
                decision = self.engine.evaluate(window, now, spread=self.spec.spread_price)
                in_test = self._in_test(now)
                buf.append(json.dumps({"t": now.isoformat(), "action": decision.get("action"),
                                       "reason": decision.get("reason"), "code": decision.get("code"),
                                       "setup_id": decision.get("setup_id"), "session": session,
                                       "in_test": in_test}, default=str) + "\n")
                if len(buf) >= 250:
                    ev_f.writelines(buf)
                    buf.clear()
                gate = self.gate.check(now) if self.gate else {"blocked": False}
                opened = None
                if self.book.layers:
                    advice = decision.get("manage") or {}
                    if advice.get("action") == "EXIT":
                        layer = self.book.layers[0]
                        rec = self.book.close_layer(layer, close, "THESIS_FAIL", now)
                        self._stamp(rec, now)
                        self.engine.on_exit(rec, now_ts)
                elif decision.get("fire") and not gate.get("blocked"):
                    if not in_test:
                        self.warmup_fires += 1
                    else:
                        self.test_fires += 1
                        direction = decision["direction"]
                        entry = float(decision["entry"]) + self.slippage * (1 if direction == "long" else -1)
                        sl = float(decision["stop"])
                        lots = float(self.fixed_lots) if self.fixed_lots else 0.02
                        sl_dist = abs(entry - sl)
                        if lots > 0 and sl_dist > 0:
                            risk_usd = lots * sl_dist * self.spec.contract_size
                            opened = self.book.open_layer(direction, entry, sl, lots, risk_usd, now,
                                                          {}, {"direction": direction}, decision.get("reason") or self.book_label,
                                                          session, {"direction": direction}, tp=None)
                            self.engine.on_open(decision, entry, sl, now_ts)
                            self._meta[opened.id] = dict(decision.get("meta") or {})
                            self._meta[opened.id].update({
                                "setup_id": decision.get("setup_id"), "vol_bucket": decision.get("vol_bucket"),
                                "vwap": decision.get("vwap"), "session": session, "in_test": True,
                                "market_regime": decision.get("market_regime") or (decision.get("meta") or {}).get("market_regime"),
                            })
                            self._path[opened.id] = {"mfe": 0.0, "mae": 0.0}
                snap = self.book.snapshot(close)
                if opened or i % 30 == 0:
                    self.equity_curve.append({"time": now.isoformat(), "equity": snap["equity"], "balance": snap["balance"]})
                self.processed_m1 = i - warm + 1
                self.current_ts = now.isoformat()
                self.progress = self.processed_m1 / max(1, self.total_m1)
                if on_progress and i % 400 == 0:
                    on_progress(self.progress)
        finally:
            if buf:
                ev_f.writelines(buf)
            ev_f.close()
        if m1c:
            last = m1c[-1]
            end_ts = pd.Timestamp(int(last["ts"]) + 60, unit="s", tz="UTC").to_pydatetime()
            for layer in list(self.book.layers):
                rec = self.book.close_layer(layer, float(last["close"]), "END_OF_DATA", end_ts)
                rec["open_at_end"] = True
                self._stamp(rec, end_ts)
        self.runtime_sec = round(time.time() - t0, 3)
        trades = self.book.closed
        for t in trades:
            t["in_test"] = bool((self._meta.get(t.get("id")) or {}).get("in_test", True))
        fn = dict(self.engine.funnel)
        bps = round(self.processed_m1 / self.runtime_sec, 1) if self.runtime_sec else None
        loaded_start = str(self.m1["time"].iloc[0])
        loaded_end = str(self.m1["time"].iloc[-1])
        test_start = str(self.test_cutoff) if self.test_cutoff is not None else str(first_eval)
        rz = realized(trades)
        eod = [t for t in trades if str(t.get("exit_reason") or "").upper() == "END_OF_DATA"]
        first_test = None
        for t in rz:
            first_test = t.get("timestamp") or t.get("entry_timestamp")
            break
        params = dict(getattr(self.engine, "cfg", object()).__dict__) if hasattr(self.engine, "cfg") else {}
        self.result = {
            "id": self.id, "status": "done", "created": utcnow().isoformat(),
            "range": {"start": test_start, "end": loaded_end, "m1_bars": int(self.processed_m1)},
            "loaded_range": {"start": loaded_start, "end": loaded_end, "m1_bars": int(n)},
            "window": {
                "loaded_start": loaded_start, "loaded_end": loaded_end,
                "test_start": test_start, "test_end": loaded_end,
                "warmup_bars": warm, "first_evaluated_bar": str(first_eval),
                "first_test_trade": first_test,
                "warmup_fires": self.warmup_fires, "test_fires": self.test_fires,
                "end_of_data": len(eod), "book": self.book_label,
            },
            "config": {
                "book": self.book_label, "sl": "STRUCTURAL", "tp": "NONE", "trail": False,
                "start_balance": self.book.start_balance, "spread": self.spec.spread_price,
                "slippage": self.slippage, "fixed_lots": self.fixed_lots, "params": params,
            },
            "stats": summarize(trades, self.book.start_balance, self.equity_curve),
            "by_direction": breakdown(trades, "direction"),
            "by_session": breakdown(trades, "session"),
            "by_volatility": breakdown(trades, "vol_bucket"),
            "funnel": fn, "conversions": conversions(fn),
            "reject_codes": dict(self.engine.stats.get("reject_codes") or {}),
            "reject_reasons": dict(self.engine.stats.get("reject_reasons") or {}),
            "trades": trades,
            "realized_trades": rz,
            "end_of_data_trades": eod,
            "equity_curve": self.equity_curve[::max(1, len(self.equity_curve) // 1500)],
            "final_balance": round(self.book.balance, 2),
            "event_file": str(ev_path),
            "event_lines": self.processed_m1,
            "runtime_sec": self.runtime_sec,
            "m1_processed": self.processed_m1,
            "m1_per_sec": bps,
        }

    def _stamp(self, rec: dict, now):
        lid = rec.get("id")
        st = self._path.get(lid) or {}
        meta = self._meta.get(lid) or {}
        entry = float(rec.get("entry") or 0)
        sl0 = float(rec.get("initial_sl") or rec.get("sl") or 0)
        risk = abs(entry - sl0) or 1e-9
        mfe = float(st.get("mfe") or 0)
        mae = float(st.get("mae") or 0)
        t0 = rec.get("timestamp")
        try:
            hold = (pd.Timestamp(now) - pd.Timestamp(t0)).total_seconds()
        except Exception:
            hold = None
        rec.update({
            "trade_id": lid, "setup_id": meta.get("setup_id"),
            "entry_timestamp": rec.get("timestamp"), "exit_timestamp": rec.get("exit_time"),
            "location_type": meta.get("location_type"), "location_price": meta.get("location_price"),
            "vwap": meta.get("vwap"), "vol_bucket": meta.get("vol_bucket"),
            "market_regime": meta.get("market_regime"),
            "initial_structural_sl": sl0, "final_sl": rec.get("sl"), "risk_distance": risk,
            "mfe": round(mfe, 4), "mae": round(mae, 4),
            "mfe_r": round(mfe / risk, 4), "mae_r": round(mae / risk, 4),
            "holding_time_seconds": hold,
            "holding_time_minutes": None if hold is None else round(hold / 60.0, 3),
            "tp_mode": "none", "in_test": bool(meta.get("in_test", True)),
        })


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
