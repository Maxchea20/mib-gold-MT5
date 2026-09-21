import axios from "axios";

function resolveBackend() {
  if (process.env.REACT_APP_BACKEND_URL) {
    return process.env.REACT_APP_BACKEND_URL.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    if (window.__TAURI_INTERNALS__ || window.__TAURI__) {
      return "http://127.0.0.1:8001";
    }
    if (window.location && window.location.origin && window.location.origin !== "null") {
      return window.location.origin;
    }
  }
  return "http://127.0.0.1:8001";
}

export const BACKEND_URL = resolveBackend();
export const API = `${BACKEND_URL}/api`;
export const WS_URL = BACKEND_URL.replace(/^http/, "ws") + "/api/ws";

const http = axios.create({ baseURL: API, timeout: 20000 });
const longHttp = axios.create({ baseURL: API, timeout: 180000 });

export const api = {
  status: () => http.get("/status").then((r) => r.data),
  config: () => http.get("/config").then((r) => r.data),
  weights: () => http.get("/weights").then((r) => r.data),
  setWeights: (partial) => http.post("/weights", partial).then((r) => r.data),
  resetWeights: () => http.post("/weights/reset").then((r) => r.data),
  chart: (tf, n = 400) => http.get("/chart", { params: { tf, n } }).then((r) => r.data),
  layers: () => http.get("/layers").then((r) => r.data),
  closeLayer: (id) => http.post(`/layers/${id}/close`).then((r) => r.data),
  setAutoTrade: (enabled) => http.post("/auto-trade", { enabled }).then((r) => r.data),
  trades: (params) => http.get("/trades", { params }).then((r) => r.data),
  tradeStats: (params) => http.get("/trades/stats", { params }).then((r) => r.data),
  news: () => http.get("/news").then((r) => r.data),
  events: () => http.get("/events").then((r) => r.data),
  addManualNews: (ev) => http.post("/news/manual", ev).then((r) => r.data),
  interpretNews: (ev) => http.post("/news/interpret", ev).then((r) => r.data),
  runBacktest: (body) => http.post("/backtest/run", body).then((r) => r.data),
  backtests: () => http.get("/backtest").then((r) => r.data),
  backtest: (id) => http.get(`/backtest/${id}`).then((r) => r.data),
  backtestTrades: (id) => longHttp.get(`/backtest/${id}/trades`).then((r) => r.data),
  backtestBars: (id, start, count) => http.get(`/backtest/${id}/bars`, { params: { start, count } }).then((r) => r.data),
  exportBacktest: (id, fmt) => http.get(`/backtest/${id}/export`, { params: { fmt } }).then((r) => r.data),
};
