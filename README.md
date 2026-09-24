# mib-gold

Desktop XAUUSD terminal. **One process.** Engine + UI on `http://127.0.0.1:8001`.

## Keeper book (live)

- Lot **0.02** · SL **$2.5** · TP **$5** · L1 only
- Skip **London**, **Friday**, **19:00 UTC**
- News gate **on** ±**30 min** around USD high-impact (NFP / CPI / FOMC)
- Daily loss limit: no new trades after **3 full stop-losses** down on the UTC day (`MAX_DAILY_LOSS_USD`)
- MT5 SL/TP are the source of truth; open bot positions are picked back up after a restart
- Trail **off**. Minute brain time-stops dead fills at 20m / <0.15R
- Auto-trade **on**

Copy `backend/.env.example` to `backend/.env` and fill MT5 login/path.

```
python run_app.py
```

Open `http://127.0.0.1:8001`. Leave Auto-trade enabled. MT5 must be logged in with Algo Trading on.

## Layout

```
run_app.py                  one-command host
backend/
  sidecar.py                uvicorn on 127.0.0.1:8001, serves /api and built UI
  server.py                 FastAPI + WebSocket
  mibgold/                  engines, book, live, backtest, news gate
frontend/                   React UI (build once, served by sidecar)
desktop/src-tauri/          window + sidecar spawn/kill
```

## First run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
cd ..\frontend && yarn && yarn build && cd ..
python run_app.py
```

## MT5 (Windows)

`backend/.env`:

```
BROKER_MODE=mt5
MT5_SYMBOL=GOLD#
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
AUTO_TRADE=true
MAX_LAYERS=1
FIXED_LOTS=0.02
SL_DOLLARS=1.5
TP_DOLLARS=3
NEWS_WINDOW_BEFORE_MIN=30
NEWS_WINDOW_AFTER_MIN=30
```

Install `MetaTrader5` in the same venv. Terminal logged in. Algo Trading ON. Then `python run_app.py`.

Status `/api/status` should show `auto_trade: true`, `book_rules` lot 0.02 / sl 1.5 / tp 3, and `news.blocked` around prints.
