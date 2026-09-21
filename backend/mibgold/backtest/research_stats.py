"""V1 research statistics. No strategy logic."""
from __future__ import annotations
from statistics import median
from typing import Dict, List


def _nums(xs):
    return [float(x) for x in xs if x is not None]


def _avg(xs):
    xs = _nums(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def _med(xs):
    xs = _nums(xs)
    return round(median(xs), 4) if xs else None


def max_dd(equity: List[dict], start: float) -> dict:
    peak = start
    dd = 0.0
    dd_r = 0.0
    for p in equity:
        eq = float(p.get("equity") or start)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"max_drawdown": round(dd, 2), "max_drawdown_pct": round(dd / start, 4) if start else None}


def summarize(trades: List[dict], start_balance: float, equity: List[dict]) -> dict:
    closed = [t for t in trades if t.get("status") == "closed"]
    wins = [t for t in closed if t.get("outcome") == "win"]
    losses = [t for t in closed if t.get("outcome") == "loss"]
    longs = [t for t in closed if t.get("direction") == "long"]
    shorts = [t for t in closed if t.get("direction") == "short"]
    gp = sum(t.get("pnl_usd") or 0 for t in wins)
    gl = -sum(t.get("pnl_usd") or 0 for t in losses)
    rs = [t.get("r_multiple") or 0 for t in closed]
    holds = [t.get("holding_time_seconds") for t in closed]
    mfes = [t.get("mfe") for t in closed]
    maes = [t.get("mae") for t in closed]
    mfe_r = [t.get("mfe_r") for t in closed]
    mae_r = [t.get("mae_r") for t in closed]
    net = sum(t.get("pnl_usd") or 0 for t in closed)
    wr = (len(wins) / len(closed)) if closed else 0.0
    avg_r = _avg(rs) or 0.0
    return {
        "trades": len(closed), "long_trades": len(longs), "short_trades": len(shorts),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(wr, 4),
        "total_r": round(sum(rs), 4),
        "average_r": avg_r,
        "median_r": _med(rs),
        "expectancy": round(avg_r, 4),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "net_pnl": round(net, 2),
        "average_winner": _avg([t.get("pnl_usd") for t in wins]),
        "average_loser": _avg([t.get("pnl_usd") for t in losses]),
        "largest_winner": max((t.get("pnl_usd") or 0 for t in wins), default=None),
        "largest_loser": min((t.get("pnl_usd") or 0 for t in losses), default=None),
        "average_holding_seconds": _avg(holds),
        "median_holding_seconds": _med(holds),
        "min_holding_seconds": min(_nums(holds), default=None),
        "max_holding_seconds": max(_nums(holds), default=None),
        "average_mfe": _avg(mfes), "average_mae": _avg(maes),
        "average_mfe_r": _avg(mfe_r), "average_mae_r": _avg(mae_r),
        **max_dd(equity, start_balance),
        "by_exit": {r: sum(1 for t in closed if t.get("exit_reason") == r) for r in {t.get("exit_reason") for t in closed}},
    }


def breakdown(trades: List[dict], key: str) -> Dict[str, dict]:
    closed = [t for t in trades if t.get("status") == "closed"]
    keys = sorted({str(t.get(key) or "NA") for t in closed})
    out = {}
    for k in keys:
        g = [t for t in closed if str(t.get(key) or "NA") == k]
        wins = [t for t in g if t.get("outcome") == "win"]
        net = sum(t.get("pnl_usd") or 0 for t in g)
        out[k] = {
            "trades": len(g), "wins": len(wins),
            "win_rate": round(len(wins) / len(g), 4) if g else 0,
            "net_pnl": round(net, 2),
            "avg_r": round(sum(t.get("r_multiple") or 0 for t in g) / len(g), 4) if g else 0,
        }
    return out


def conversions(funnel: dict) -> dict:
    def rate(a, b):
        x, y = funnel.get(a) or 0, funnel.get(b) or 0
        return round(y / x, 4) if x else None
    return {
        "sweep_to_reclaim": rate("sweeps_detected", "reclaims_detected"),
        "reclaim_to_bos": rate("reclaims_detected", "bos_5m_detected"),
        "bos_to_pullback": rate("bos_5m_detected", "pullbacks_detected"),
        "pullback_to_continuation": rate("pullbacks_detected", "continuations_detected"),
        "continuation_to_fire": rate("continuations_detected", "fires"),
    }
