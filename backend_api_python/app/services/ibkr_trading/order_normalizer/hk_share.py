from typing import Tuple

from app.services.ibkr_trading.order_normalizer import OrderNormalizer


HK_LOT_SIZES = {
    "5": 400,       # 汇丰控股
    "9618": 50,     # 京东集团
    "1211": 100,    # 比亚迪
}


def _hk_symbol_key(symbol: str) -> str:
    """Normalize HK symbol to lookup key (strip leading zeros and .HK suffix)."""
    s = (symbol or "").strip().upper()
    if s.endswith(".HK"):
        s = s[:-3]
    return s.lstrip("0") or "0"


class HShareNormalizer(OrderNormalizer):

    def _lot_size(self, symbol: str) -> int:
        return HK_LOT_SIZES.get(_hk_symbol_key(symbol), 1)

    def normalize(self, raw_qty: float, symbol: str) -> int:
        lot = self._lot_size(symbol)
        return int(raw_qty // lot) * lot

    def check(self, qty: int, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        if qty != int(qty):
            return False, f"Quantity must be a whole number, got {qty}"
        lot = self._lot_size(symbol)
        if lot > 1 and qty % lot != 0:
            return False, f"HK stock {symbol} requires multiples of {lot} shares, got {qty}"
        return True, ""
