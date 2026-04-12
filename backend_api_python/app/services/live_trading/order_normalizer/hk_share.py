from typing import Tuple

from app.services.live_trading.order_normalizer import MarketPreNormalizer


_DEFAULT_HK_LOT = 100

HK_LOT_SIZES = {
    # ── 金融 ──
    "5": 400,        # 汇丰控股
    "11": 1000,      # 恒生银行
    "388": 100,      # 香港交易所
    "939": 1000,     # 建设银行
    "1398": 1000,    # 工商银行
    "3988": 1000,    # 中国银行
    "2318": 200,     # 中国平安
    "1299": 200,     # 友邦保险
    # ── 科技 / 互联网 ──
    "700": 100,      # 腾讯控股
    "9988": 100,     # 阿里巴巴
    "3690": 100,     # 美团
    "9618": 50,      # 京东集团
    "9999": 100,     # 网易
    "1810": 200,     # 小米集团
    "9888": 100,     # 百度集团
    "9961": 100,     # 携程集团
    "1024": 100,     # 快手
    "2015": 200,     # 理想汽车
    "9866": 200,     # 蔚来
    "9868": 100,     # 小鹏汽车
    # ── 消费 / 医药 / 制造 ──
    "1211": 500,     # 比亚迪
    "2331": 500,     # 李宁
    "9633": 500,     # 农夫山泉
    "6098": 200,     # 碧桂园服务
    "1177": 1000,    # 中国生物制药
    "2269": 200,     # 药明生物
    "175": 1000,     # 吉利汽车
    # ── 电信 / 能源 / 公用 ──
    "941": 500,      # 中国移动
    "883": 1000,     # 中海油
    "2": 500,        # 中电控股
    "1038": 500,     # 长江基建
    "16": 500,       # 新鸿基地产
    "27": 1000,      # 银河娱乐
    "1928": 200,     # 金沙中国
    # ── ETF ──
    "2800": 500,     # 盈富基金
    "2823": 100,     # 安硕A50
    "3032": 100,     # 恒生科技ETF
    "3033": 100,     # 南方恒生科技ETF
}


def _hk_symbol_key(symbol: str) -> str:
    """Normalize HK symbol to lookup key (strip leading zeros and .HK suffix)."""
    s = (symbol or "").strip().upper()
    if s.endswith(".HK"):
        s = s[:-3]
    return s.lstrip("0") or "0"


class HSharePreNormalizer(MarketPreNormalizer):

    def _lot_size(self, symbol: str) -> int:
        return HK_LOT_SIZES.get(_hk_symbol_key(symbol), _DEFAULT_HK_LOT)

    def pre_normalize(self, raw_qty: float, symbol: str) -> float:
        lot = self._lot_size(symbol)
        if lot <= 1:
            return float(raw_qty)
        snapped = int(raw_qty // lot) * lot
        # Keep sub-lot positive quantities so pre_check can emit board-lot messaging (e.g. 400).
        if raw_qty > 0 and snapped == 0:
            return float(int(raw_qty))
        return float(snapped)

    def pre_check(self, qty: float, symbol: str) -> Tuple[bool, str]:
        if qty <= 0:
            return False, f"Quantity must be positive, got {qty}"
        if qty != int(qty):
            return False, f"Quantity must be a whole number, got {qty}"
        lot = self._lot_size(symbol)
        if lot > 1 and qty % lot != 0:
            return False, f"HK stock {symbol} requires multiples of {lot} shares, got {qty}"
        return True, ""
