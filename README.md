# mib-gold

Desktop XAUUSD terminal. **One process.** Engine + UI on `http://127.0.0.1:8001`.

## Keeper book (live)

- Lot **0.02** · SL **$2.5** · TP **$5** · L1 only
- Skip **London**, **Friday**, **19:00 UTC**
- News gate **on** ±**30 min** around USD high-impact (NFP / CPI / FOMC)
- Daily loss limit: no new trades after **3 full stop-losses** down on the UTC day (`MAX_DAILY_LOSS_USD`)
- MT5 SL/TP are the source of truth; open bot positions are picked back up after a restart
- Trail **off**. Minute brain time-stops dead fills at 45m / <0.15R
- Auto-trade **on**

Copy `backend/.env.example` to `backend/.env` and fill MT5 login/path.

```
python run_app.py
```

Open `http://127.0.0.1:8001`. Leave Auto-trade enabled. MT5 must be logged in with Algo Trading on.

## Broker clock

MT5 bars and ticks come in broker server time. The app converts everything to UTC
(sessions, skip hours, news gate). Default: New York close clock (UTC+3 in US summer,
UTC+2 otherwise), checked against live ticks. Pin a fixed clock with
`MT5_SERVER_UTC_OFFSET_HOURS` only if your broker runs something else.

On first start after this change the bar cache (`backend/data/mibgold.sqlite`) keeps its
old server-time bars in `m1_bars_server_time_backup` and refills in UTC.

## Backtest the live rules

Plain Python, no pandas needed:

```
cd backend
python -m mibgold.backtest.replay_live "data/GOLD#_M1_202606031118_202609141118.csv"
python -m mibgold.backtest.replay_live "data/GOLD#_M1_....csv" --sl 3 --tp 6 --no-time-stop
```

Includes spread, calendar cuts, time-stop and daily loss limit. Not modelled: news gate, commission.

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
SL_DOLLARS=2.5
TP_DOLLARS=5
DEAD_FILL_MIN=45
NEWS_WINDOW_BEFORE_MIN=30
NEWS_WINDOW_AFTER_MIN=30
```

Install `MetaTrader5` in the same venv (`pip install MetaTrader5`). Terminal logged in. Algo Trading ON. Then `python run_app.py`.

Status `/api/status` should show `auto_trade: true`, `book_rules` lot 0.02 / sl 2.5 / tp 5, and `news.blocked` around prints.
