from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List


def _downloads() -> Path:
    home = Path.home()
    for name in ("Downloads", "Download"):
        p = home / name
        if p.is_dir():
            return p
    p = home / "Downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_report(bt_id: str, fmt: str, doc: Dict[str, Any], trades: List[dict]) -> str:
    fmt = (fmt or "json").lower()
    if fmt not in ("json", "txt"):
        fmt = "json"
    folder = _downloads()
    stem = f"mibgold-{bt_id}"
    stats = (doc or {}).get("stats") or {}
    rows = []
    for t in trades or []:
        rows.append({
            "id": t.get("id"),
            "time": t.get("exit_time") or t.get("timestamp") or t.get("time"),
            "side": t.get("direction") or t.get("side"),
            "layer": t.get("layer_number") or t.get("layer"),
            "session": t.get("session"),
            "entry": t.get("entry") or t.get("entry_price"),
            "exit": t.get("exit_price") or t.get("exit"),
            "exit_reason": t.get("exit_reason") or t.get("exit_type"),
            "r": t.get("r_multiple") if t.get("r_multiple") is not None else t.get("r"),
            "pnl": t.get("pnl") if t.get("pnl") is not None else t.get("pnl_usd"),
            "vol_bucket": t.get("vol_bucket"),
            "market_regime": t.get("market_regime"),
            "location_type": t.get("location_type"),
            "mfe": t.get("mfe"),
            "mae": t.get("mae"),
        })
    payload = {
        "id": bt_id,
        "book": ((doc or {}).get("config") or {}).get("book") or "LIQ-JOIN M3",
        "range": (doc or {}).get("range"),
        "config": (doc or {}).get("config"),
        "stats": stats,
        "by_session": (doc or {}).get("by_session"),
        "by_direction": (doc or {}).get("by_direction"),
        "by_volatility": (doc or {}).get("by_volatility"),
        "cfast_v2": (doc or {}).get("cfast_v2"),
        "final_balance": (doc or {}).get("final_balance"),
        "trades": rows,
    }
    if fmt == "json":
        path = folder / f"{stem}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(path)
    path = folder / f"{stem}.txt"
    lines = [
        f"FILE {path.name}", f"ID {bt_id}",
        f"STATS trades={stats.get('trades')} wr={stats.get('win_rate')} pf={stats.get('profit_factor')} net={stats.get('net_pnl')}",
        "", "time\tside\tsession\tvol\tin\tout\texit\tR\tpnl",
    ]
    for t in rows:
        lines.append("\t".join("" if x is None else str(x) for x in [
            t.get("time"), str(t.get("side") or "").upper(), t.get("session"), t.get("vol_bucket"),
            t.get("entry"), t.get("exit"), t.get("exit_reason"), t.get("r"), t.get("pnl"),
        ]))
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
