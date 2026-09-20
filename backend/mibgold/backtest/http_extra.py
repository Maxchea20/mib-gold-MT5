"""Extra Lab routes. Imported from server.py."""
from fastapi import HTTPException
from .export_report import write_report


def slim_trades(rows):
    out = []
    for t in rows or []:
        if not isinstance(t, dict):
            continue
        out.append({
            "id": t.get("id"),
            "exit_time": t.get("exit_time") or t.get("timestamp"),
            "direction": t.get("direction"),
            "layer_number": t.get("layer_number"),
            "session": t.get("session"),
            "entry": t.get("entry"),
            "exit_price": t.get("exit_price"),
            "exit_reason": t.get("exit_reason"),
            "r_multiple": t.get("r_multiple"),
            "pnl": t.get("pnl"),
        })
    return out


def attach(api, runner, store):
    @api.get("/backtest/{bt_id}/export")
    async def backtest_export(bt_id: str, fmt: str = "json"):
        bt = runner.runs.get(bt_id)
        if bt and bt.result:
            doc, trades = bt.result, bt.result.get("trades") or []
        else:
            doc = store.get_backtest(bt_id)
            trades = store.list_trades(status=None, backtest_id=bt_id, limit=8000, order="timestamp", descending=False)
        if not doc:
            raise HTTPException(404, "backtest not finished or not found")
        path = write_report(bt_id, fmt, doc, trades)
        return {"ok": True, "path": path, "fmt": fmt}
