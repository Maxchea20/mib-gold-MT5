"""Shared backtest launch so /api/backtest/run honors book=."""
from datetime import timedelta
from .window import slice_for_test
from .harness import Backtest


def launch(req, m1, spec, gate):
    if m1 is None or getattr(m1, "empty", False):
        raise ValueError("no data")
    m1, cutoff, warm = slice_for_test(m1, int(getattr(req, "days", 30) or 30))
    book = getattr(req, "book", None) or "scalp_v1"
    bt = Backtest(
        m1, spec,
        float(getattr(req, "start_balance", 100) or 100),
        int(getattr(req, "max_layers", 1) or 1),
        float(getattr(req, "budget_pct", 0.1) or 0.1),
        float(getattr(req, "slippage_points", 5) or 5),
        warmup_bars=warm,
        news_gate=gate if getattr(req, "use_news_gate", True) else None,
        weights=getattr(req, "weights", None),
        bias_min_score=getattr(req, "bias_min_score", None),
        struct_oppose_score=getattr(req, "struct_oppose_score", None),
        session_thresholds=getattr(req, "session_thresholds", None),
        session_min_aligned=getattr(req, "session_min_aligned", None),
        min_risk_usd=float(getattr(req, "min_risk_usd", 1) or 1),
        max_risk_usd=float(getattr(req, "max_risk_usd", 100) or 100),
        fixed_lots=getattr(req, "fixed_lots", None),
        sl_dollars=getattr(req, "sl_dollars", None),
        tp_dollars=getattr(req, "tp_dollars", None),
        test_cutoff=cutoff,
        book=book,
    )
    return bt
