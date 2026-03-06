import math
from typing import Tuple

from app.services.live_trading.order_normalizer import OrderNormalizer


class ForexNormalizer(OrderNormalizer):

    def normalize(self, raw_qty: float, symbol: str) -> int:
        return math.floor(raw_qty)

    def check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        return True, ""
