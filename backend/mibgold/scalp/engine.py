"""Scalp V1 single interface for live and backtest. Manager never opens."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional
from .config import ScalpConfig
from . import core


def _hour(ts: int) -> int:
    return datetime.utcfromtimestamp(int(ts)).hour


@dataclass
class Thesis:
    setup_id: str
    direction: str
    level_name: str
    level: float
    sweep_px: float
    entry: float
    sl: float
    invalid_px: float
    opened_ts: int
    mfe: float = 0.0
    mae: float = 0.0


class Engine:
    def __init__(self, cfg: Optional[ScalpConfig] = None, log: Optional[Callable[[str], None]] = None):
        self.cfg = cfg or ScalpConfig()
        self.log = log or (lambda m: None)
        self.events: List[Dict] = []
        self.seq = 0
        self.thesis: Optional[Thesis] = None
        self.failed_keys = set()
        self.stats = {"scanned": 0, "rejected": 0, "fired": 0, "exits": 0, "reject_reasons": {}}

    def _ev(self, kind: str, **kw):
        rec = {"kind": kind, **kw}
        self.events.append(rec)
        if len(self.events) > 4000:
            self.events = self.events[-3000:]
        self.log(f"{kind}: {rec.get('reason') or kind}")
        return rec

    def _reject(self, reason: str, extra: Optional[dict] = None) -> Dict:
        self.stats["rejected"] += 1
        self.stats["reject_reasons"][reason] = self.stats["reject_reasons"].get(reason, 0) + 1
        body = {"action": "WAIT", "fire": False, "reason": reason}
        self._ev("SETUP_REJECTED", reason=reason)
        if extra:
            body.update(extra)
        return body

    def evaluate(self, frames: dict, now, spread: float = 0.0) -> Dict:
        self.stats["scanned"] += 1
        m1 = core.rows(frames.get("M1")) if hasattr(frames.get("M1"), "iterrows") else (frames.get("M1") or [])
        m5 = core.rows(frames.get("M5")) if hasattr(frames.get("M5"), "iterrows") else (frames.get("M5") or [])
        m15 = core.rows(frames.get("M15")) if hasattr(frames.get("M15"), "iterrows") else (frames.get("M15") or [])
        d1 = core.rows(frames.get("D1")) if hasattr(frames.get("D1"), "iterrows") else (frames.get("D1") or [])
        if len(m15) < 30 or len(m5) < 30 or len(m1) < 30:
            return self._reject("Need more closed candles")
        atr5 = core.atr(m5)
        atr1 = core.atr(m1)
        if atr5 <= 0 or atr1 <= 0:
            return self._reject("ATR not ready")
        prior = core.atr(m5[:-20]) or atr5
        vol_ratio = atr5 / prior
        if vol_ratio > 2.2:
            return self._reject("CHAOS: extreme 5M ATR expansion", {"state": "CHAOS"})
        last5, last1 = m5[-1], m1[-1]
        sess = core.session_name(_hour(last5["ts"]))
        locs = core.locations(m15, d1, m5, self.cfg.swing_k)
        if not locs:
            return self._reject("No location map yet")
        manage = self.manage(last1, atr1) if self.thesis else None
        setup = self._scan_setup(m1, m5, locs, atr5, atr1, last5, last1, sess, spread, vol_ratio)
        setup["manage"] = manage
        setup["atr_1m"] = atr1
        setup["atr_5m"] = atr5
        setup["session"] = sess
        setup["version"] = self.cfg.version
        return setup

    def _scan_setup(self, m1, m5, locs, atr5, atr1, last5, last1, sess, spread, vol_ratio) -> Dict:
        cfg = self.cfg
        candidates = []
        for loc in locs:
            px = loc["price"]
            if loc["side"] == "sup" and last5["low"] <= px + cfg.level_touch_atr * atr5:
                candidates.append((loc, "long"))
            if loc["side"] == "res" and last5["high"] >= px - cfg.level_touch_atr * atr5:
                candidates.append((loc, "short"))
        if not candidates:
            return self._reject("15M/session location not being probed")
        loc, side = candidates[-1]
        level = float(loc["price"])
        key = f"{side}|{loc['name']}|{round(level, 1)}"
        if key in self.failed_keys:
            return self._reject(f"OLD SETUP {key} already failed")
        if side == "long":
            sweep_px = last5["low"]
            penetration = level - sweep_px
        else:
            sweep_px = last5["high"]
            penetration = sweep_px - level
        if penetration < cfg.min_sweep_atr * atr5:
            return self._reject("Sweep penetration too small", {"location": loc, "side": side})
        if penetration > cfg.max_sweep_atr * atr5:
            return self._reject("Sweep penetration too large / runaway", {"location": loc, "side": side})
        window = m5[-cfg.reclaim_max_bars:]
        if side == "long":
            reclaimed = any(b["close"] > level for b in window) and last5["close"] > level
        else:
            reclaimed = any(b["close"] < level for b in window) and last5["close"] < level
        if not reclaimed:
            return self._reject("Sweep seen but 5M has not reclaimed the level", {"location": loc, "side": side})
        br = core.bos(m5, side, cfg.swing_k)
        if not br:
            return self._reject("Reclaim without 5M structure break", {"location": loc, "side": side})
        impulse = abs(last5["close"] - sweep_px)
        if impulse <= 0:
            return self._reject("Impulse size is 0")
        if side == "long":
            pb_depth = (max(c["high"] for c in m1[-12:]) - last1["low"]) / impulse
        else:
            pb_depth = (last1["high"] - min(c["low"] for c in m1[-12:])) / impulse
        if pb_depth > cfg.max_pullback_frac:
            return self._reject("1M pullback exceeded maximum structural depth", {"pb_depth": round(pb_depth, 3)})
        cont = core.bos(m1, side, cfg.swing_k)
        if not cont:
            return self._reject("Waiting 1M continuation after pullback", {"location": loc, "side": side, "stage": "PULLBACK_1M"})
        rv = core.rvol(m5)
        if rv < cfg.min_rvol:
            return self._reject(f"Volume participation weak rvol={rv:.2f}")
        if spread and atr5 and (spread / atr5) > cfg.max_spread_atr_5m:
            return self._reject(f"Spread too wide vs ATR ({spread:.3f}/{atr5:.3f})")
        if side == "long":
            invalid = sweep_px
            sl = invalid - cfg.sl_buffer_atr_1m * atr1
            sl_dist = last1["close"] - sl
        else:
            invalid = sweep_px
            sl = invalid + cfg.sl_buffer_atr_1m * atr1
            sl_dist = sl - last1["close"]
        min_sl = cfg.min_sl_atr_1m * atr1
        if sl_dist < min_sl:
            return self._reject(f"Structural SL too tight ({sl_dist:.3f} < {min_sl:.3f})")
        entry = last1["close"]
        self.seq += 1
        sid = f"SV1-{side[0].upper()}-{last1['ts']}-{self.seq}"
        self.stats["fired"] += 1
        self._ev("SETUP_ACCEPTED", reason=f"{sid} {side} {loc['name']} @{level:.2f} entry={entry:.2f} sl={sl:.2f}", setup_id=sid, session=sess)
        return {
            "action": "FIRE", "fire": True, "direction": side, "entry": entry, "stop": sl,
            "invalid_px": invalid, "level": level, "level_name": loc["name"], "setup_id": sid,
            "structure_key": key, "session": sess, "rvol": rv, "vol_ratio": vol_ratio,
            "reason": f"VALID {side.upper()} sweep-reclaim-BOS-pullback-continuation",
            "why_state": [f"15M/loc {loc['name']} {level:.2f}", f"5M sweep {penetration:.2f}", "5M reclaim", f"5M {br['event']}", "1M pullback", "1M continuation"],
        }

    def on_open(self, setup: Dict, fill: float, sl: float, ts: int):
        self.thesis = Thesis(setup.get("setup_id") or "", setup["direction"], setup.get("level_name") or "",
                             float(setup.get("level") or fill), float(setup.get("invalid_px") or sl),
                             fill, sl, float(setup.get("invalid_px") or sl), ts)

    def on_exit(self, rec: Dict, ts: int = 0):
        reason = str(rec.get("exit_reason") or "").upper()
        key = None
        if self.thesis:
            key = f"{self.thesis.direction}|{self.thesis.level_name}|{round(self.thesis.level, 1)}"
        if "SL" in reason or reason in ("STOP", "STOP_LOSS", "THESIS_FAIL"):
            if key:
                self.failed_keys.add(key)
            self._ev("THESIS_DEAD", reason=f"{key} {reason}")
        self.stats["exits"] += 1
        self.thesis = None

    def manage(self, bar: Dict, atr1: float) -> Dict:
        t = self.thesis
        if not t:
            return {"action": "FLAT"}
        px = bar["close"]
        fav = (px - t.entry) if t.direction == "long" else (t.entry - px)
        adv = (t.entry - px) if t.direction == "long" else (px - t.entry)
        t.mfe = max(t.mfe, fav)
        t.mae = max(t.mae, adv)
        failed = (t.direction == "long" and bar["close"] < t.invalid_px) or (t.direction == "short" and bar["close"] > t.invalid_px)
        if failed:
            return {"action": "EXIT", "reason": "THESIS_FAIL", "mfe": t.mfe, "mae": t.mae}
        return {"action": "HOLD", "mfe": t.mfe, "mae": t.mae, "setup_id": t.setup_id}
