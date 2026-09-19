from datetime import datetime, timezone

# UTC-based session map for XAUUSD liquidity regimes
SESSIONS = [
    (0, 7, "asian"), (7, 12, "london"), (12, 16, "ny_overlap"), (16, 21, "ny"), (21, 24, "off"),
]
SESSION_LABEL = {"asian": "Asian", "london": "London", "ny_overlap": "NY Overlap", "ny": "New York", "off": "Off-hours"}

# Display-only. Fire no longer requires these (see Consensus.evaluate).
SESSION_THRESHOLD = {"asian": 0.0, "london": 0.0, "ny_overlap": 0.0, "ny": 0.0, "off": 0.0}
SESSION_MIN_ALIGNED = {"asian": 0, "london": 0, "ny_overlap": 0, "ny": 0, "off": 0}


def session_for(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hour = ts.astimezone(timezone.utc).hour
    if ts.weekday() >= 5:
        return "off"
    for start, end, name in SESSIONS:
        if start <= hour < end:
            return name
    return "off"
