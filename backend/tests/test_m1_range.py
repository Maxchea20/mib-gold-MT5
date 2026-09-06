import MetaTrader5 as mt5

if not mt5.initialize():
    print("initialize failed:", mt5.last_error())
    exit()

symbol = "GOLD#"
mt5.symbol_select(symbol, True)

for count in (500, 1000, 2000, 3000, 5000, 10000, 20000, 50000):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, count)
    if rates is None:
        print(f"count={count:>6}: FAILED  ({mt5.last_error()})")
    else:
        span_days = (rates[-1][0] - rates[0][0]) / 86400
        print(f"count={count:>6}: OK  got {len(rates):>6} bars  spanning {span_days:.1f} days  "
              f"(oldest={rates[0][0]})")

mt5.shutdown()