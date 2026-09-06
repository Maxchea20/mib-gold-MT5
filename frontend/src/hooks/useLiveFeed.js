import { useEffect, useRef, useState, useCallback } from "react";
import { api, WS_URL } from "@/lib/api";

// Single WebSocket feed shared by the whole app. Falls back to REST polling if the socket cannot connect.
export default function useLiveFeed() {
  const [status, setStatus] = useState(null);
  const [tick, setTick] = useState(null);
  const [layers, setLayers] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [news, setNews] = useState({ blocked: false });
  const [account, setAccount] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [lastTrades, setLastTrades] = useState([]);
  const [barUpdates, setBarUpdates] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const [connected, setConnected] = useState(false);
  const [transport, setTransport] = useState("connecting");
  const wsRef = useRef(null);
  const pollRef = useRef(null);

  const applySnapshot = useCallback((s) => {
    setStatus(s);
    setTick(s.tick);
    setAnalysis(s.analysis);
    setNews(s.news);
    setAdvisory(s.advisory);
    setAccount({ equity: s.account.equity, balance: s.account.balance, floating_pnl: s.account.floating_pnl,
      risk_used_pct: s.account.risk_used_pct, risk_used_usd: s.account.risk_used_usd, today_pnl: s.today_pnl,
      risk_budget_pct: s.account.risk_budget_pct, max_layers: s.account.max_layers });
    setLayers(s.account.layers);
  }, []);

  useEffect(() => {
    let closed = false, retry = 0;
    const startPolling = () => {
      if (pollRef.current) return;
      setTransport("polling");
      pollRef.current = setInterval(() => api.status().then(applySnapshot).catch(() => {}), 1000);
    };
    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => { retry = 0; setConnected(true); setTransport("websocket"); if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        switch (m.type) {
          case "snapshot": applySnapshot(m.status); break;
          case "tick":
            setTick(m.tick); setLayers(m.layers); setNews(m.news);
            setAccount((a) => ({ ...(a || {}), equity: m.equity, balance: m.balance, floating_pnl: m.floating_pnl,
              risk_used_pct: m.risk_used_pct, risk_used_usd: m.risk_used_usd, today_pnl: m.today_pnl }));
            break;
          case "bars": setBarUpdates({ bars: m.bars, ts: Date.now() }); setNews(m.news); break;
          case "analysis": setAnalysis(m.analysis); setLayers(m.layers); break;
          case "news": setNews(m.news); break;
          case "advisory": setAdvisory(m.advisory); break;
          case "trade_opened": setLastTrades((t) => [{ kind: "open", ...m.trade }, ...t].slice(0, 30)); break;
          case "trade_closed": setLastTrades((t) => [{ kind: "close", ...m.trade }, ...t].slice(0, 30)); break;
          case "auto_trade": setStatus((s) => (s ? { ...s, auto_trade: m.enabled } : s)); break;
          case "backtest_progress": setBacktest({ id: m.id, progress: m.progress, done: false }); break;
          case "backtest_done": setBacktest({ id: m.id, progress: 1, done: true, status: m.status, error: m.error, ts: Date.now() }); break;
          default: break;
        }
      };
      ws.onclose = () => { setConnected(false); if (closed) return; retry += 1; if (retry >= 2) startPolling(); setTimeout(connect, Math.min(1000 * retry, 5000)); };
      ws.onerror = () => ws.close();
    };
    api.status().then(applySnapshot).catch(() => {});
    connect();
    return () => { closed = true; wsRef.current?.close(); if (pollRef.current) clearInterval(pollRef.current); };
  }, [applySnapshot]);

  return { status, tick, layers, analysis, news, account, advisory, lastTrades, barUpdates, backtest, connected, transport, setStatus };
}
