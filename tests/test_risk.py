import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from datetime import datetime, timezone
from mibgold.risk import RiskManager, SymbolSpec
from mibgold.contracts import Layer, money_text
from mibgold.trailing import TrailingTP


def mk(direction, entry, sl, lots):
    return Layer(id="x", group_id="g", layer_number=1, direction=direction, entry=entry, sl=sl, initial_sl=sl,
                 lots=lots, risk_usd=abs(entry - sl) * lots * 100, open_time=datetime.now(timezone.utc), peak=entry)


def test_shared_budget_across_hedged_layers():
    rm = RiskManager(SymbolSpec(), budget_pct=0.10, max_layers=3)
    eq = 1000.0
    d1 = rm.size_new_layer(eq, 2000.0, 1990.0, [], "long")  # $10 SL -> 3.33% of 1000 = $33.3 -> 0.03 lots
    assert d1.allowed and d1.lots == 0.03
    l1 = mk("long", 2000.0, 1990.0, 0.03)
    l2 = mk("short", 2000.0, 2010.0, 0.03)  # hedged opposite leg counts against the SAME budget
    used = rm.used_risk_pct([l1, l2], eq)
    assert abs(used - 0.06) < 1e-9
    d3 = rm.size_new_layer(eq, 2000.0, 1990.0, [l1, l2], "long")
    assert d3.allowed and abs(d3.used_pct_after - 0.09) < 1e-9
    l3 = mk("long", 2000.0, 1990.0, 0.03)
    d4 = rm.size_new_layer(eq, 2000.0, 1990.0, [l1, l2, l3], "short")
    assert d4.allowed and d4.lots == 0.01  # only $10 of budget left -> 0.01 lot
    l4 = mk("short", 2000.0, 2010.0, 0.01)
    d5 = rm.size_new_layer(eq, 2000.0, 1990.0, [l1, l2, l3, l4], "short")
    assert not d5.allowed  # budget exhausted at exactly 10%


def test_small_account_rejects_wide_stop():
    rm = RiskManager(SymbolSpec(), budget_pct=0.10, max_layers=3)
    d = rm.size_new_layer(100.0, 2000.0, 1995.0, [], "long")  # min lot risks $5 > $3.33 allowed
    assert not d.allowed and "Min lot" in d.reason


def test_trailing_and_text():
    t = TrailingTP()
    l = mk("long", 2000.0, 1996.0, 0.01)
    t.update(l, 2004.5, atr=1.0)  # +1.125R -> trail arms, SL to breakeven
    assert l.trail_active and l.sl >= 2000.0
    t.update(l, 2010.0, atr=1.0)
    assert l.sl > 2000.0 and l.worst_case_loss(100) == 0.0
    assert t.check_exit(l, 2010.0, l.sl - 0.01)[0] == "TRAIL_TP"
    assert money_text(-3.2, closed=True) == "Lost $3.20" and money_text(1.5, closed=False) == "Floating +$1.50"
