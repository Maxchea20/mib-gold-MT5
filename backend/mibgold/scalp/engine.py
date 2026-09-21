"""Scalp V1. Frozen parameters. Funnel + coded rejects for Lab research."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional
from .config import ScalpConfig
from . import core

CODES = {
    "Need more closed candles": "NO_CANDLES",
    "ATR not ready": "NO_ATR",
    "CHAOS: extreme 5M ATR expansion": "CHAOS",
    "No location map yet": "NO_LOCATION",
    "15M/session location not being probed": "NO_LOCATION",
    "Sweep penetration too small": "SWEEP_TOO_SMALL",
    "Sweep penetration too large / runaway": "SWEEP_TOO_LARGE",
    "Sweep seen but 5M has not reclaimed the level": "RECLAIM_TIMEOUT",
    "Reclaim without 5M structure break": "NO_BOS",
    "Impulse size is 0": "NO_IMPULSE",
    "1M pullback exceeded maximum structural depth": "PULLBACK_TOO_DEEP",
    "Waiting 1M continuation after pullback": "NO_CONTINUATION",
}


def _hour(ts: int) -> int:
    return datetime.utcfromtimestamp(int(ts)).hour


def _code(reason: str) -> str:
    if reason.startswith("OLD SETUP"):
        return "OLD_SETUP"
    if reason.startswith("Volume participation"):
        return "RVOL_TOO_LOW"
    if reason.startswith("Spread too wide"):
        return "SPREAD_TOO_HIGH"
    if reason.startswith("Structural SL too tight"):
        return "SL_TOO_TIGHT"
    return CODES.get(reason, "OTHER")


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
    meta: dict = field(default_factory=dict)


class Engine:
    def __init__(self, cfg: Optional[ScalpConfig] = None, log: Optional[Callable[[str], None]] = None):
        self.cfg = cfg or ScalpConfig()
        self.log = log or (lambda m: None)
        self.events: List[Dict] = []
        self.seq = 0
        self.thesis: Optional[Thesis] = None
        self.failed_keys = set()
        self.stats = {"scanned": 0, "rejected": 0, "fired": 0, "exits": 0, "reject_reasons": {}, "reject_codes": {}}
        self.funnel = {
            "locations_detected": 0, "sweeps_detected": 0, "reclaims_detected": 0,
            "bos_5m_detected": 0, "pullbacks_detected": 0, "continuations_detected": 0,
            "spread_passed": 0, "fires": 0,
        }

    def _ev(self, kind: str, **kw):
        rec = {"kind": kind, **kw}
        self.events.append(rec)
        self.log(f"{kind}: {rec.get('reason') or kind}")
        return rec

    def _reject(self, reason: str, extra: Optional[dict] = None) -> Dict:
        self.stats["rejected"] += 1
        self.stats["reject_reasons"][reason] = self.stats["reject_reasons"].get(reason, 0) + 1
        code = _code(reason)
        self.stats["reject_codes"][code] = self.stats["reject_codes"].get(code, 0) + 1
        self._ev("SETUP_REJECTED", reason=reason, code=code)
        body = {"action": "WAIT", "fire": False, "reason": reason, "code": code}
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
        bucket = core.vol_bucket(vol_ratio)
        if vol_ratio > 2.2:
            return self._reject("CHAOS: extreme 5M ATR expansion", {"state": "CHAOS", "vol_bucket": bucket})
        last5, last1 = m5[-1], m1[-1]
        sess = core.session_name(_hour(last5["ts"]))
        vwap = core.session_vwap(m1, last1["ts"])
        locs = core.locations(m15, d1, m5, m1=m1, k=self.cfg.swing_k, now_ts=last1["ts"])
        if locs:
            self.funnel["locations_detected"] += 1
        if not locs:
            return self._reject("No location map yet")
        manage = self.manage(last1, atr1) if self.thesis else None
        setup = self._scan_setup(m1, m5, locs, atr5, atr1, last5, last1, sess, spread, vol_ratio, vwap, bucket)
        setup["manage"] = manage
        setup["atr_1m"] = atr1
        setup["atr_5m"] = atr5
        setup["session"] = sess
        setup["vwap"] = vwap
        setup["vol_bucket"] = bucket
        setup["version"] = self.cfg.version
        return setup

    def _scan_setup(self, m1, m5, locs, atr5, atr1, last5, last1, sess, spread, vol_ratio, vwap, bucket) -> Dict:
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
        self.funnel["sweeps_detected"] += 1
        window = m5[-cfg.reclaim_max_bars:]
        if side == "long":
            reclaimed = any(b["close"] > level for b in window) and last5["close"] > level
        else:
            reclaimed = any(b["close"] < level for b in window) and last5["close"] < level
        if not reclaimed:
            return self._reject("Sweep seen but 5M has not reclaimed the level", {"location": loc, "side": side})
        self.funnel["reclaims_detected"] += 1
        br = core.bos(m5, side, cfg.swing_k)
        if not br:
            return self._reject("Reclaim without 5M structure break", {"location": loc, "side": side})
        self.funnel["bos_5m_detected"] += 1
        impulse = abs(last5["close"] - sweep_px)
        if impulse <= 0:
            return self._reject("Impulse size is 0")
        if side == "long":
            pb_depth = (max(c["high"] for c in m1[-12:]) - last1["low"]) / impulse
        else:
            pb_depth = (last1["high"] - min(c["low"] for c in m1[-12:])) / impulse
        if pb_depth > cfg.max_pullback_frac:
            return self._reject("1M pullback exceeded maximum structural depth", {"pb_depth": round(pb_depth, 3)})
        self.funnel["pullbacks_detected"] += 1
        cont = core.bos(m1, side, cfg.swing_k)
        if not cont:
            return self._reject("Waiting 1M continuation after pullback", {"location": loc, "side": side, "stage": "PULLBACK_1M"})
        self.funnel["continuations_detected"] += 1
        rv = core.rvol(m5)
        if rv < cfg.min_rvol:
            return self._reject(f"Volume participation weak rvol={rv:.2f}")
        if spread and atr5 and (spread / atr5) > cfg.max_spread_atr_5m:
            return self._reject(f"Spread too wide vs ATR ({spread:.3f}/{atr5:.3f})")
        self.funnel["spread_passed"] += 1
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
        self.funnel["fires"] += 1
        meta = {
            "location_type": loc["name"], "location_price": level, "sweep_level": level,
            "sweep_price": sweep_px, "sweep_distance_atr": penetration / atr5 if atr5 else None,
            "pullback_depth": pb_depth, "vwap": vwap, "vol_bucket": bucket, "rvol": rv,
        }
        self._ev("SETUP_ACCEPTED", reason=f"{sid} {side} {loc['name']} @{level:.2f} entry={entry:.2f} sl={sl:.2f}", setup_id=sid, session=sess)
        return {
            "action": "FIRE", "fire": True, "direction": side, "entry": entry, "stop": sl,
            "invalid_px": invalid, "level": level, "level_name": loc["name"], "setup_id": sid,
            "structure_key": key, "session": sess, "rvol": rv, "vol_ratio": vol_ratio,
            "vwap": vwap, "vol_bucket": bucket, "meta": meta,
            "reason": f"VALID {side.upper()} sweep-reclaim-BOS-pullback-continuation",
            "why_state": [f"loc {loc['name']} {level:.2f}", f"sweep {penetration:.2f}", "reclaim", "5M BOS", "1M PB", "1M cont"],
        }

    def on_open(self, setup: Dict, fill: float, sl: float, ts: int):
        self.thesis = Thesis(setup.get("setup_id") or "", setup["direction"], setup.get("level_name") or "",
                             float(setup.get("level") or fill), float(setup.get("invalid_px") or sl),
                             fill, sl, float(setup.get("invalid_px") or sl), ts, meta=setup.get("meta") or {})

    def on_exit(self, rec: Dict, ts: int = 0):
        reason = str(rec.get("exit_reason") or "").upper()
        key = None
        if self.thesis:
            key = f"{self.thesis.direction}|{self.thesis.level_name}|{round(self.thesis.level, 1)}"
        if "SL" in reason or reason in ("STOP", "STOP_LOSS", "THESIS_FAIL", "STRUCTURAL_SL"):
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
