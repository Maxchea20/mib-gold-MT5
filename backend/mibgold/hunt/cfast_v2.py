"""C-Fast V2.1: 1:3 RR. SL kills that setup identity only, not the whole direction."""
from __future__ import annotations
from typing import Callable, Dict, Optional
from .hunt_c_fast import evaluate_hunt_c_fast

VERSION = "C_FAST_V2_1"
RR = 3.0
LEVEL_BUCKET = 1.0


def setup_key(direction: str, event: str, level: float) -> str:
    bucket = round(float(level) / LEVEL_BUCKET) * LEVEL_BUCKET
    return f"{(direction or '').lower()}|{(event or 'NA').upper()}|{bucket:.1f}"


class CFastV2:
    def __init__(self, log: Optional[Callable[[str], None]] = None):
        self.log = log or (lambda m: None)
        self.seq = 0
        self.failed_keys: set = set()
        self.completed_keys: set = set()
        self.active: Optional[Dict] = None
        self.last_sl_dir: Optional[str] = None
        self.stats = {
            "setups_invalidated": 0,
            "old_setup_blocked": 0,
            "new_same_dir_after_sl": 0,
            "fires": 0,
            "sl": 0,
            "tp": 0,
        }

    def _emit(self, msg: str):
        self.log(msg)

    def on_exit(self, rec: dict, now_ts: int = 0):
        reason = str(rec.get("exit_reason") or rec.get("exit_type") or "").upper()
        direction = (rec.get("direction") or rec.get("side") or "").lower()
        setup = self.active if self.active and self.active.get("direction") == direction else None
        sid = (setup or {}).get("setup_id") or rec.get("id")
        key = (setup or {}).get("structure_key")
        if key is None and rec.get("entry") is not None:
            key = setup_key(direction, "", rec.get("entry"))
        if reason in ("SL", "STOP", "STOP_LOSS") or reason.startswith("SL"):
            self.stats["sl"] += 1
            self.stats["setups_invalidated"] += 1
            if key:
                self.failed_keys.add(key)
            self.last_sl_dir = direction
            self._emit(
                f"SETUP_ID={sid} DIRECTION={direction.upper()} RESULT=SL "
                f"SETUP_STATE=FAILED REASON=SETUP INVALIDATED KEY={key}"
            )
            self.active = None
            return
        if reason in ("TP", "TRAIL_TP", "TARGET_REACHED", "TARGET") or "TP" in reason:
            self.stats["tp"] += 1
            if key:
                self.completed_keys.add(key)
            self._emit(f"SETUP_ID={sid} DIRECTION={direction.upper()} RESULT=TP SETUP_STATE=COMPLETED")
            self.active = None
            return
        self.active = None

    def evaluate(self, candles_15m, candle_5m, live_5ms=None, candles_4h=None, candles_1h=None, candles_5m=None) -> Dict:
        raw = evaluate_hunt_c_fast(
            candles_15m, candle_5m, live_5ms=live_5ms,
            candles_4h=candles_4h, candles_1h=candles_1h, candles_5m=candles_5m,
        )
        raw["brain_version"] = VERSION
        raw["rr"] = f"1:{int(RR)}"
        if raw.get("action") != "FIRE":
            raw["setup_id"] = (self.active or {}).get("setup_id")
            raw["structure_state"] = "WAITING" if not self.active else "ACTIVE"
            raw["structure_key"] = (self.active or {}).get("structure_key")
            return raw

        direction = (raw.get("direction") or "").lower()
        level = float(raw.get("entry") or raw.get("stop") or 0)
        key = setup_key(direction, raw.get("event") or "", level)

        if key in self.failed_keys:
            self.stats["old_setup_blocked"] += 1
            raw["action"] = "WAIT"
            why = f"OLD SETUP {key} FAILED - will not reuse"
            raw["why_state"] = [why]
            raw["blocking_reasons"] = [why]
            raw["structure_state"] = "FAILED"
            raw["structure_key"] = key
            return raw

        # Same identity already offered this cycle: do not mint a new id every minute
        if self.active and self.active.get("structure_key") == key:
            raw["action"] = "WAIT"
            raw["why_state"] = [f"setup {self.active.get('setup_id')} already armed on {key}"]
            raw["setup_id"] = self.active.get("setup_id")
            raw["structure_key"] = key
            raw["structure_state"] = "ACTIVE"
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
        setup_id = f"CF21-{direction[:1].upper()}-{int((candle_5m or {}).get('ts') or 0)}-{self.seq}"
        raw["setup_id"] = setup_id
        raw["structure_key"] = key
        raw["structure_id"] = key
        raw["structure_state"] = "FIRED"
        if self.last_sl_dir == direction:
            raw["new_setup_after_sl"] = True
            self.stats["new_same_dir_after_sl"] += 1
            self._emit(
                f"OLD_SETUP_ID=failed NEW_SETUP_ID={setup_id} DIRECTION={direction.upper()} "
                f"NEW_SETUP=TRUE REASON=NEW TRIGGER KEY={key}"
            )
            self.last_sl_dir = None
        else:
            self._emit(
                f"NEW C-FAST SETUP NEW_SETUP_ID={setup_id} DIRECTION={direction.upper()} "
                f"STRUCTURE/ORIGIN={key} ENTRY={entry} SL={raw['stop']} TP={raw['target']} "
                f"RR=1:{int(RR)} SETUP_STATE=FIRED"
            )
        self.active = raw
        self.stats["fires"] += 1
        return raw

    def apply_fixed_rr(self, entry: float, sl_dist: float, direction: str):
        sl_dist = abs(float(sl_dist))
        if direction == "long":
            return entry - sl_dist, entry + sl_dist * RR
        return entry + sl_dist, entry - sl_dist * RR
