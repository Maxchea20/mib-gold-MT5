"""Local SQLite store. Replaces Mongo so the desktop app has no extra server."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_db_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data / "mibgold.sqlite"


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    direction TEXT,
                    session TEXT,
                    outcome TEXT,
                    mode TEXT,
                    backtest_id TEXT,
                    exit_time TEXT,
                    timestamp TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS backtests (
                    id TEXT PRIMARY KEY,
                    created TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_bt ON trades(backtest_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_exit ON trades(exit_time)")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert_trade(self, rec: Dict[str, Any]) -> None:
        payload = json.dumps(rec, default=str)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO trades (id, status, direction, session, outcome, mode, backtest_id, exit_time, timestamp, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    direction=excluded.direction,
                    session=excluded.session,
                    outcome=excluded.outcome,
                    mode=excluded.mode,
                    backtest_id=excluded.backtest_id,
                    exit_time=excluded.exit_time,
                    timestamp=excluded.timestamp,
                    payload=excluded.payload
                """,
                (
                    rec.get("id"),
                    rec.get("status"),
                    rec.get("direction"),
                    rec.get("session"),
                    rec.get("outcome"),
                    rec.get("mode"),
                    rec.get("backtest_id"),
                    str(rec.get("exit_time") or ""),
                    str(rec.get("timestamp") or rec.get("exit_time") or ""),
                    payload,
                ),
            )
            self._conn.commit()

    def upsert_backtest(self, rec: Dict[str, Any]) -> None:
        payload = json.dumps(rec, default=str)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO backtests (id, created, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    created=excluded.created,
                    payload=excluded.payload
                """,
                (rec.get("id"), str(rec.get("created") or ""), payload),
            )
            self._conn.commit()

    def get_backtest(self, bt_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM backtests WHERE id=?", (bt_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_backtests(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM backtests ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            doc = json.loads(row["payload"])
            doc.pop("equity_curve", None)
            doc.pop("attribution", None)
            out.append(doc)
        return out

    def list_trades(
        self,
        *,
        status: Optional[str] = "closed",
        direction: Optional[str] = None,
        session: Optional[str] = None,
        outcome: Optional[str] = None,
        mode: Optional[str] = None,
        backtest_id: Optional[str] = None,
        engine: Optional[str] = None,
        limit: int = 200,
        order: str = "exit_time",
        descending: bool = True,
    ) -> List[Dict[str, Any]]:
        where = ["1=1"]
        args: List[Any] = []
        if status:
            where.append("status=?")
            args.append(status)
        if direction:
            where.append("direction=?")
            args.append(direction)
        if session:
            where.append("session=?")
            args.append(session)
        if outcome:
            where.append("outcome=?")
            args.append(outcome)
        if mode:
            where.append("mode=?")
            args.append(mode)
        if backtest_id:
            where.append("backtest_id=?")
            args.append(backtest_id)
        col = "exit_time" if order == "exit_time" else "timestamp"
        direction_sql = "DESC" if descending else "ASC"
        sql = f"SELECT payload FROM trades WHERE {' AND '.join(where)} ORDER BY {col} {direction_sql} LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        docs = [json.loads(r["payload"]) for r in rows]
        if engine:
            filtered = []
            for d in docs:
                vote = (d.get("agent_votes") or {}).get(engine) or {}
                if vote.get("signal") in ("long", "short") and vote.get("signal") == d.get("direction"):
                    filtered.append(d)
            return filtered
        return docs
