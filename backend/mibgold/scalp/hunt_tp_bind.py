"""Attach last Hunt TP onto PositionBook.open_layer."""
LAST_TP = None


def bind():
    from ..book import PositionBook
    if getattr(PositionBook.open_layer, "_hunt_bound", False):
        return
    orig = PositionBook.open_layer

    def wrapped(self, direction, entry, sl, lots, risk_usd, ts, votes, consensus, summary, session, bias, ticket=None, tp=None):
        global LAST_TP
        if tp is None:
            tp = LAST_TP
        return orig(self, direction, entry, sl, lots, risk_usd, ts, votes, consensus, summary, session, bias, ticket, tp)

    wrapped._hunt_bound = True
    PositionBook.open_layer = wrapped
