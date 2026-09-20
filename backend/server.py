from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Set
from datetime import datetime, timezone, timedelta
from pathlib import Path
import asyncio
import json
import logging
import os
from mibgold.backtest.export_report import write_report
from mibgold.backtest.routes import slim_trades as _slim_trades

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from mibgold.adapters import make_adapter
from mibgold.adapters.sim import SimAdapter, load_csv
from mibgold.news import NewsGate, NewsInterpreter, NewsEvent, start_refresher
from mibgold.live import LiveEngine
from mibgold.backtest.harness import Backtest, BacktestRunner
from mibgold.consensus import DEFAULT_WEIGHTS
from mibgold.engines import ENGINE_META
from mibgold.session import SESSION_THRESHOLD, SESSION_MIN_ALIGNED, SESSION_LABEL
from mibgold.store import Store
from mibgold.bars_cache import ingest_folder, stats as bar_stats

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mibgold.server")

store = Store(Path(os.environ["MIBGOLD_DB"]) if os.environ.get("MIBGOLD_DB") else None)

app = FastAPI(title="mib-gold")
api = APIRouter(prefix="/api")


class Hub:
    def __init__(self):
        self.clients: Set[WebSocket] = set()

    async def broadcast(self, msg: dict):
        if not self.clients:
            return
        data = json.dumps(msg, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


hub = Hub()
gate = NewsGate(before_min=int(os.environ.get("NEWS_WINDOW_BEFORE_MIN", "30")), after_min=int(os.environ.get("NEWS_WINDOW_AFTER_MIN", "30")))
interpreter = NewsInterpreter(gate)
adapter = make_adapter()
runner = BacktestRunner()


async def persist_trade(rec: dict):
    store.upsert_trade(rec)


live = LiveEngine(adapter, gate, interpreter, hub.broadcast, persist_trade)

WEIGHTS_FILE = ROOT_DIR / "data" / "live_weights.json"
try:
    live.strategy.consensus.weights.update(json.loads(WEIGHTS_FILE.read_text()))
except Exception:
    pass


@app.on_event("startup")
async def _startup():
    start_refresher(gate)
    if isinstance(adapter, SimAdapter) and os.environ.get("SIM_NEWS", "true").lower() == "true":
        gate.add_runtime_events(adapter.sim_news_events())
    sym = os.environ.get("MT5_SYMBOL", getattr(adapter, "symbol", "GOLD#"))
    try:
        imported = ingest_folder(ROOT_DIR / "data", symbol=sym)
        if imported:
            logger.info("history import %s", imported)
    except Exception:
        logger.exception("history import failed")
    asyncio.create_task(live.run())


@app.on_event("shutdown")
async def _shutdown():
    store.close()
    adapter.shutdown()


@api.get("/")
async def root():
    return {"app": "mib-gold", "mode": live.book.mode}


@api.get("/status")
async def status():
    return live.status()


@api.get("/connection")
async def connection():
    return {"connection": live.connection, "account": adapter.account(), "symbol": live.spec.to_dict()}


@api.get("/config")
async def config():
    return {"weights": DEFAULT_WEIGHTS, "engines": ENGINE_META, "session_thresholds": SESSION_THRESHOLD,
            "session_min_aligned": SESSION_MIN_ALIGNED, "session_labels": SESSION_LABEL,
            "risk": {"budget_pct": live.risk.budget_pct, "max_layers": live.risk.max_layers, "allocation": live.risk.allocation.name},
            "news_window": {"before": gate.before.total_seconds() // 60, "after": gate.after.total_seconds() // 60},
            "ai_enabled": interpreter.enabled}


@api.get("/weights")
async def get_weights():
    return live.strategy.consensus.weights


@api.post("/weights")
async def set_weights(body: dict):
    live.strategy.consensus.weights.update(body)
    WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_FILE.write_text(json.dumps(live.strategy.consensus.weights))
    return live.strategy.consensus.weights


@api.post("/weights/reset")
async def reset_weights():
    live.strategy.consensus.weights = dict(DEFAULT_WEIGHTS)
    if WEIGHTS_FILE.exists():
        WEIGHTS_FILE.unlink()
    return live.strategy.consensus.weights


@api.get("/chart")
async def chart(tf: str = "M5", n: int = 400):
    if tf not in ("M1", "M5", "M15", "H1", "H4", "D1"):
        raise HTTPException(400, "bad timeframe")
    return {"tf": tf, "bars": live.chart(tf, n)}


@api.get("/history")
async def history():
    sym = os.environ.get("MT5_SYMBOL", getattr(adapter, "symbol", "GOLD#"))
    return bar_stats(sym)


@api.post("/history/import")
async def history_import():
    sym = os.environ.get("MT5_SYMBOL", getattr(adapter, "symbol", "GOLD#"))
    imported = ingest_folder(ROOT_DIR / "data", symbol=sym)
    return {"imported": imported, "stats": bar_stats(sym)}


@api.get("/analysis")
async def analysis():
    return live.analysis


@api.get("/layers")
async def layers():
    return live.book.snapshot(live.tick.mid if live.tick else 0.0)


@api.post("/layers/{layer_id}/close")
async def close_layer(layer_id: str):
    rec = await live.close_layer_manual(layer_id)
    if not rec:
        raise HTTPException(404, "layer not found")
    return rec


class AutoTrade(BaseModel):
    enabled: bool


@api.post("/auto-trade")
async def set_auto(body: AutoTrade):
    live.auto_trade = body.enabled
    await hub.broadcast({"type": "auto_trade", "enabled": body.enabled})
    return {"auto_trade": live.auto_trade}


@api.get("/events")
async def events():
    return live.events[-100:]


@api.get("/trades")
async def trades(direction: Optional[str] = None, session: Optional[str] = None, outcome: Optional[str] = None,
                 engine: Optional[str] = None, mode: Optional[str] = None, backtest_id: Optional[str] = None, limit: int = 200):
    return store.list_trades(
        status="closed", direction=direction, session=session, outcome=outcome,
        mode=mode, backtest_id=backtest_id, engine=engine, limit=limit,
        order="exit_time", descending=True,
    )


@api.get("/trades/stats")
async def trade_stats(mode: Optional[str] = None, backtest_id: Optional[str] = None):
    from mibgold.backtest.attribution import summary_stats
    docs = store.list_trades(status="closed", mode=mode, backtest_id=backtest_id, limit=5000)
    return summary_stats(docs, live.book.start_balance)


@api.get("/news")
async def news():
    now = live.tick.time if live.tick else datetime.now(timezone.utc)
    return {"gate": gate.check(now), "advisory": interpreter.current(now), "advisory_history": interpreter.history[-10:],
            "ai_enabled": interpreter.enabled, "sim_time": now.isoformat()}


class ManualEvent(BaseModel):
    title: str
    time: str
    country: str = "USD"
    impact: str = "High"
    forecast: str = ""
    previous: str = ""
    actual: str = ""
    enabled: bool = True


@api.post("/news/manual")
async def add_manual(ev: ManualEvent):
    gate.add_manual(ev.model_dump())
    now = live.tick.time if live.tick else datetime.now(timezone.utc)
    live.gate_state = gate.check(now)
    await hub.broadcast({"type": "news", "news": live.gate_state})
    return live.gate_state


@api.post("/news/interpret")
async def interpret(ev: ManualEvent):
    if not interpreter.enabled:
        raise HTTPException(400, "EMERGENT_LLM_KEY not configured")
    e = NewsEvent(ev.title, ev.country, datetime.fromisoformat(ev.time).astimezone(timezone.utc), ev.impact, ev.forecast, ev.previous, ev.actual, "manual")
    adv = await interpreter.interpret_now(e, live.tick.time if live.tick else None)
    await hub.broadcast({"type": "advisory", "advisory": adv})
    return adv


class BacktestRequest(BaseModel):
    days: int = 10
    start_balance: float = 250.0
    max_layers: int = 3
    budget_pct: float = 0.10
    slippage_points: float = 5.0
    use_news_gate: bool = True
    csv_path: Optional[str] = None
    weights: Optional[dict] = None
    bias_min_score: Optional[float] = None
    struct_oppose_score: Optional[float] = None
    session_thresholds: Optional[dict] = None
    session_min_aligned: Optional[dict] = None
    min_risk_usd: float = 1.0
    max_risk_usd: float = 100.0
    fixed_lots: Optional[float] = 0.01
    sl_dollars: Optional[float] = 3.0
    tp_dollars: Optional[float] = 3.0


@api.post("/backtest/run")
async def backtest_run(req: BacktestRequest):
    if req.csv_path:
        if not os.path.exists(req.csv_path):
            raise HTTPException(400, "csv not found")
        m1 = load_csv(req.csv_path)
    elif isinstance(adapter, SimAdapter):
        m1 = adapter.full_history()
    else:
        end = datetime.now(timezone.utc)
        max_total_days = int(os.environ.get("BACKTEST_MAX_TOTAL_DAYS", "45"))
        warmup_days = max(5, min(60, max_total_days - req.days))
        m1 = adapter.m1_range(end - timedelta(days=req.days + warmup_days), end)
    if m1.empty:
        raise HTTPException(400, "no data")
    cutoff = m1["time"].iloc[-1] - timedelta(days=req.days)
    m1 = m1[m1["time"] >= cutoff - timedelta(days=60)].reset_index(drop=True)
    warm_idx = int(m1["time"].searchsorted(cutoff)) // 5
    bt = Backtest(m1, live.spec, req.start_balance, req.max_layers, req.budget_pct, req.slippage_points,
                  warmup_bars=max(300, warm_idx), news_gate=gate if req.use_news_gate else None, weights=req.weights,
                  bias_min_score=req.bias_min_score, struct_oppose_score=req.struct_oppose_score,
                  session_thresholds=req.session_thresholds, session_min_aligned=req.session_min_aligned,
                  min_risk_usd=req.min_risk_usd, max_risk_usd=req.max_risk_usd,
                  fixed_lots=req.fixed_lots, sl_dollars=req.sl_dollars, tp_dollars=req.tp_dollars)
    loop = asyncio.get_event_loop()

    def on_progress(p):
        asyncio.run_coroutine_threadsafe(hub.broadcast({"type": "backtest_progress", "id": bt.id, "progress": round(p, 3)}), loop)
    runner.start(bt, on_progress)
    asyncio.create_task(_await_backtest(bt))
    return {"id": bt.id, "status": bt.status, "m5_bars": int(len(m1) // 5)}


async def _await_backtest(bt: Backtest):
    while bt.status in ("pending", "running"):
        await asyncio.sleep(0.5)
    if bt.result:
        doc = {k: v for k, v in bt.result.items() if k != "trades"}
        doc["trade_count"] = len(bt.result["trades"])
        store.upsert_backtest(doc)
        for t in bt.result["trades"]:
            store.upsert_trade(dict(t, backtest_id=bt.id))
    await hub.broadcast({"type": "backtest_done", "id": bt.id, "status": bt.status, "error": bt.error})


@api.get("/backtest")
async def backtest_list():
    return store.list_backtests(20)


@api.get("/backtest/{bt_id}")
async def backtest_get(bt_id: str):
    bt = runner.runs.get(bt_id)
    if bt:
        if bt.result:
            slim = _slim_trades(bt.result.get("trades") or [])
            payload = {k: v for k, v in bt.result.items() if k != "trades"}
            payload.update({"status": bt.status, "progress": bt.progress,
                            "bar_count": len(bt.bars), "trades": slim, "trade_count": len(slim)})
            return payload
        return {"id": bt.id, "status": bt.status, "progress": bt.progress, "error": bt.error, "bar_count": len(bt.bars)}
    doc = store.get_backtest(bt_id)
    if not doc:
        raise HTTPException(404, "not found")
    return doc

@api.get("/backtest/{bt_id}/trades")
async def backtest_trades(bt_id: str):
    bt = runner.runs.get(bt_id)
    if bt and bt.result:
        return _slim_trades(bt.result.get("trades") or [])
    return _slim_trades(store.list_trades(status=None, backtest_id=bt_id, limit=8000, order="timestamp", descending=False))

@api.get("/backtest/{bt_id}/export")
async def backtest_export(bt_id: str, fmt: str = "json"):
    bt = runner.runs.get(bt_id)
    if bt and bt.result:
        doc, trades = bt.result, bt.result.get("trades") or []
    else:
        doc = store.get_backtest(bt_id)
        trades = store.list_trades(status=None, backtest_id=bt_id, limit=5000, order="timestamp", descending=False)
    if not doc:
        raise HTTPException(404, "backtest not finished or not found")
    return {"ok": True, "path": write_report(bt_id, fmt, doc, trades), "fmt": fmt}

@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "snapshot", "status": live.status()}, default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.clients.discard(ws)


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
                   allow_methods=["*"], allow_headers=["*"])


def _ui_dir() -> Optional[Path]:
    raw = os.environ.get("MIBGOLD_UI_DIR")
    candidates = []
    if raw:
        candidates.append(Path(raw))
    candidates.append(ROOT_DIR / "ui")
    candidates.append(ROOT_DIR.parent / "frontend" / "build")
    for p in candidates:
        if (p / "index.html").is_file():
            return p
    return None


UI_DIR = _ui_dir()
if UI_DIR is not None:
    assets = UI_DIR / "static"
    if assets.is_dir():
        app.mount("/static", StaticFiles(directory=str(assets)), name="static")

    @app.get("/")
    async def ui_index():
        return FileResponse(UI_DIR / "index.html")

    @app.get("/{path:path}")
    async def ui_spa(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "not found")
        target = (UI_DIR / path).resolve()
        try:
            target.relative_to(UI_DIR.resolve())
        except ValueError:
            raise HTTPException(404, "not found")
        if target.is_file():
            return FileResponse(target)
        return FileResponse(UI_DIR / "index.html")
else:
    @app.get("/")
    async def no_ui():
        return {"app": "mib-gold", "ui": False, "hint": "build frontend or open /api"}
