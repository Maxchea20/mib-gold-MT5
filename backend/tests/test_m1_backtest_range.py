import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

if not mt5.initialize():
    print("initialize failed:", mt5.last_error())
    exit()

symbol = "GOLD#"
mt5.symbol_select(symbol, True)

end = datetime.now(timezone.utc)
for days in (10, 30, 50, 70, 90):
    start = end - timedelta(days=days)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start, end)
    if rates is None:
        print(f"days={days:>3}: FAILED  ({mt5.last_error()})")
    else:
        print(f"days={days:>3}: OK  got {len(rates):>6} bars")

mt5.shutdown()