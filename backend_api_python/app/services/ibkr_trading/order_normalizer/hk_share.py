"""Backward-compatible re-export."""
from app.services.exchange_engine.order_normalizer.hk_share import (  # noqa: F401
    HShareNormalizer,
    HK_LOT_SIZES,
    _hk_symbol_key,
)
