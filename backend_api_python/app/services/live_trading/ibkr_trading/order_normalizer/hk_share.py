"""Backward-compatible re-export."""
from app.services.live_trading.order_normalizer.hk_share import (  # noqa: F401
    HSharePreNormalizer,
    HK_LOT_SIZES,
    _hk_symbol_key,
)
