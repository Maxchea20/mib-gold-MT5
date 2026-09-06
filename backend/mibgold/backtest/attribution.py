from typing import Dict, List
from ..consensus import DEFAULT_WEIGHTS, NAME


def attribution(trades: List[dict], weights: Dict[str, float] | None = None) -> Dict[str, dict]:
    """Per-engine performance attribution used to validate/reweight engines with real data."""
    weights = weights or DEFAULT_WEIGHTS
    closed = [t for t in trades if t.get("status") == "closed"]
    out = {}
    for key in DEFAULT_WEIGHTS:
        strongest = [t for t in closed if t.get("strongest_engine") == key]
        strongest_wins = sum(1 for t in strongest if t["outcome"] == "win")
        wins = [t for t in closed if t["outcome"] == "win"]
        losses = [t for t in closed if t["outcome"] == "loss"]
        agree_w = [t for t in wins if t["agent_votes"].get(key, {}).get("signal") == t["direction"]]
        agree_l = [t for t in losses if t["agent_votes"].get(key, {}).get("signal") == t["direction"]]
        conf_w = [t["agent_votes"][key]["confidence"] for t in agree_w]
        conf_l = [t["agent_votes"][key]["confidence"] for t in agree_l]
        neutral = sum(1 for t in closed if t["agent_votes"].get(key, {}).get("signal") == "neutral")
        agr_w = len(agree_w) / len(wins) if wins else 0.0
        agr_l = len(agree_l) / len(losses) if losses else 0.0
        edge = agr_w - agr_l
        rec = "insufficient data" if len(closed) < 10 else "upweight" if edge > 0.15 else "keep" if edge > -0.05 else "downweight" if edge > -0.2 else "drop"
        out[key] = {
            "engine": NAME.get(key, key), "weight": weights.get(key, DEFAULT_WEIGHTS[key]),
            "strongest_count": len(strongest),
            "strongest_win_rate": round(strongest_wins / len(strongest), 4) if strongest else None,
            "agreement_on_wins": round(agr_w, 4), "agreement_on_losses": round(agr_l, 4),
            "edge": round(edge, 4), "neutral_rate": round(neutral / len(closed), 4) if closed else 0.0,
            "avg_conf_wins": round(sum(conf_w) / len(conf_w), 4) if conf_w else None,
            "avg_conf_losses": round(sum(conf_l) / len(conf_l), 4) if conf_l else None,
            "recommendation": rec,
        }
    return out


def summary_stats(trades: List[dict], start_balance: float) -> dict:
    closed = [t for t in trades if t.get("status") == "closed"]
    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    gp = sum(t["pnl_usd"] for t in wins)
    gl = -sum(t["pnl_usd"] for t in losses)
    net = sum(t["pnl_usd"] for t in closed)
    return {
        "trades": len(closed), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(closed), 4) if closed else 0.0,
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "avg_r": round(sum(t["r_multiple"] for t in closed) / len(closed), 3) if closed else 0.0,
        "net_pnl": round(net, 2), "net_pnl_text": ("Profited" if net >= 0 else "Lost") + f" ${abs(net):,.2f}",
        "return_pct": round(net / start_balance, 4) if start_balance else 0.0,
        "by_exit": {r: sum(1 for t in closed if t["exit_reason"] == r) for r in {t["exit_reason"] for t in closed}},
    }