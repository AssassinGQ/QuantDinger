"""
Exchange Engine Adapter Layer

Defines the abstract base class (`ExchangeEngine`) and unified `OrderResult`
that all trading engine implementations must conform to.

The `pending_order_worker` depends only on these abstractions, never on
concrete engine classes. Each engine (IBKR, MT5, future engines) implements
`ExchangeEngine` and is responsible for returning accurate `OrderResult`
values — the worker layer trusts them without fabricating fills.
"""

from app.services.exchange_engine.base import ExchangeEngine, OrderResult, PositionRecord

__all__ = ["ExchangeEngine", "OrderResult", "PositionRecord"]
