"""Hard mechanical news gate: pure timestamp/rule logic. Zero API/LLM calls on the hot path."""
from __future__ import annotations
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
import requests

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_FILE = DATA_DIR / "ff_calendar_cache.json"
MANUAL_FILE = DATA_DIR / "manual_events.json"
HIGH_IMPACT_KEYWORDS = ("non-farm", "nonfarm", "cpi", "fomc", "federal funds", "pce", "gdp", "unemployment", "ppi", "retail sales", "powell", "ism")


class NewsEvent:
    def __init__(self, title: str, country: str, time: datetime, impact: str, forecast="", previous="", actual="", source="ff"):
        self.title, self.country, self.time, self.impact = title, country, time, impact
        self.forecast, self.previous, self.actual, self.source = forecast, previous, actual, source

    @property
    def key(self):
        return f"{self.time.isoformat()}|{self.title}"

    def to_dict(self):
        return {"title": self.title, "country": self.country, "time": self.time.isoformat(), "impact": self.impact,
                "forecast": self.forecast, "previous": self.previous, "actual": self.actual, "source": self.source}


class NewsGate:
    def __init__(self, before_min: int = 30, after_min: int = 30, currencies=("USD",)):
        self.before = timedelta(minutes=before_min)
        self.after = timedelta(minutes=after_min)
        self.currencies = set(currencies)
        self.events: List[NewsEvent] = []
        self.last_fetch: Optional[datetime] = None
        self.fetch_error: Optional[str] = None
        self._lock = threading.Lock()
        DATA_DIR.mkdir(exist_ok=True)
        self._load_cache()
        self._load_manual()

    # ---- loading (off hot path; called from a background thread) ----
    def refresh(self) -> None:
        try:
            r = requests.get(FF_URL, timeout=10, headers={"User-Agent": "mib-gold/1.0"})
            r.raise_for_status()
            CACHE_FILE.write_text(r.text)
            self._ingest_ff(r.json())
            self.fetch_error = None
        except Exception as e:  # keep serving cached/manual events
            self.fetch_error = str(e)
        self.last_fetch = datetime.now(timezone.utc)
        self._load_manual()

    def _load_cache(self):
        if CACHE_FILE.exists():
            try:
                self._ingest_ff(json.loads(CACHE_FILE.read_text()))
            except Exception:
                pass

    def _ingest_ff(self, items):
        evs = []
        for it in items:
            if it.get("impact") != "High" or it.get("country") not in self.currencies:
                continue
            try:
                t = datetime.fromisoformat(it["date"]).astimezone(timezone.utc)
            except Exception:
                continue
            evs.append(NewsEvent(it.get("title", ""), it["country"], t, "High", it.get("forecast", ""), it.get("previous", ""), it.get("actual", ""), "ff"))
        with self._lock:
            self.events = [e for e in self.events if e.source != "ff"] + evs

    def _load_manual(self):
        if not MANUAL_FILE.exists():
            MANUAL_FILE.write_text(json.dumps([{"title": "Example: US CPI m/m", "country": "USD", "time": "2026-01-01T13:30:00+00:00",
                                                 "impact": "High", "forecast": "0.3%", "previous": "0.2%", "enabled": False}], indent=2))
        try:
            items = json.loads(MANUAL_FILE.read_text())
        except Exception:
            return
        evs = []
        for it in items:
            if not it.get("enabled", True):
                continue
            try:
                t = datetime.fromisoformat(it["time"]).astimezone(timezone.utc)
            except Exception:
                continue
            evs.append(NewsEvent(it.get("title", "manual"), it.get("country", "USD"), t, it.get("impact", "High"),
                                 it.get("forecast", ""), it.get("previous", ""), it.get("actual", ""), "manual"))
        with self._lock:
            self.events = [e for e in self.events if e.source != "manual"] + evs

    def add_manual(self, ev: dict) -> None:
        items = json.loads(MANUAL_FILE.read_text()) if MANUAL_FILE.exists() else []
        items.append(ev)
        MANUAL_FILE.write_text(json.dumps(items, indent=2))
        self._load_manual()

    def add_runtime_events(self, evs: List[NewsEvent]) -> None:
        with self._lock:
            self.events = [e for e in self.events if e.source != "sim"] + evs

    # ---- hot path: pure comparisons ----
    def check(self, now: datetime) -> dict:
        with self._lock:
            evs = list(self.events)
        blocking = None
        for e in evs:
            if e.time - self.before <= now <= e.time + self.after:
                if blocking is None or abs((e.time - now).total_seconds()) < abs((blocking.time - now).total_seconds()):
                    blocking = e
        upcoming = sorted((e for e in evs if e.time > now), key=lambda e: e.time)[:5]
        res = {"blocked": blocking is not None, "window_before_min": int(self.before.total_seconds() // 60),
               "window_after_min": int(self.after.total_seconds() // 60), "upcoming": [e.to_dict() for e in upcoming],
               "events_loaded": len(evs), "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
               "fetch_error": self.fetch_error}
        if blocking:
            secs = (blocking.time - now).total_seconds()
            res.update(event=blocking.to_dict(), seconds_to_event=int(secs),
                       seconds_until_clear=int((blocking.time + self.after - now).total_seconds()),
                       phase="pre" if secs > 0 else "post")
        return res

    def recently_released(self, now: datetime, min_age_s: int = 45, max_age_s: int = 900) -> List[NewsEvent]:
        with self._lock:
            return [e for e in self.events if min_age_s <= (now - e.time).total_seconds() <= max_age_s]


def start_refresher(gate: NewsGate, interval_s: int = 1800):
    def loop():
        while True:
            gate.refresh()
            time.sleep(interval_s)
    threading.Thread(target=loop, daemon=True, name="news-refresh").start()
