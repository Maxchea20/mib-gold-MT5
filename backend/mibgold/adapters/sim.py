from __future__ import annotations
import os
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional
import numpy as np
import pandas as pd
from .base import DataAdapter, Tick
from ..risk import SymbolSpec
from ..session import session_for

SESSION_VOL = {"asian": 0.55, "london": 1.0, "ny_overlap": 1.35, "ny": 0.95, "off": 0.4}


def synth_gold_m1(start: datetime, minutes: int, seed: int = 7, start_price: float = 2350.0) -> pd.DataFrame:
    """Realistic-ish XAUUSD M1: session-scaled vol, regime-switching drift, fat tails, tick-volume proxy."""
    rng = np.random.default_rng(seed)
    times = pd.date_range(start, periods=minutes, freq="1min", tz="UTC")
    times = times[times.weekday < 5]  # market closed at weekends; path stays continuous across the gap
    minutes = len(times)
    base_sigma = 0.00035  # per-minute log vol ~ 0.035%
    drift = 0.0
    prices = np.empty(minutes)
    vols = np.empty(minutes)
    p = start_price
    for i, t in enumerate(times):
        if i % 240 == 0:  # regime switch every 4h
            drift = rng.choice([-1, 0, 0, 1]) * rng.uniform(0.00002, 0.00006)
        sv = SESSION_VOL[session_for(t.to_pydatetime())]
        shock = rng.standard_t(4) * base_sigma * sv
        if rng.random() < 0.0015:  # news-like jump
            shock += rng.choice([-1, 1]) * rng.uniform(4, 9) * base_sigma
        p *= np.exp(drift + shock)
        prices[i] = p
        vols[i] = max(5, rng.poisson(120 * sv) + abs(shock) / base_sigma * 40)
    close = prices
    open_ = np.roll(close, 1)
    open_[0] = start_price
    wick = np.abs(rng.normal(0, 0.25, minutes)) * np.abs(close - open_) + rng.uniform(0.02, 0.2, minutes)
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.25, minutes)) * np.abs(close - open_) - rng.uniform(0.02, 0.2, minutes)
    df = pd.DataFrame({"time": times, "open": open_, "high": high, "low": low, "close": close, "tick_volume": vols.astype(int)})
    return df.round({"open": 2, "high": 2, "low": 2, "close": 2})


def load_csv(path: str) -> pd.DataFrame:
    """Accepts MT5 'Export bars' TSV (<DATE> <TIME> <OPEN>...) or plain time,open,high,low,close,tick_volume CSV."""
    sep = "\t" if path.lower().endswith((".tsv", ".txt")) else None
    df = pd.read_csv(path, sep=sep, engine="python")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        df["time"] = pd.to_datetime(df["date"] + " " + df["time"], utc=True)
        df = df.rename(columns={"tickvol": "tick_volume"})
    else:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    if "tick_volume" not in df.columns:
        df["tick_volume"] = df.get("volume", 100)
    return df[["time", "open", "high", "low", "close", "tick_volume"]].sort_values("time").reset_index(drop=True)


class SimAdapter(DataAdapter):
    """Synthetic or CSV-replayed gold feed with an accelerated clock. Same interface as MT5Adapter."""
    name = "sim"

    def __init__(self, speed: float | None = None, history_days: int = 120, csv_path: str | None = None, seed: int = 7):
        self.speed = speed if speed is not None else float(os.environ.get("SIM_SPEED", "30"))
        self.spec = SymbolSpec(symbol="XAUUSD", contract_size=100, min_lot=0.01, lot_step=0.01, digits=2, spread_points=30, point=0.01)
        self.balance = float(os.environ.get("SIM_START_BALANCE", "100"))
        csv_path = csv_path or os.environ.get("SIM_CSV_PATH")
        if csv_path and os.path.exists(csv_path):
            self.data = load_csv(csv_path)
            self.source = f"csv:{os.path.basename(csv_path)}"
        else:
            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            start = now - timedelta(days=history_days)
            self.data = synth_gold_m1(start, (history_days + 10) * 1440, seed=seed)
            self.source = "synthetic"
        # replay cursor begins at "history end" so the UI starts with a full chart
        anchor_ts = datetime.now(timezone.utc) if self.source == "synthetic" else self.data["time"].iloc[int(len(self.data) * 0.7)].to_pydatetime()
        self._cursor0 = int(self.data["time"].searchsorted(pd.Timestamp(anchor_ts)))
        self._cursor0 = min(max(self._cursor0, 300), len(self.data) - 2)
        self._t0_real = _time.time()
        self._t0_sim = self.data["time"].iloc[self._cursor0].to_pydatetime()
        self._rng = np.random.default_rng(seed + 1)

    def connect(self) -> dict:
        return {"connected": True, "mode": "sim", "source": self.source, "speed": self.speed, "bars": len(self.data)}

    def symbol_spec(self) -> SymbolSpec:
        return self.spec

    def account(self) -> dict:
        return {"login": 0, "server": "SIM", "currency": "USD", "balance": self.balance, "leverage": 500, "hedging": True}

    def now(self) -> datetime:
        return self._t0_sim + timedelta(seconds=(_time.time() - self._t0_real) * self.speed)

    def _cursor(self) -> int:
        idx = int(self.data["time"].searchsorted(pd.Timestamp(self.now()), side="right")) - 1
        return min(max(idx, 0), len(self.data) - 1)

    def tick(self) -> Optional[Tick]:
        i = self._cursor()
        row = self.data.iloc[i]
        frac = ((self.now() - row["time"].to_pydatetime()).total_seconds() / 60.0) % 1.0
        # path inside the bar: open -> extreme -> other extreme -> close
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        pts = [o, h if c >= o else l, l if c >= o else h, c]
        seg = min(int(frac * 3), 2)
        f = frac * 3 - seg
        mid = pts[seg] + (pts[seg + 1] - pts[seg]) * f + self._rng.normal(0, 0.03)
        spr = self.spec.spread_price
        return Tick(self.now(), round(mid - spr / 2, 2), round(mid + spr / 2, 2))

    def m1_history(self, bars: int) -> pd.DataFrame:
        i = self._cursor()  # bars strictly completed before now
        return self.data.iloc[max(0, i - bars):i].reset_index(drop=True)

    def m1_range(self, start: datetime, end: datetime) -> pd.DataFrame:
        m = (self.data["time"] >= pd.Timestamp(start)) & (self.data["time"] < pd.Timestamp(end))
        return self.data[m].reset_index(drop=True)

    def sim_news_events(self):
        """Synthetic high-impact USD events along the replay timeline so the hard gate is exercised in sim."""
        from ..news.calendar import NewsEvent
        t0 = self.now().replace(second=0, microsecond=0)
        evs = [NewsEvent("US Non-Farm Payrolls (SIM)", "USD", t0 + timedelta(minutes=12), "High", "180K", "175K", "", "sim")]
        for d in range(1, 12):
            day = (t0 + timedelta(days=d)).replace(hour=12, minute=30)
            evs.append(NewsEvent(["US CPI m/m (SIM)", "FOMC Statement (SIM)", "US PPI m/m (SIM)"][d % 3], "USD", day, "High", "0.3%", "0.2%", "", "sim"))
        return evs

    def full_history(self) -> pd.DataFrame:
        return self.data
