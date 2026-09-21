class StructuralOnly:
    def update(self, layer, price, atr):
        return None

    def check_exit(self, layer, high, low):
        tp = getattr(layer, "tp", None)
        if tp:
            if layer.sign > 0 and high >= tp:
                return ("STRUCTURE_TP", tp)
            if layer.sign < 0 and low <= tp:
                return ("STRUCTURE_TP", tp)
        if layer.sign > 0 and low <= layer.sl:
            return ("STRUCTURAL_SL", layer.sl)
        if layer.sign < 0 and high >= layer.sl:
            return ("STRUCTURAL_SL", layer.sl)
        return None
