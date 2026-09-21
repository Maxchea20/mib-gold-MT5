"""Extra backtest HTTP helpers imported by server.py."""


def slim_trades(rows):
    out = []
    for t in rows or []:
        if not isinstance(t, dict):
            continue
        side = t.get("direction") or t.get("side")
        out.append({
            "id": t.get("id"),
            "time": t.get("exit_time") or t.get("timestamp") or t.get("time"),
            "exit_time": t.get("exit_time") or t.get("timestamp") or t.get("time"),
            "direction": side,
            "side": side,
            "layer_number": t.get("layer_number") or t.get("layer") or 1,
            "session": t.get("session"),
            "entry": t.get("entry"),
            "exit_price": t.get("exit_price") or t.get("exit"),
            "exit_reason": t.get("exit_reason"),
            "r_multiple": t.get("r_multiple") if t.get("r_multiple") is not None else t.get("r"),
            "r": t.get("r_multiple") if t.get("r_multiple") is not None else t.get("r"),
            "pnl": t.get("pnl"),
            "vol_bucket": t.get("vol_bucket"),
            "market_regime": t.get("market_regime"),
            "location_type": t.get("location_type"),
            "mfe": t.get("mfe"),
            "mae": t.get("mae"),
        })
    return out
