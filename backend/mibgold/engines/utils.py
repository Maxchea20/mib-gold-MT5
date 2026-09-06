import numpy as np
import pandas as pd


def ema(a, n):
    return pd.Series(a).ewm(span=n, adjust=False).mean().to_numpy()


def sma(a, n):
    return pd.Series(a).rolling(n).mean().to_numpy()


def atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ru = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    rd = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    rs = ru / np.where(rd == 0, 1e-9, rd)
    return 100 - 100 / (1 + rs)


def pivots(df: pd.DataFrame, k: int = 3):
    """Return list of (index, price, 'H'|'L') confirmed swing points."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(h)
    out = []
    for i in range(k, n - k):
        win_h = h[i - k:i + k + 1]
        win_l = l[i - k:i + k + 1]
        if h[i] >= win_h.max():
            out.append((i, float(h[i]), "H"))
        if l[i] <= win_l.min():
            out.append((i, float(l[i]), "L"))
    return out


def zigzag(df: pd.DataFrame, k: int = 3):
    """Alternating swing points: consecutive same-type pivots collapse to the extreme."""
    zz = []
    for idx, price, kind in pivots(df, k):
        if zz and zz[-1][2] == kind:
            if (kind == "H" and price > zz[-1][1]) or (kind == "L" and price < zz[-1][1]):
                zz[-1] = (idx, price, kind)
        else:
            zz.append((idx, price, kind))
    return zz


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(min(max(x, lo), hi))


def safe_atr(df: pd.DataFrame) -> float:
    a = atr(df)
    v = float(a[-1]) if len(a) else 0.0
    return v if v > 0 else max(float(df["close"].iloc[-1]) * 0.0005, 0.01)
