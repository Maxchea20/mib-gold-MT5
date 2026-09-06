import pandas as pd

RULES = {"M1": "1min", "M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h", "D1": "1D"}
COLS = ["time", "open", "high", "low", "close", "tick_volume"]


def resample(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """M1 -> higher timeframe in pandas so live and backtest bars are built identically."""
    if tf == "M1":
        return m1[COLS].reset_index(drop=True)
    df = m1[COLS].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index(pd.DatetimeIndex(df["time"]))
    agg = df.resample(RULES[tf], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"}).dropna()
    return agg.reset_index()[COLS]


def all_frames(m1: pd.DataFrame, tfs=("M5", "H1", "H4", "D1")) -> dict:
    out = {"M1": m1[COLS].reset_index(drop=True)}
    for tf in tfs:
        out[tf] = resample(m1, tf)
    return out


def completed_only(df: pd.DataFrame, tf: str, now: pd.Timestamp) -> pd.DataFrame:
    """Drop the in-progress bar so engines only see closed candles."""
    end = df["time"] + pd.Timedelta(RULES[tf])
    return df[end <= now]