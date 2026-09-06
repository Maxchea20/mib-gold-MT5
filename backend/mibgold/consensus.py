from typing import Dict
from .session import SESSION_THRESHOLD, SESSION_MIN_ALIGNED
from .engines import ENGINE_META

# Elliott Wave deliberately downweighted (subjective, low standalone reliability)
DEFAULT_WEIGHTS = {
    "trend": 1.0, "structure": 1.0, "sr": 1.0, "breakout": 0.9, "momentum": 0.8,
    "volume": 0.6, "fibonacci": 0.7, "elliott": 0.35, "fvg": 0.9, "pattern": 0.8,
}
NAME = {m["key"]: m["name"] for m in ENGINE_META}


class Consensus:
    def __init__(self, weights: Dict[str, float] | None = None, session_threshold: Dict[str, float] | None = None,
                 session_min_aligned: Dict[str, int] | None = None):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        # Per-instance copies so a backtest's overrides never leak into the live engine's thresholds
        self.session_threshold = dict(SESSION_THRESHOLD)
        if session_threshold:
            self.session_threshold.update(session_threshold)
        self.session_min_aligned = dict(SESSION_MIN_ALIGNED)
        if session_min_aligned:
            self.session_min_aligned.update(session_min_aligned)

    def evaluate(self, votes: Dict[str, dict], session: str) -> dict:
        total_w = sum(self.weights.get(k, 1.0) for k in votes)
        net, contrib = 0.0, {}
        for k, v in votes.items():
            w = self.weights.get(k, 1.0)
            sign = 1 if v["signal"] == "long" else -1 if v["signal"] == "short" else 0
            c = w * v["confidence"] * sign
            contrib[k] = c
            net += c
        score = net / total_w if total_w else 0.0
        direction = "long" if score > 0 else "short" if score < 0 else "neutral"
        aligned = [k for k, v in votes.items() if v["signal"] == direction and direction != "neutral"]
        opposed = [k for k, v in votes.items() if v["signal"] not in (direction, "neutral")]
        leaders = sorted(aligned, key=lambda k: abs(contrib[k]), reverse=True)[:3]
        threshold = self.session_threshold.get(session, 0.3)
        min_aligned = self.session_min_aligned.get(session, 5)
        passes = abs(score) >= threshold and len(aligned) >= min_aligned
        return {
            "direction": direction,
            "score": round(score, 4),
            "confidence": round(min(abs(score) / 0.6, 1.0), 4),
            "aligned": len(aligned),
            "opposed": len(opposed),
            "total": len(votes),
            "leaders": leaders,
            "leader_names": [NAME.get(k, k) for k in leaders],
            "threshold": threshold,
            "min_aligned": min_aligned,
            "session": session,
            "passes": passes,
            "contributions": {k: round(v, 4) for k, v in contrib.items()},
        }


def summarize(consensus: dict) -> str:
    """Deterministic, rule-based one-liner. No AI."""
    d = consensus["direction"]
    if d == "neutral" or consensus["aligned"] == 0:
        return f"No consensus: {consensus['total']} engines split, score {consensus['score']:+.2f}."
    led = " + ".join(consensus["leader_names"])
    s = f"{consensus['aligned']}/{consensus['total']} engines aligned {d}, led by {led}."
    if consensus["opposed"]:
        s += f" {consensus['opposed']} opposed."
    return s