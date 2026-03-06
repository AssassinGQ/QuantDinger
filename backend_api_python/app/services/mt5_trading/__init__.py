"""
MetaTrader 5 Trading Module

Provides forex trading capabilities via MT5 terminal.
Requires Windows platform and MetaTrader5 Python library.
"""

from app.services.mt5_trading.client import MT5Client, MT5Config
from app.services.mt5_trading.symbols import normalize_symbol, parse_symbol
from app.services.exchange_engine import OrderResult

__all__ = [
    "MT5Client",
    "MT5Config",
    "OrderResult",
    "normalize_symbol",
    "parse_symbol",
]
