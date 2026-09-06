import MetaTrader5 as mt5

if not mt5.initialize():
    print("initialize failed:", mt5.last_error())
    exit()

symbol = "GOLD#"
mt5.symbol_select(symbol, True)

rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 500)
print("--- count=500 ---")
print("rates is None:", rates is None)
print("count:", 0 if rates is None else len(rates))
if rates is not None and len(rates) > 0:
    print("first:", rates[0])
    print("last:", rates[-1])

print()
print("--- count=172800 (what the real app requests) ---")
rates2 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 172800)
print("rates is None:", rates2 is None)
print("count:", 0 if rates2 is None else len(rates2))
if rates2 is not None and len(rates2) > 0:
    print("first:", rates2[0])
    print("last:", rates2[-1])
print("last_error:", mt5.last_error())

mt5.shutdown()