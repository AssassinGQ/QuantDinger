"""
Interactive Brokers (IBKR) Trading Module

Supports US stocks and Hong Kong stocks trading via TWS or IB Gateway.

Port Reference:
- TWS Live: 7497, TWS Paper: 7496
- IB Gateway Live: 4001, IB Gateway Paper: 4002
"""

from app.services.ibkr_trading.client import IBKRClient, IBKRConfig
from app.services.ibkr_trading.symbols import normalize_symbol, parse_symbol
from app.services.exchange_engine import OrderResult

__all__ = ['IBKRClient', 'IBKRConfig', 'OrderResult', 'normalize_symbol', 'parse_symbol']
