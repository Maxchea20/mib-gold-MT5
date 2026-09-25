"""Replay the live rules (Hunt C pullback + C-Fast V2.1) minute by minute on an MT5 M1 export.

Mirrors live.py: one clip, fill at market inside the no-chase band, fixed-dollar SL/TP,
calendar cuts, dead-fill time-stop, daily loss limit. Longs exit on bid, shorts on ask;
if one bar touches both SL and TP it counts as SL. Not modelled: news gate, commission.
Plain Python (no pandas):

    python -m mibgold.backtest.replay_live data/GOLD#_M1_....csv
    python -m mibgold.backtest.replay_live data/GOLD#_M1_....csv --sl 3 --tp 6 --no-time-stop
"""
from __future__ import annotations
import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..hunt.cfast_v2 import CFastV2
from ..servertime import server_to_utc_ts
from ..session import session_for


def load_mt5_csv(path: str) -> List[dict]:
    """MT5 'Export bars' file (<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>), server time."""
    out = []
    with open(path) as f:
        rows = csv.reader(f, delimiter="\t")
        head = [c.strip("<>").lower() for c in next(rows)]
        ix = {k: head.index(k) for k in ("date", "time", "open", "high", "low", "close")}
        iv = head.index("tickvol") if "tickvol" in head else None
        isp = head.index("spread") if "spread" in head else None
        for r in rows:
            if not r:
                continue
            srv = datetime.strptime(r[ix["date"]] + " " + r[ix["time"]], "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append({"ts": server_to_utc_ts(int(srv.timestamp())), "open": float(r[ix["open"]]),
                        "high": float(r[ix["high"]]), "low": float(r[ix["low"]]), "close": float(r[ix["close"]]),
                        "volume": float(r[iv]) if iv is not None else 0.0,
                        "spread": int(r[isp]) * 0.01 if isp is not None else 0.30})
    out.sort(key=lambda b: b["ts"])
    return out


class _Agg:
    """Completed bars of one timeframe, built from M1 as time passes."""

    def __init__(self, secs: int, keep: int):
        self.secs, self.keep, self.done, self.cur = secs, keep, [], None

    def roll(self, now: int):
        if self.cur and now >= self.cur["ts"] + self.secs:
            self.done.append(self.cur)
            self.done = self.done[-self.keep:]
            self.cur = None

    def add(self, b: dict):
        start = b["ts"] - b["ts"] % self.secs
        self.roll(start)
        if self.cur is None:
            self.cur = {k: b[k] for k in ("open", "high", "low", "close", "volume")} | {"ts": start}
        else:
            c = self.cur
            c["high"], c["low"], c["close"] = max(c["high"], b["high"]), min(c["low"], b["low"]), b["close"]
            c["volume"] += b["volume"]


def replay(bars: List[dict], lots: float = 0.02, sl: float = 2.5, tp: float = 5.0, contract: float = 100.0,
           cuts: bool = True, blocked_sessions=("london",), blocked_weekdays=(4,), blocked_hours=(19,),
           time_stop: bool = True, dead_min: float = 45, dead_r: float = 0.15,
           max_daily_loss: Optional[float] = None) -> List[dict]:
    m5, m15, h1, h4 = _Agg(300, 600), _Agg(900, 300), _Agg(3600, 200), _Agg(14400, 120)
    cf = CFastV2()
    limit = max_daily_loss if max_daily_loss is not None else 3 * lots * sl * contract
    pos: Optional[dict] = None
    trades: List[dict] = []
    day, day_pnl = None, 0.0

    def close(px: float, reason: str, now: int):
        nonlocal pos, day_pnl
        pnl = (px - pos["entry"]) * pos["sign"] * lots * contract
        trades.append(dict(pos, exit=px, reason=reason, pnl=pnl, minutes=(now - pos["ts"]) / 60))
        day_pnl += pnl
        cf.on_exit({"exit_reason": reason, "direction": pos["direction"], "entry": pos["entry"]}, now)
        pos = None

    for b in bars:
        now = b["ts"]
        for a in (m5, m15, h1, h4):
            a.roll(now)
        t = datetime.fromtimestamp(now, timezone.utc)
        if t.date() != day:
            day, day_pnl = t.date(), 0.0
        bid, ask = b["open"], b["open"] + b["spread"]

        if pos and time_stop:
            px = bid if pos["sign"] > 0 else ask
            if (now - pos["ts"]) / 60 >= dead_min and (px - pos["entry"]) * pos["sign"] / sl < dead_r:
                close(px, "TIME_STOP", now)

        if pos is None and len(m15.done) >= 40 and m5.done:
            c5 = m5.done
            parent = c5[-1]["ts"] - c5[-1]["ts"] % 900
            live = [x for x in c5 if x["ts"] >= parent]
            hunt = cf.evaluate(m15.done, c5[-1], live_5ms=live or [c5[-1]], candles_4h=h4.done,
                               candles_1h=h1.done, candles_5m=c5)
            if hunt.get("action") == "FIRE":
                session = session_for(t)
                direction, level = hunt["direction"], float(hunt["entry"])
                px = ask if direction == "long" else bid
                band = max(0.40, float(hunt.get("atr_15m") or 0) * 0.25)
                late = (direction == "long" and px > level + 0.15) or (direction == "short" and px < level - 0.15)
                cut = cuts and (t.weekday() in blocked_weekdays or t.hour in blocked_hours or session in blocked_sessions)
                if cut or day_pnl <= -limit or late or abs(px - level) > band:
                    cf.active = None
                else:
                    sign = 1 if direction == "long" else -1
                    pos = {"direction": direction, "sign": sign, "entry": px, "sl": px - sign * sl,
                           "tp": px + sign * tp, "ts": now, "session": session, "weekday": t.weekday(), "hour": t.hour}

        if pos:
            if pos["sign"] > 0:
                if b["low"] <= pos["sl"]:
                    close(pos["sl"], "SL", now)
                elif b["high"] >= pos["tp"]:
                    close(pos["tp"], "TP", now)
            else:
                if b["high"] + b["spread"] >= pos["sl"]:
                    close(pos["sl"], "SL", now)
                elif b["low"] + b["spread"] <= pos["tp"]:
                    close(pos["tp"], "TP", now)
        for a in (m5, m15, h1, h4):
            a.add(b)
    return trades


def summary(trades: List[dict]) -> Dict:
    n = len(trades)
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    eq = peak = dd = 0.0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {"trades": n, "win_pct": round(100 * len(wins) / n, 1) if n else 0.0,
            "net_usd": round(sum(t["pnl"] for t in trades), 2),
            "profit_factor": round(sum(wins) / sum(losses), 2) if losses else None,
            "max_drawdown_usd": round(dd, 2)}


def breakdown(trades: List[dict], key: str) -> Dict:
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t["pnl"])
    return {k: {"trades": len(v), "net_usd": round(sum(v), 2)} for k, v in sorted(g.items())}


def _env_tuple(name, default, cast=str):
    raw = os.environ.get(name, default)
    return tuple(cast(x.strip().lower() if cast is str else x.strip()) for x in raw.split(",") if x.strip())


def main():
    p = argparse.ArgumentParser(description="Replay the live rules on an MT5 M1 export")
    p.add_argument("csv")
    p.add_argument("--lots", type=float, default=float(os.environ.get("FIXED_LOTS", "0.02")))
    p.add_argument("--sl", type=float, default=float(os.environ.get("SL_DOLLARS", "2.5")))
    p.add_argument("--tp", type=float, default=float(os.environ.get("TP_DOLLARS", "5.0")))
    p.add_argument("--dead-min", type=float, default=float(os.environ.get("DEAD_FILL_MIN", "45")))
    p.add_argument("--max-daily-loss", type=float, default=float(os.environ.get("MAX_DAILY_LOSS_USD") or 0) or None)
    p.add_argument("--no-cuts", action="store_true")
    p.add_argument("--no-time-stop", action="store_true")
    a = p.parse_args()
    bars = load_mt5_csv(a.csv)
    trades = replay(bars, lots=a.lots, sl=a.sl, tp=a.tp, dead_min=a.dead_min, max_daily_loss=a.max_daily_loss,
                    cuts=not a.no_cuts, time_stop=not a.no_time_stop,
                    blocked_sessions=_env_tuple("BLOCKED_SESSIONS", "london"),
                    blocked_weekdays=_env_tuple("BLOCKED_WEEKDAYS", "4", int),
                    blocked_hours=_env_tuple("BLOCKED_HOURS_UTC", "19", int))
    first, last = (datetime.fromtimestamp(bars[i]["ts"], timezone.utc) for i in (0, -1))
    print(f"{len(bars)} M1 bars, {first:%Y-%m-%d} to {last:%Y-%m-%d} UTC")
    print(f"lots {a.lots}  SL ${a.sl}  TP ${a.tp}  cuts {not a.no_cuts}  "
          f"time-stop {'off' if a.no_time_stop else f'{a.dead_min:g}m'}")
    print("summary   ", summary(trades))
    for key in ("reason", "session", "direction", "weekday"):
        print(f"by {key:9s}", breakdown(trades, key))


if __name__ == "__main__":
    main()
