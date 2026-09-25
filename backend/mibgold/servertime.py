"""Broker server time <-> UTC.

Most gold CFD brokers run server time on New York close: UTC+3 while the US is on
summer time, UTC+2 otherwise (week opens Mon 01:00 server = Sun 22:00/23:00 UTC).
MT5_SERVER_UTC_OFFSET_HOURS pins a fixed offset instead (for brokers on another clock).
No pandas here so plain-Python tools can use it.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

HOUR = 3600


def fixed_offset_hours() -> Optional[float]:
    raw = (os.environ.get("MT5_SERVER_UTC_OFFSET_HOURS") or "").strip()
    return float(raw) if raw else None


def _nth_sunday(year: int, month: int, n: int) -> datetime:
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def us_dst(utc: datetime) -> bool:
    """US summer time: 2nd Sunday of March 07:00 UTC to 1st Sunday of November 06:00 UTC."""
    y = utc.year
    start = _nth_sunday(y, 3, 2) + timedelta(hours=7)
    end = _nth_sunday(y, 11, 1) + timedelta(hours=6)
    return start <= utc < end


def ny_close_offset_hours(utc: datetime) -> int:
    return 3 if us_dst(utc) else 2


def offset_hours(utc: datetime) -> float:
    fixed = fixed_offset_hours()
    return fixed if fixed is not None else ny_close_offset_hours(utc)


def server_to_utc_ts(server_ts: int) -> int:
    """Server-clock epoch seconds (server wall time read as UTC) -> true UTC epoch seconds."""
    guess = datetime.fromtimestamp(server_ts - 3 * HOUR, tz=timezone.utc)
    return int(server_ts - offset_hours(guess) * HOUR)


def detect_offset_hours(server_ts: float, utc_now_ts: float, tolerance_s: float = 120) -> Optional[int]:
    """Offset from a fresh broker tick. None if the tick is stale (market closed)."""
    diff = server_ts - utc_now_ts
    hours = round(diff / HOUR)
    return hours if abs(diff - hours * HOUR) <= tolerance_s else None


def series_server_to_utc(t):
    """pandas Series of server wall times (tz-aware, read as UTC) -> true UTC. Offset looked up per day."""
    import pandas as pd
    days = t.dt.floor("D")
    off = {d: offset_hours(d.to_pydatetime()) for d in days.unique()}
    return t - pd.to_timedelta(days.map(off), unit="h")
