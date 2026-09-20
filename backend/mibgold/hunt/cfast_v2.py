"""C-Fast V2: same Hunt C-fast door, fixed 1:3 RR, SL invalidates that direction until new structure."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from .hunt_c_fast import evaluate_hunt_c_fast, _swings

VERSION = "C_FAST_V2"
RR = 3.0


def _ts(row: dict) -> int:
    return int(row.get("ts") or 0)


def _setup_key(direction: str, event: str, level: float, origin_ts: int) -> str:
    return f"{direction}|{event or 'NA'}|{round(float(level), 2)}|{int(origin_ts)}"


@dataclass
class DirLock:
    locked: bool = False
    failed_setup_id: Optional[str] = None
    failed_key: Optional[str] = None
    lock_ts: int = 0
    failed_level: Optional[float] = None
    pivot: Optional[float] = None
    pivot_ts: int = 0
    rearmed_at: int = 0
    invalidated: int = 0
    rearms: int = 0


class CFastV2:
    def __init__(self, log: Optional[Callable[[str], None]] = None):
        self.log = log or (lambda m: None)
        self.locks = {"long": DirLock(), "short": DirLock()}
        self.seq = 0
        self.failed_keys: set = set()
        self.active: Optional[Dict] = None
        self.stats = {
            "setups_invalidated": 0, "new_structures": 0, "same_dir_blocked": 0,
            "old_setup_blocked": 0, "fires": 0, "sl": 0, "tp": 0,
        }

    def _emit(self, msg: str):
        self.log(msg)

    def on_exit(self, rec: dict, now_ts: int = 0):
        reason = str(rec.get("exit_reason") or rec.get("exit_type") or "").upper()
        direction = (rec.get("direction") or "").lower()
        setup = self.active if self.active and self.active.get("direction") == direction else None
        sid = (setup or {}).get("setup_id") or rec.get("id")
        if reason in ("SL", "STOP", "STOP_LOSS") or reason.startswith("SL"):
            self.stats["sl"] += 1
            self.stats["setups_invalidated"] += 1
            if direction in self.locks:
                lk = self.locks[direction]
                lk.locked = True
                lk.failed_setup_id = sid
                lk.failed_key = (setup or {}).get("structure_key")
                lk.lock_ts = int(now_ts or 0)
                lk.failed_level = rec.get("entry") or rec.get("entry_price")
                lk.pivot = None
                lk.pivot_ts = 0
                lk.invalidated += 1
                if lk.failed_key:
                    self.failed_keys.add(lk.failed_key)
            self._emit(f"SL HIT SETUP_ID={sid} DIRECTION={direction.upper()} SETUP_STATE=INVALIDATED RE-ENTRY=LOCKED REASON=CURRENT STRUCTURE FAILED")
            self.active = None
            return
        if reason in ("TP", "TRAIL_TP", "TARGET_REACHED", "TARGET") or "TP" in reason:
            self.stats["tp"] += 1
            self._emit(f"TP HIT SETUP_ID={sid} DIRECTION={direction.upper()} SETUP_STATE=COMPLETED")
            self.active = None
            return
        self.active = None

    def _unlock_if_new_structure(self, direction: str, m5: List[dict], now_ts: int) -> Optional[str]:
        lk = self.locks[direction]
        if not lk.locked:
            return None
        highs, lows = _swings(m5, k=2)
        after = [b for b in (highs if direction == "long" else lows) if _ts(b) > lk.lock_ts]
        if not after:
            return f"{direction.upper()} LOCKED waiting new swing after SL {lk.failed_setup_id}"
        if lk.pivot is None:
            last = after[-1]
            lk.pivot = float(last["high"] if direction == "long" else last["low"])
            lk.pivot_ts = _ts(last)
            self._emit(f"NEW PIVOT MARKED OLD_SETUP_ID={lk.failed_setup_id} DIRECTION={direction.upper()} PIVOT={lk.pivot} TS={lk.pivot_ts}")
        close = float(m5[-1]["close"])
        broke = (direction == "long" and close > float(lk.pivot)) or (direction == "short" and close < float(lk.pivot))
        if not broke:
            return f"{direction.upper()} LOCKED: need break of fresh {'high' if direction == 'long' else 'low'} {lk.pivot}"
        lk.locked = False
        lk.rearmed_at = int(now_ts)
        lk.rearms += 1
        self.stats["new_structures"] += 1
        self._emit(f"NEW STRUCTURE DETECTED OLD_SETUP_ID={lk.failed_setup_id} NEW_STRUCTURE_ID={direction}-{lk.pivot}-{lk.pivot_ts} DIRECTION={direction.upper()} {direction.upper()}_DIRECTION=RE-ARMED")
        lk.pivot = None
        return None

    def evaluate(self, candles_15m, candle_5m, live_5ms=None, candles_4h=None, candles_1h=None, candles_5m=None) -> Dict:
        raw = evaluate_hunt_c_fast(candles_15m, candle_5m, live_5ms=live_5ms, candles_4h=candles_4h, candles_1h=candles_1h, candles_5m=candles_5m)
        m5 = candles_5m or live_5ms or ([candle_5m] if candle_5m else [])
        now_ts = int((candle_5m or {}).get("ts") or 0)
        for d in ("long", "short"):
            self._unlock_if_new_structure(d, m5, now_ts)
        raw["brain_version"] = VERSION
        raw["rr"] = f"1:{int(RR)}"
        if raw.get("action") != "FIRE":
            raw["setup_id"] = None
            raw["structure_state"] = self._state_label()
            return raw
        direction = (raw.get("direction") or "").lower()
        lk = self.locks.get(direction)
        if lk and lk.locked:
            self.stats["same_dir_blocked"] += 1
            raw["action"] = "WAIT"
            why = f"{direction.upper()} LOCKED after SL {lk.failed_setup_id}; need new structure before another {direction.upper()}"
            raw["why_state"] = [why]
            raw["blocking_reasons"] = [why]
            raw["structure_state"] = "LOCKED"
            raw["setup_id"] = lk.failed_setup_id
            return raw
        origin_ts = int(candles_15m[-2]["ts"]) if candles_15m and len(candles_15m) >= 2 else now_ts
        key = _setup_key(direction, raw.get("event") or "", raw.get("entry") or raw.get("stop") or 0, origin_ts)
        if key in self.failed_keys:
            self.stats["old_setup_blocked"] += 1
            raw["action"] = "WAIT"
            why = f"OLD SETUP {key} FAILED — will not reuse"
            raw["why_state"] = [why]
            raw["blocking_reasons"] = [why]
            raw["structure_state"] = "INVALIDATED"
            return raw
        entry = float(raw["entry"])
        stop = float(raw["stop"])
        sl_dist = abs(entry - stop)
        if sl_dist <= 0:
            raw["action"] = "WAIT"
            raw["why_state"] = ["SL distance is 0"]
            return raw
        raw["target"] = entry + sl_dist * RR if direction == "long" else entry - sl_dist * RR
        self.seq += 1
        setup_id = f"CF2-{direction[0].upper()}-{now_ts}-{self.seq}"
        raw["setup_id"] = setup_id
        raw["structure_key"] = key
        raw["structure_id"] = key
        raw["structure_state"] = "FIRED"
        self.active = raw
        self.stats["fires"] += 1
        self._emit(f"NEW C-FAST SETUP NEW_SETUP_ID={setup_id} DIRECTION={direction.upper()} STRUCTURE_ID={key} ENTRY={entry} SL={raw['stop']} TP={raw['target']} RR=1:{int(RR)}")
        return raw

    def _state_label(self) -> str:
        return " ".join(f"{d}={'LOCKED' if lk.locked else 'ARMED'}" for d, lk in self.locks.items())

    def apply_fixed_rr(self, entry: float, sl_dist: float, direction: str):
        sl_dist = abs(float(sl_dist))
        if direction == "long":
            return entry - sl_dist, entry + sl_dist * RR
        return entry + sl_dist, entry - sl_dist * RR
