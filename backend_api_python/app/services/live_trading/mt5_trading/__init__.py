"""
MetaTrader 5 Trading Module

Provides forex trading capabilities via MT5 terminal.
Requires Windows platform and MetaTrader5 Python library.
"""

from app.services.live_trading.mt5_trading.client import MT5Client, MT5Config
from app.services.live_trading.mt5_trading.symbols import normalize_symbol, parse_symbol
from app.services.live_trading.base import LiveOrderResult

__all__ = [
    "MT5Client",
    "MT5Config",
    "LiveOrderResult",
    "normalize_symbol",
    "parse_symbol",
]
