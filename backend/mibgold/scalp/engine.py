"""Scalp V1. Frozen parameters. HTF cache is performance-only."""
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


def _cs(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return core.rows(x)


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
        self._htf = {}

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
        m1 = _cs(frames.get("M1"))
        m5 = _cs(frames.get("M5"))
        m15 = _cs(frames.get("M15"))
        d1 = _cs(frames.get("D1"))
        if len(m15) < 30 or len(m5) < 30 or len(m1) < 30:
            return self._reject("Need more closed candles")
        last5, last1 = m5[-1], m1[-1]
        key = (d1[-1]["ts"] if d1 else 0, m15[-1]["ts"], last5["ts"])
        htf = self._htf
        if htf.get("key") != key:
            atr5 = core.atr(m5)
            prior = core.atr(m5[:-20]) or atr5
            vol_ratio = atr5 / prior if prior else 1.0
            htf.update({
                "key": key, "atr5": atr5, "vol_ratio": vol_ratio,
                "bucket": core.vol_bucket(vol_ratio),
                "static_locs": core.locations(m15, d1, m5, m1=None, k=self.cfg.swing_k, now_ts=last5["ts"]),
            })
        atr5 = htf["atr5"]
        vol_ratio = htf["vol_ratio"]
        bucket = htf["bucket"]
        atr1 = core.atr(m1)
        if atr5 <= 0 or atr1 <= 0:
            return self._reject("ATR not ready")
        if vol_ratio > 2.2:
            return self._reject("CHAOS: extreme 5M ATR expansion", {"state": "CHAOS", "vol_bucket": bucket})
        sess = core.session_name(_hour(last5["ts"]))
        vwap = core.session_vwap(m1, last1["ts"])
        # Session levels move every M1; PDH/15M/5M swings stay until that TF closes.
        locs = list(htf["static_locs"])
        extra = core.locations([], [], [], m1=m1, k=self.cfg.swing_k, now_ts=last1["ts"])
        locs.extend(extra)
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
