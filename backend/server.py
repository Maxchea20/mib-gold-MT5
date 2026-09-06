from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List, Set
from datetime import datetime, timezone, timedelta
from pathlib import Path
import asyncio
import json
import logging
import os

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mibgold.server")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
    await db.trades.update_one({"id": rec["id"]}, {"$set": rec}, upsert=True)


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
    asyncio.create_task(live.run())


@app.on_event("shutdown")
async def _shutdown():
    client.close()
    adapter.shutdown()


# ---------------- REST ----------------
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
    """Current LIVE engine weights (applies to real-time trading, not backtests)."""
    return live.strategy.consensus.weights


@api.post("/weights")
async def set_weights(body: dict):
    """Update one or more LIVE engine weights immediately (no restart needed) and persist to disk
    so the change survives a server restart. Backtests are unaffected - they take weights per-run."""
    live.strategy.consensus.weights.update(body)
    WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_FILE.write_text(json.dumps(live.strategy.consensus.weights))
    return live.strategy.consensus.weights


@api.post("/weights/reset")
async def reset_weights():
    """Reset LIVE engine weights back to the built-in defaults and remove the persisted override file."""
    live.strategy.consensus.weights = dict(DEFAULT_WEIGHTS)
    if WEIGHTS_FILE.exists():
        WEIGHTS_FILE.unlink()
    return live.strategy.consensus.weights


@api.get("/chart")
async def chart(tf: str = "M5", n: int = 400):
    if tf not in ("M1", "M5", "H1", "H4", "D1"):
        raise HTTPException(400, "bad timeframe")
    return {"tf": tf, "bars": live.chart(tf, n)}


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
    q = {"status": "closed"}
    if direction:
        q["direction"] = direction
    if session:
        q["session"] = session
    if outcome:
        q["outcome"] = outcome
    if mode:
        q["mode"] = mode
    if backtest_id:
        q["backtest_id"] = backtest_id
    if engine:
        q[f"agent_votes.{engine}.signal"] = {"$in": ["long", "short"]}
        q["$expr"] = {"$eq": [f"$agent_votes.{engine}.signal", "$direction"]}
    docs = await db.trades.find(q, {"_id": 0}).sort("exit_time", -1).to_list(limit)
    return docs


@api.get("/trades/stats")
async def trade_stats(mode: Optional[str] = None, backtest_id: Optional[str] = None):
    from mibgold.backtest.attribution import summary_stats
    q = {"status": "closed"}
    if mode:
        q["mode"] = mode
    if backtest_id:
        q["backtest_id"] = backtest_id
    docs = await db.trades.find(q, {"_id": 0}).to_list(5000)
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
    """Manually trigger the AI layer on a release (e.g. to test). Never called by the hot path."""
    if not interpreter.enabled:
        raise HTTPException(400, "EMERGENT_LLM_KEY not configured")
    e = NewsEvent(ev.title, ev.country, datetime.fromisoformat(ev.time).astimezone(timezone.utc), ev.impact, ev.forecast, ev.previous, ev.actual, "manual")
    adv = await interpreter.interpret_now(e, live.tick.time if live.tick else None)
    await hub.broadcast({"type": "advisory", "advisory": adv})
    return adv


# ---------------- backtest ----------------
class BacktestRequest(BaseModel):
    days: int = 10
    start_balance: float = 100.0
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
    min_risk_usd: float = 10.0
    max_risk_usd: float = 100.0


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
        # MT5's copy_rates_range silently rejects overly large windows (observed: OK up to ~50 days,
        # fails at 70+ with "Invalid params"). Cap warmup so req.days + warmup stays safely under that.
        max_total_days = int(os.environ.get("BACKTEST_MAX_TOTAL_DAYS", "45"))
        warmup_days = max(5, min(60, max_total_days - req.days))
        m1 = adapter.m1_range(end - timedelta(days=req.days + warmup_days), end)
    if m1.empty:
        raise HTTPException(400, "no data")
    cutoff = m1["time"].iloc[-1] - timedelta(days=req.days)
    # keep 60 days of warmup for D1/H4 engines but only trade the last `days`
    m1 = m1[m1["time"] >= cutoff - timedelta(days=60)].reset_index(drop=True)
    warm_idx = int(m1["time"].searchsorted(cutoff)) // 5
    bt = Backtest(m1, live.spec, req.start_balance, req.max_layers, req.budget_pct, req.slippage_points,
                  warmup_bars=max(300, warm_idx), news_gate=gate if req.use_news_gate else None, weights=req.weights,
                  bias_min_score=req.bias_min_score, struct_oppose_score=req.struct_oppose_score,
                  session_thresholds=req.session_thresholds, session_min_aligned=req.session_min_aligned,
                  min_risk_usd=req.min_risk_usd, max_risk_usd=req.max_risk_usd)
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
        await db.backtests.update_one({"id": bt.id}, {"$set": doc}, upsert=True)
        for t in bt.result["trades"]:
            t2 = dict(t, backtest_id=bt.id)
            await db.trades.update_one({"id": t["id"]}, {"$set": t2}, upsert=True)
    await hub.broadcast({"type": "backtest_done", "id": bt.id, "status": bt.status, "error": bt.error})


@api.get("/backtest")
async def backtest_list():
    docs = await db.backtests.find({}, {"_id": 0, "equity_curve": 0, "attribution": 0}).sort("created", -1).to_list(20)
    return docs


@api.get("/backtest/{bt_id}")
async def backtest_get(bt_id: str):
    bt = runner.runs.get(bt_id)
    if bt:
        if bt.result:
            return {k: v for k, v in bt.result.items() if k != "trades"} | {"status": bt.status, "progress": bt.progress, "bar_count": len(bt.bars)}
        return {"id": bt.id, "status": bt.status, "progress": bt.progress, "error": bt.error, "bar_count": len(bt.bars)}
    doc = await db.backtests.find_one({"id": bt_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    return doc


@api.get("/backtest/{bt_id}/trades")
async def backtest_trades(bt_id: str):
    bt = runner.runs.get(bt_id)
    if bt and bt.result:
        return bt.result["trades"]
    return await db.trades.find({"backtest_id": bt_id}, {"_id": 0}).sort("timestamp", 1).to_list(5000)


@api.get("/backtest/{bt_id}/bars")
async def backtest_bars(bt_id: str, start: int = 0, count: int = 600):
    bt = runner.runs.get(bt_id)
    if not bt:
        raise HTTPException(404, "replay frames only kept in memory for recent runs")
    return {"total": len(bt.bars), "start": start, "bars": bt.bars[start:start + count]}


@api.post("/backtest/{bt_id}/stop")
async def backtest_stop(bt_id: str):
    bt = runner.runs.get(bt_id)
    if not bt:
        raise HTTPException(404, "not found")
    bt.stop()
    return {"status": "stopping"}


# ---------------- WebSocket ----------------
@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "snapshot", "status": live.status()}, default=str))
        while True:
            await ws.receive_text()  # keepalive / ignore client messages
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.clients.discard(ws)


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
                   allow_methods=["*"], allow_headers=["*"])