"""Secondary, non-blocking AI interpretive layer. Runs 45-60s after a release, sets an advisory flag only."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from .calendar import NewsGate, NewsEvent

log = logging.getLogger("mibgold.news.ai")
SYSTEM = ("You are a macro desk analyst for XAUUSD (gold). Given a high-impact release with actual vs forecast vs previous, "
          "return ONLY compact JSON: {\"bias\": \"long\"|\"short\"|\"neutral\", \"strength\": 0-1, \"note\": \"one sentence\"}. "
          "Hotter-than-expected US inflation/jobs = stronger USD/higher yields = bearish gold; misses = bullish gold.")


class NewsInterpreter:
    def __init__(self, gate: NewsGate, delay_s: int = 45, ttl_min: int = 90):
        self.gate, self.delay_s, self.ttl = gate, delay_s, timedelta(minutes=ttl_min)
        self.advisory: Optional[dict] = None
        self.history: list = []
        self._done: set = set()
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.enabled = bool(self.api_key)

    def current(self, now: datetime) -> Optional[dict]:
        if self.advisory and datetime.fromisoformat(self.advisory["expires"]) > now:
            return self.advisory
        return None

    async def poll(self, now: datetime) -> None:
        """Called from the loop; spawns background interpretation tasks, never awaits the LLM inline."""
        if not self.enabled:
            return
        for ev in self.gate.recently_released(now, self.delay_s, 900):
            if ev.key in self._done:
                continue
            self._done.add(ev.key)
            asyncio.create_task(self._interpret(ev, now))

    async def interpret_now(self, ev: NewsEvent, now: Optional[datetime] = None) -> dict:
        return await self._interpret(ev, now or datetime.now(timezone.utc), force=True)

    async def _interpret(self, ev: NewsEvent, now: datetime, force: bool = False) -> dict:
        import anthropic
        if not ev.actual and not force:
            self._done.discard(ev.key)  # actual not printed yet; retry on next poll
            return {}
        prompt = (f"Event: {ev.title} ({ev.country}) at {ev.time.isoformat()}\nActual: {ev.actual or 'n/a'}\n"
                  f"Forecast: {ev.forecast or 'n/a'}\nPrevious: {ev.previous or 'n/a'}\nGive the gold bias for the next 1-4 hours.")
        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0)) if m else {"bias": "neutral", "strength": 0, "note": text[:200]}
        except Exception as e:
            log.warning("news AI failed: %s", e)
            data = {"bias": "neutral", "strength": 0, "note": f"AI unavailable: {type(e).__name__}"}
        adv = {"event": ev.to_dict(), "bias": data.get("bias", "neutral"), "strength": float(data.get("strength", 0) or 0),
               "note": data.get("note", ""), "created": now.isoformat(), "expires": (now + self.ttl).isoformat(), "model": "claude-sonnet-4-6"}
        self.advisory = adv
        self.history.append(adv)
        return adv