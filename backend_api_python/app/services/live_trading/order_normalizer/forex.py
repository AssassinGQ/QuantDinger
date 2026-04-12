from typing import Tuple

from app.services.live_trading.order_normalizer import MarketPreNormalizer


class ForexPreNormalizer(MarketPreNormalizer):

    def pre_normalize(self, raw_qty: float, symbol: str) -> float:
        return raw_qty

    def pre_check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        return True, ""
