import math
from typing import Tuple

from app.services.live_trading.order_normalizer import MarketPreNormalizer


class USStockPreNormalizer(MarketPreNormalizer):

    def pre_normalize(self, raw_qty: float, symbol: str) -> int:
        return math.floor(raw_qty)

    def pre_check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        if qty != int(qty):
            return False, f"Quantity must be a whole number, got {qty}"
        return True, ""
