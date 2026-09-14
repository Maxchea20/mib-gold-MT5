# mib-gold

Desktop XAUUSD terminal. **One process.** Engine + UI on `http://127.0.0.1:8001`.
No Mongo. No separate frontend server.

```
python run_app.py
```

Then open that URL. That is the operate path.

Tauri still wraps the same sidecar: double-click the built `.exe` and it spawns the engine, then kills it when the window closes.

## Layout

```
run_app.py                  one-command host
backend/
  sidecar.py                uvicorn on 127.0.0.1:8001, serves /api and built UI
  server.py                 FastAPI + WebSocket
  mibgold/store.py          SQLite (backend/data/mibgold.sqlite)
  mibgold/                  engines, book, risk, adapters, live, backtest
frontend/                   React UI (build once, then served by sidecar)
desktop/src-tauri/          window + sidecar spawn/kill
```

## Daily use (sim, any OS)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # mac/linux
pip install -r requirements.txt
cd ..
python run_app.py
```

Optional first time if you want the UI from the same port:

```bash
cd frontend && yarn && yarn build && cd ..
python run_app.py
```

If `frontend/build` is missing you still get `/api`. Build the UI once; you do not run `yarn start` next to uvicorn.

## MT5 (Windows)

In `backend/.env`:

```
BROKER_MODE=mt5
MT5_SYMBOL=GOLD
MT5_SERVER=XMGlobal-MT5 2
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_SERVER_UTC_OFFSET_HOURS=3
```

Install `MetaTrader5` into the same venv. Keep the MT5 terminal logged in with Algo Trading on. Then `python run_app.py`.

## Desktop .exe

```
cd backend && pip install pyinstaller && pyinstaller --onefile --name mibgold-backend-x86_64-pc-windows-msvc sidecar.py
mkdir ..\desktop\src-tauri\binaries && move dist\mibgold-backend-x86_64-pc-windows-msvc.exe ..\desktop\src-tauri\binaries\
cd ..\frontend && yarn build
cd ..\desktop && cargo tauri build
```

Open the installed app only. Sidecar starts and dies with the window.

## Env

`MAX_LAYERS` `RISK_BUDGET_PCT` `NEWS_WINDOW_BEFORE_MIN` `NEWS_WINDOW_AFTER_MIN`
`TICK_POLL_MS` `AUTO_TRADE` `SIM_SPEED` `SIM_START_BALANCE` `MIBGOLD_DB` `MIBGOLD_UI_DIR` `PORT`
`EMERGENT_LLM_KEY` is optional (news advisory only).
