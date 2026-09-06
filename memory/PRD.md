# mib-gold — PRD / living memory

## Original problem statement (condensed)
Desktop XAUUSD trading system "mib-gold": Python + official MetaTrader5 package (Windows, IPC to local MT5, XM hedging account), Tauri (Rust + React) UI.
Broker-/time-agnostic engines (OHLCV in → standardized Signal {signal, confidence, reason, raw_data}). 10 engines: Trend, S/R, Breakout, Momentum (session-normalized), Volume (tick proxy), Fibonacci, Elliott (low weight), FVG (ATR-gated, contract-size adjusted), Pattern, Market Structure.
Weighted session-aware consensus; D1/H4 bias → H1 structure → M5 entry. Risk: 10% capital stop shared across ALL hedged layers, equal-split across max 3 layers (swappable allocation), trailing TP. News gate: hard calendar block (±30m, rule-only) + async Claude advisory (non-blocking). Every trade logs all 10 votes + rule-based summary + R-multiple + plain-English $ (Floating/Profited/Lost). Bar-by-bar backtest with spread/slippage + per-engine attribution. Dark terminal UI: Terminal, Journal, Backtest Lab.

## User choices
- Linux sandbox → SIM adapter (synthetic + CSV replay) here; MT5 adapter code complete for Windows.
- Tauri scaffold (desktop/src-tauri) + React UI previewed in browser; user builds .exe on Windows.
- News source: ForexFactory JSON + manual_events.json. AI: Claude Sonnet 4.6 via Emergent key.
- Backend→UI: WebSocket push (/api/ws), backend polls adapter every 100ms. Max layers 3, window ±30m.

## Architecture
backend/server.py (FastAPI, WS hub, REST, backtest runner) · mibgold/{contracts, engines/*, consensus, session, strategy, risk, trailing, book, journal, live, news/{calendar, ai_interpreter}, adapters/{base, sim, mt5_adapter, resample}, backtest/{harness, attribution}} · frontend React (Terminal/Journal/BacktestLab, lightweight-charts, recharts) · desktop/src-tauri (Tauri 2 + sidecar) · backend/sidecar.py.
Mongo collections: trades (closed records, incl. backtest trades with backtest_id), backtests.

## Implemented (2026-09-05, session 1)
- All 10 engines + EngineSuite, consensus with Elliott 0.35 weight, session thresholds.
- Top-down strategy, RiskManager (shared 10%, EqualSplitAllocation), TrailingTP, PositionBook, journal records.
- SimAdapter (synthetic gold M1, CSV import, accelerated clock, sim news events), MT5Adapter (untested here — Windows only).
- NewsGate (FF feed + manual + sim), NewsInterpreter (Claude, async, advisory flag).
- LiveEngine paper loop (10Hz ticks → WS), backtest harness + attribution, REST API.
- UI: TopBar, NewsBanner (countdown), PriceChart (TF switch, layer lines/markers), AgentBoard, LayersPanel, TradeCard/JustificationCard, Journal filters, Backtest Lab (run, progress, equity curve, scrubber, replay chart, attribution).
- Tests: tests/test_risk.py; backend/tests/test_backend_api.py (testing agent, 18/18 pass). Frontend verified by testing agent.

## Backlog
P0: Run on Windows against XM MT5 demo — verify symbol spec (GOLD vs XAUUSD), server UTC offset, order_send filling mode; reconcile book with broker positions on restart.
P1: Adaptive allocation model; weight re-tuning UI from attribution; CSV upload endpoint from UI; per-bar replay persistence beyond memory; walk-forward/OOS validation.
P2: Tauri icon + CI build script; MT5 position reconciliation; alerts/sounds; export journal CSV.
