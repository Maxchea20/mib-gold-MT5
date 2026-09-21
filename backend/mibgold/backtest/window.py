"""Test-window helpers. No strategy logic."""
from datetime import timedelta


def slice_for_test(m1, days: int, pad_days: int = 60):
    cutoff = m1["time"].iloc[-1] - timedelta(days=int(days))
    loaded = m1[m1["time"] >= cutoff - timedelta(days=pad_days)].reset_index(drop=True)
    warm_idx = int(loaded["time"].searchsorted(cutoff))
    return loaded, cutoff, max(400, warm_idx)
