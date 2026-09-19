from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import pandas as pd
from .contracts import EngineContext
from .engines import EngineSuite
from .engines.utils import safe_atr
from .consensus import Consensus, summarize
from .session import session_for
from .book import PositionBook
from .risk import SymbolSpec

REFERENCE_TFS = ("D1", "H4")
BIAS_TF = "H1"
SETUP_TF = "M15"
ENTRY_TF = "M5"


@dataclass
class StrategyConfig:
    sl_atr_mult: float = 1.2
    scale_in_r: float = 0.5
    bias_min_score: float = 0.10
    struct_oppose_score: float = 0.15
    lookback: int = 220
    blocked_sessions: Tuple[str, ...] = ("london",)
    blocked_weekdays: Tuple[int, ...] = (4,)   # Friday
    blocked_hours_utc: Tuple[int, ...] = (19,)  # 19:00-19:59 UTC


class TopDownStrategy:
    def __init__(self, suite: EngineSuite, consensus: Consensus, cfg: StrategyConfig | None = None):
        self.suite, self.consensus, self.cfg = suite, consensus, cfg or StrategyConfig()
        self._cache: Dict[str, tuple] = {}

    def _tf_votes(self, tf: str, df: pd.DataFrame, ctx: EngineContext) -> dict:
        last_ts = df["time"].iloc[-1]
        key = (tf, last_ts, ctx.session)
        cached = self._cache.get(tf)
        if cached and cached[0] == key:
            return cached[1]
        ctx.timeframe = tf
        votes = self.suite.run(df.tail(self.cfg.lookback), ctx)
        cons = self.consensus.evaluate(votes, ctx.session)
        out = {"votes": votes, "consensus": cons}
        self._cache[tf] = (key, out)
        return out

    def analyze(self, frames: Dict[str, pd.DataFrame], now: datetime, spec: SymbolSpec, advisory: Optional[dict] = None) -> dict:
        session = session_for(now)
        ts = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        utc = ts.astimezone(timezone.utc)
        ctx = EngineContext(session=session, contract_size=spec.contract_size, advisory=advisory, now=now)
        all_tfs = (*REFERENCE_TFS, BIAS_TF, SETUP_TF, ENTRY_TF)
        tf = {t: self._tf_votes(t, frames[t], ctx) for t in all_tfs if t in frames and len(frames[t]) > 0}

        h1 = tf.get(BIAS_TF, {}).get("consensus", {})
        d1 = tf.get("D1", {}).get("consensus", {})
        h4 = tf.get("H4", {}).get("consensus", {})
        bias = self._bias_from_h1(h1, d1, h4)
        reference = {"d1_direction": d1.get("direction", "neutral"), "d1_score": d1.get("score", 0.0),
                     "h4_direction": h4.get("direction", "neutral"), "h4_score": h4.get("score", 0.0)}
        m15 = tf.get(SETUP_TF, {}).get("consensus", {})
        struct_ok = not (m15 and bias["direction"] != "neutral" and m15.get("direction") not in (bias["direction"], "neutral")
                         and abs(m15.get("score", 0)) >= self.cfg.struct_oppose_score)
        m5 = tf.get(ENTRY_TF, {})
        entry_cons = m5.get("consensus", {})
        fire, gate_reason = self._brain_decide(utc, session, bias, struct_ok, m15, entry_cons)
        if fire and advisory and advisory.get("bias") not in (None, "neutral", bias["direction"]):
            entry_cons = dict(entry_cons)
            entry_cons["advisory_conflict"] = True
        return {
            "time": now.isoformat(), "session": session, "bias": bias, "reference": reference,
            "structure": m15, "struct_ok": struct_ok,
            "timeframes": tf, "entry": entry_cons, "votes": m5.get("votes", {}),
            "summary": summarize(entry_cons) if entry_cons else "No M5 data",
            "fire": fire, "gate_reason": gate_reason, "advisory": advisory,
        }

    def _brain_decide(self, utc, session, bias, struct_ok, m15, entry_cons) -> tuple:
        """Calendar + stack. Votes are input only — no score/aligned threshold."""
        m5d = entry_cons.get("direction") or "neutral"
        if utc.weekday() in self.cfg.blocked_weekdays:
            return False, "brain: Friday cut"
        if utc.hour in self.cfg.blocked_hours_utc:
            return False, f"brain: {utc.hour:02d}:00 UTC cut"
        if session in self.cfg.blocked_sessions:
            return False, f"brain: {session} cut"
        if bias["direction"] == "neutral":
            return False, "brain: H1 no side"
        if not struct_ok:
            return False, f"brain: M15 against {bias['direction']} ({m15.get('score', 0):+.2f})"
        if m5d == "neutral":
            return False, "brain: M5 no side"
        if m5d != bias["direction"]:
            return False, f"brain: M5 {m5d} vs H1 {bias['direction']}"
        return True, None

    def _bias_from_h1(self, h1: dict, d1: dict, h4: dict) -> dict:
        s = h1.get("score", 0.0)
        m = self.cfg.bias_min_score
        direction = "long" if s >= m else "short" if s <= -m else "neutral"
        return {"direction": direction, "strength": round(abs(s), 4), "h1_score": round(s, 4),
                "d1_score": round(d1.get("score", 0.0), 4), "h4_score": round(h4.get("score", 0.0), 4)}

    def propose_entry(self, analysis: dict, frames: Dict[str, pd.DataFrame], book: PositionBook, spec: SymbolSpec,
                      price_bid: float, price_ask: float) -> Optional[dict]:
        if not analysis["fire"]:
            return None
        direction = analysis["bias"]["direction"]
        m5 = frames[ENTRY_TF]
        atr = safe_atr(m5.tail(60))
        group = book.group_for(direction)
        if group:
            last = group[-1]
            ref = price_bid if direction == "long" else price_ask
            if last.tp is not None:
                need = abs(last.tp - last.entry) * 0.5
                gone = (ref - last.entry) if last.direction == "long" else (last.entry - ref)
                if gone < need:
                    return {"blocked": f"Scale-in requires L1 50% to TP (need {need:.2f}, have {gone:.2f})"}
            elif last.r_multiple(ref) < self.cfg.scale_in_r:
                return {"blocked": f"Scale-in requires +{self.cfg.scale_in_r}R on layer {last.layer_number} first"}
        entry = price_ask if direction == "long" else price_bid
        sl = entry - atr * self.cfg.sl_atr_mult if direction == "long" else entry + atr * self.cfg.sl_atr_mult
        equity = book.equity((price_bid + price_ask) / 2)
        decision = book.risk.size_new_layer(equity, entry, sl, book.layers, direction)
        return {"direction": direction, "entry": entry, "sl": round(sl, 2), "atr": atr, "decision": decision,
                "blocked": None if decision.allowed else decision.reason}
