# mib-gold

Desktop XAUUSD trading system: Python engine suite + FastAPI (WebSocket push) + React UI wrapped in Tauri.

```
backend/
  server.py                 FastAPI + /api/ws WebSocket hub, REST, backtest runner
  sidecar.py                Tauri sidecar entrypoint (PyInstaller)
  mibgold/
    contracts.py            Signal contract, Layer, money/R text helpers
    engines/                10 engines (OHLCV in -> Signal out, never touch MT5)
    consensus.py            weighted voting, Elliott downweighted, session thresholds
    strategy.py             D1/H4 bias -> H1 structure -> M5 sniper entry
    risk.py                 shared 10% budget across hedged layers, EqualSplitAllocation (swappable)
    trailing.py             trailing TP / protective stop ratchet
    book.py                 PositionBook (layers, exits, records) used by live + backtest
    journal.py              full justification records (10 votes + summary + R + plain-English $)
    news/calendar.py        hard news gate: ForexFactory JSON + data/manual_events.json, pure timestamp logic
    news/ai_interpreter.py  async Claude Sonnet 4.6 advisory (never blocks execution)
    adapters/mt5_adapter.py real MetaTrader5 adapter (Windows)
    adapters/sim.py         synthetic gold / CSV replay adapter with accelerated clock
    backtest/harness.py     bar-by-bar walk-forward, spread + slippage, per-engine attribution
frontend/                   React terminal UI (Terminal / Journal / Backtest Lab)
desktop/src-tauri/          Tauri 2 shell that spawns the backend sidecar
```

## Run locally (sim mode, any OS)
Backend `BROKER_MODE=sim` (default). Frontend uses `REACT_APP_BACKEND_URL`.

## Run against MT5 (Windows)
1. Install MT5 terminal (XM), log in to the hedging demo account, enable *Algo Trading*.
2. `pip install MetaTrader5` then in `backend/.env`:
   ```
   BROKER_MODE=mt5
   MT5_SYMBOL=GOLD            # XM names gold "GOLD" (fallback XAUUSD); check Market Watch
   MT5_LOGIN=12345678         # optional; leave empty to reuse the terminal's logged-in session
   MT5_PASSWORD=...
   MT5_SERVER=XMGlobal-MT5 2
   MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
   MT5_SERVER_UTC_OFFSET_HOURS=3   # XM server time is GMT+2/+3 (DST) - keep sessions honest
   ```
3. `uvicorn server:app --port 8001` and open the UI. `GET /api/connection` returns the symbol spec
   (contract size, min lot, spread) straight from `symbol_info` — build step 1 of the spec.

## Replay real M1 data from MT5 (CSV)
In MT5: Tools → History Center / Symbols → Export bars for GOLD, M1 → save as `.csv`.
Set `SIM_CSV_PATH=C:\data\GOLD_M1.csv` (sim mode) or pass `csv_path` in `POST /api/backtest/run`.

## Build the desktop .exe (Windows)
```
cd backend && pip install pyinstaller && pyinstaller --onefile --name mibgold-backend-x86_64-pc-windows-msvc sidecar.py
mkdir ..\desktop\src-tauri\binaries && move dist\mibgold-backend-x86_64-pc-windows-msvc.exe ..\desktop\src-tauri\binaries\
cd ..\desktop && cargo install tauri-cli --version "^2" && cargo tauri build
```
Add an `icons/icon.ico` under `desktop/src-tauri` (any 256px icon) before building.

## Key env knobs
`MAX_LAYERS=3` `RISK_BUDGET_PCT=0.10` `NEWS_WINDOW_BEFORE_MIN=30` `NEWS_WINDOW_AFTER_MIN=30`
`TICK_POLL_MS=100` `AUTO_TRADE=true` `SIM_SPEED=30` `SIM_START_BALANCE=100` `EMERGENT_LLM_KEY` (AI news layer).
