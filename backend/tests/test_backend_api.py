"""Backend API tests for mib-gold trading system."""
import os
import time
import json
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mib-gold-trader.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ENGINES = {"trend", "sr", "breakout", "momentum", "volume", "fibonacci", "elliott", "fvg", "pattern", "structure"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------------- Basics / status ----------------
def test_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    d = r.json()
    assert d.get("app") == "mib-gold"


def test_status(s):
    r = s.get(f"{API}/status")
    assert r.status_code == 200
    d = r.json()
    assert "connection" in d
    assert d["connection"].get("mode") == "sim"
    assert "tick" in d and d["tick"] is not None
    assert "bid" in d["tick"] and "ask" in d["tick"]
    assert "account" in d
    acct = d["account"]
    for k in ("equity", "balance", "risk_used_pct", "layers"):
        assert k in acct, f"missing account key: {k}"
    assert "news" in d


def test_config(s):
    r = s.get(f"{API}/config")
    assert r.status_code == 200
    d = r.json()
    w = d["weights"]
    for e in ENGINES:
        assert e in w, f"missing engine weight: {e}"
    # elliott should be lowest
    assert w["elliott"] == min(w.values()), f"elliott not lowest: {w}"
    assert abs(w["elliott"] - 0.35) < 1e-6
    assert d["risk"]["budget_pct"] == 0.10
    assert d["risk"]["max_layers"] == 3
    assert "session_thresholds" in d


@pytest.mark.parametrize("tf", ["M5", "H1", "H4", "D1"])
def test_chart_valid(s, tf):
    r = s.get(f"{API}/chart", params={"tf": tf, "n": 50})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tf"] == tf
    bars = d["bars"]
    assert isinstance(bars, list) and len(bars) > 0
    b = bars[0]
    for k in ("time", "open", "high", "low", "close", "volume"):
        assert k in b


def test_chart_invalid_tf(s):
    r = s.get(f"{API}/chart", params={"tf": "XX"})
    assert r.status_code == 400


def test_analysis(s):
    # Wait up to ~15s for warmup + first M5 close
    votes = None
    for _ in range(20):
        r = s.get(f"{API}/analysis")
        assert r.status_code == 200
        d = r.json()
        votes = d.get("votes") or {}
        if votes and set(votes.keys()) >= ENGINES:
            break
        time.sleep(1)
    assert votes and set(votes.keys()) >= ENGINES, f"votes missing engines: {set(votes or {})}"
    for k, v in votes.items():
        assert v["signal"] in {"long", "short", "neutral"}
        assert 0.0 <= v["confidence"] <= 1.0
        assert "reason" in v
    for k in ("entry", "bias", "timeframes", "summary", "fire", "gate_reason"):
        assert k in d


# ---------------- news ----------------
def test_news(s):
    r = s.get(f"{API}/news")
    assert r.status_code == 200
    d = r.json()
    assert "gate" in d
    assert "blocked" in d["gate"]
    assert "events_loaded" in d["gate"]
    assert d["gate"]["events_loaded"] > 0


def test_news_manual_blocks(s):
    # get sim time from status
    st = s.get(f"{API}/status").json()
    sim_time = st["tick"]["time"]
    t = datetime.fromisoformat(sim_time.replace("Z", "+00:00")) + timedelta(minutes=5)
    payload = {"title": "TEST_manual_event", "time": t.isoformat(), "impact": "High"}
    r = s.post(f"{API}/news/manual", json=payload)
    assert r.status_code == 200
    d = r.json()
    assert d.get("blocked") is True


@pytest.mark.slow
def test_news_interpret(s):
    payload = {
        "title": "US CPI m/m",
        "time": "2026-09-07T12:30:00+00:00",
        "actual": "0.5%", "forecast": "0.3%", "previous": "0.2%",
        "impact": "High"
    }
    r = s.post(f"{API}/news/interpret", json=payload, timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("bias") in {"long", "short", "neutral"}
    assert "strength" in d
    assert "note" in d
    assert "claude" in (d.get("model", "").lower())


# ---------------- auto trade ----------------
def test_auto_trade_toggle(s):
    r = s.post(f"{API}/auto-trade", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["auto_trade"] is False
    r = s.post(f"{API}/auto-trade", json={"enabled": True})
    assert r.json()["auto_trade"] is True
    st = s.get(f"{API}/status").json()
    assert st.get("auto_trade") is True
    # revert
    s.post(f"{API}/auto-trade", json={"enabled": False})


# ---------------- trades ----------------
def test_trades_list(s):
    r = s.get(f"{API}/trades", params={"limit": 10})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_trades_filters(s):
    for params in [{"direction": "long"}, {"outcome": "win"}, {"session": "asian"},
                   {"engine": "trend"}, {"mode": "backtest"}]:
        r = s.get(f"{API}/trades", params=params)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_trades_stats(s):
    r = s.get(f"{API}/trades/stats")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, dict)


# ---------------- backtest ----------------
@pytest.mark.slow
def test_backtest_full_flow(s):
    r = s.post(f"{API}/backtest/run", json={"days": 5})
    assert r.status_code == 200, r.text
    bt_id = r.json()["id"]

    deadline = time.time() + 90
    status_doc = None
    while time.time() < deadline:
        r = s.get(f"{API}/backtest/{bt_id}")
        assert r.status_code == 200
        status_doc = r.json()
        if status_doc.get("status") == "done":
            break
        if status_doc.get("status") in ("error", "stopped"):
            pytest.fail(f"backtest failed: {status_doc}")
        time.sleep(2)
    assert status_doc and status_doc.get("status") == "done", f"timeout: {status_doc}"

    stats = status_doc.get("stats") or {}
    for k in ("trades", "win_rate", "profit_factor", "avg_r", "net_pnl", "net_pnl_text"):
        assert k in stats, f"missing stats key {k}: {stats}"
    assert isinstance(stats["net_pnl_text"], str)
    assert stats["net_pnl_text"].startswith("Profited") or stats["net_pnl_text"].startswith("Lost")
    attr = status_doc.get("attribution") or {}
    assert set(attr.keys()) >= ENGINES, f"missing engines in attribution: {set(attr)}"
    for k, v in attr.items():
        assert "edge" in v and "recommendation" in v
    assert isinstance(status_doc.get("equity_curve"), list)
    assert "range" in status_doc

    # trades
    r = s.get(f"{API}/backtest/{bt_id}/trades")
    assert r.status_code == 200
    trades = r.json()
    if trades:  # trades may be sparse
        t0 = trades[0]
        assert set(t0.get("agent_votes", {}).keys()) >= ENGINES
        for k in ("summary", "r_multiple", "r_text", "pnl_text", "exit_reason", "layer_number", "session", "consensus", "mode"):
            assert k in t0, f"trade missing {k}"
        assert t0["mode"] == "backtest"
        assert t0["pnl_text"].startswith("Profited") or t0["pnl_text"].startswith("Lost")

    # bars
    r = s.get(f"{API}/backtest/{bt_id}/bars", params={"start": 0, "count": 50})
    assert r.status_code == 200
    bd = r.json()
    assert "total" in bd and isinstance(bd["bars"], list)

    # list
    r = s.get(f"{API}/backtest")
    assert r.status_code == 200
    lst = r.json()
    assert any(x.get("id") == bt_id for x in lst)


# ---------------- websocket ----------------
def test_websocket_stream():
    try:
        from websockets.sync.client import connect
    except Exception:
        pytest.skip("websockets not installed")
    ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"
    got_snapshot = False
    got_tick = False
    with connect(ws_url, open_timeout=10, close_timeout=5) as ws:
        deadline = time.time() + 15
        while time.time() < deadline and not (got_snapshot and got_tick):
            try:
                msg = ws.recv(timeout=5)
            except Exception:
                break
            data = json.loads(msg)
            t = data.get("type")
            if t == "snapshot":
                got_snapshot = True
            elif t == "tick":
                got_tick = True
                tick = data.get("tick") or {}
                assert "bid" in tick and "ask" in tick
    assert got_snapshot, "no snapshot message"
    assert got_tick, "no tick message"
