from datetime import datetime, timezone

# UTC-based session map for XAUUSD liquidity regimes
SESSIONS = [
    (0, 7, "asian"), (7, 12, "london"), (12, 16, "ny_overlap"), (16, 21, "ny"), (21, 24, "off"),
]
SESSION_LABEL = {"asian": "Asian", "london": "London", "ny_overlap": "NY Overlap", "ny": "New York", "off": "Off-hours"}

# Consensus score needed before an entry is allowed to fire, per session
SESSION_THRESHOLD = {"asian": 0.34, "london": 0.26, "ny_overlap": 0.24, "ny": 0.28, "off": 0.42}
# Minimum non-neutral aligned engines per session
SESSION_MIN_ALIGNED = {"asian": 5, "london": 4, "ny_overlap": 4, "ny": 4, "off": 6}


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
