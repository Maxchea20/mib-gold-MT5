"""Local M1 history cache in backend/data/mibgold.sqlite. Code is in git; bars stay on disk."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import sqlite3
import pandas as pd


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS m1_bars (
            symbol TEXT NOT NULL,
            ts INTEGER NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            tick_volume INTEGER,
            PRIMARY KEY (symbol, ts)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_m1_symbol_ts ON m1_bars(symbol, ts)")
    return conn


def default_db() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "mibgold.sqlite"


def data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def load_mt5_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    raw = path.read_bytes()[:200]
    text = raw.decode("utf-8", errors="ignore")
    sep = "\t" if "\t" in text else ("," if "," in text else None)
    df = pd.read_csv(path, sep=sep, engine="python")
    df.columns = [str(c).strip("<>").lower() for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        df["time"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), utc=True)
        if "tickvol" in df.columns:
            df = df.rename(columns={"tickvol": "tick_volume"})
    else:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    if "tick_volume" not in df.columns:
        df["tick_volume"] = df["volume"] if "volume" in df.columns else 0
    return (
        df[["time", "open", "high", "low", "close", "tick_volume"]]
        .dropna(subset=["time"])
        .sort_values("time")
        .drop_duplicates("time")
        .reset_index(drop=True)
    )


def upsert_m1(symbol: str, df: pd.DataFrame, db_path: Optional[Path] = None) -> int:
    if df is None or df.empty:
        return 0
    conn = _connect(db_path or default_db())
    rows = [
        (
            symbol,
            int(pd.Timestamp(t).timestamp()),
            float(o),
            float(h),
            float(l),
            float(c),
            int(v or 0),
        )
        for t, o, h, l, c, v in zip(
            df["time"], df["open"], df["high"], df["low"], df["close"], df["tick_volume"]
        )
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO m1_bars(symbol, ts, open, high, low, close, tick_volume) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def import_csv(path: str | Path, symbol: str, db_path: Optional[Path] = None) -> dict:
    df = load_mt5_csv(path)
    n = upsert_m1(symbol, df, db_path)
    return {
        "file": str(path),
        "symbol": symbol,
        "rows": n,
        "from": None if df.empty else str(df["time"].iloc[0]),
        "to": None if df.empty else str(df["time"].iloc[-1]),
        "db": str(db_path or default_db()),
    }


def ingest_folder(folder: Optional[Path] = None, symbol: str = "GOLD#") -> list:
    folder = Path(folder) if folder else data_dir()
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(list(folder.glob("*.csv")) + list(folder.glob("*.tsv")) + list(folder.glob("*.txt"))):
        name = p.name.upper()
        if name in {"LIVE_WEIGHTS.JSON", "MANUAL_EVENTS.JSON", "FF_CALENDAR_CACHE.JSON"}:
            continue
        try:
            out.append(import_csv(p, symbol))
        except Exception as e:
            out.append({"file": str(p), "error": str(e)})
    return out


def load_m1(symbol: str, bars: int = 200000, db_path: Optional[Path] = None) -> pd.DataFrame:
    conn = _connect(db_path or default_db())
    cur = conn.execute(
        "SELECT ts, open, high, low, close, tick_volume FROM m1_bars WHERE symbol=? ORDER BY ts DESC LIMIT ?",
        (symbol, int(bars)),
    )
    rows = cur.fetchall()
    if not rows:
        cur = conn.execute(
            "SELECT ts, open, high, low, close, tick_volume FROM m1_bars ORDER BY ts DESC LIMIT ?",
            (int(bars),),
        )
        rows = cur.fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "tick_volume"])
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df[["time", "open", "high", "low", "close", "tick_volume"]].sort_values("time").reset_index(drop=True)


def merge_live(cached: pd.DataFrame, live: pd.DataFrame) -> pd.DataFrame:
    parts = [x for x in (cached, live) if x is not None and not x.empty]
    if not parts:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])
    out = pd.concat(parts, ignore_index=True)
    out["time"] = pd.to_datetime(out["time"], utc=True)
    return out.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def stats(symbol: Optional[str] = None, db_path: Optional[Path] = None) -> dict:
    conn = _connect(db_path or default_db())
    if symbol:
        row = conn.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts) FROM m1_bars WHERE symbol=?",
            (symbol,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM m1_bars").fetchone()
    conn.close()
    n, a, b = row
    return {
        "symbol": symbol,
        "rows": int(n or 0),
        "from": None if not a else str(pd.to_datetime(a, unit="s", utc=True)),
        "to": None if not b else str(pd.to_datetime(b, unit="s", utc=True)),
    }


if __name__ == "__main__":
    import argparse
    import os

    p = argparse.ArgumentParser(description="Import MT5 M1 CSV into local sqlite cache")
    p.add_argument("csv", nargs="?")
    p.add_argument("--symbol", default=os.environ.get("MT5_SYMBOL", "GOLD#"))
    p.add_argument("--folder", action="store_true")
    args = p.parse_args()
    if args.folder or not args.csv:
        print(ingest_folder(symbol=args.symbol))
    else:
        print(import_csv(args.csv, args.symbol))
    print(stats(args.symbol))
