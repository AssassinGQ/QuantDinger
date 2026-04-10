"""
Base classes for live trading.

Hierarchy
---------
- BaseRestfulClient   — stateless HTTP REST clients (crypto exchanges)
- BaseStatefulClient   — stateful TCP/IPC clients (IBKR, MT5)

Data classes
------------
- LiveOrderResult   — unified order result returned by all clients
- PositionRecord    — normalized position snapshot
- OrderContext      — order parameters passed from worker to runner
- ExecutionResult   — unified execution result returned by runner to worker
- LiveTradingError  — base exception
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import requests


# ── data classes ─────────────────────────────────────────────────────

@dataclass
class LiveOrderResult:
    success: bool = True
    exchange_id: str = ""
    exchange_order_id: str = ""
    filled: float = 0.0
    avg_price: float = 0.0
    status: str = ""
    message: str = ""
    order_id: int = 0
    deal_id: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)
    fee: float = 0.0
    fee_ccy: str = ""


@dataclass
class PositionRecord:
    symbol: str
    side: str           # "long" or "short"
    quantity: float     # always positive
    entry_price: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderContext:
    order_id: int
    strategy_id: int
    symbol: str
    signal_type: str
    amount: float
    market_type: str
    market_category: str
    exchange_config: Dict[str, Any]
    payload: Dict[str, Any]
    order_row: Dict[str, Any]
    notification_config: Dict[str, Any] = field(default_factory=dict)
    strategy_name: str = ""
    direction: str = "long"
    price: float = 0.0


@dataclass
class ExecutionResult:
    success: bool
    exchange_id: str = ""
    exchange_order_id: str = ""
    filled: float = 0.0
    avg_price: float = 0.0
    fee: float = 0.0
    fee_ccy: str = ""
    error: str = ""
    note: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class LiveTradingError(Exception):
    pass


# ── BaseRestfulClient (stateless HTTP) ──────────────────────────────

class BaseRestfulClient:
    def __init__(self, base_url: str, timeout_sec: float = 15.0):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout_sec = float(timeout_sec)

    def _url(self, path: str) -> str:
        p = str(path or "")
        if not p.startswith("/"):
            p = "/" + p
        return f"{self.base_url}{p}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
    ) -> Tuple[int, Dict[str, Any], str]:
        url = self._url(path)
        resp = requests.request(
            method=str(method or "GET").upper(),
            url=url,
            params=params or None,
            json=json_body if json_body is not None else None,
            data=data,
            headers=headers or None,
            timeout=self.timeout_sec,
        )
        text = resp.text or ""
        parsed: Dict[str, Any] = {}
        try:
            parsed = resp.json() if text else {}
        except Exception:
            parsed = {"raw_text": text[:2000]}
        return int(resp.status_code), parsed, text

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _json_dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ── BaseStatefulClient (TCP/IPC, e.g. IBKR, MT5) ────────────────────

class BaseStatefulClient(ABC):
    engine_id: str = ""
    supported_market_categories: FrozenSet[str] = frozenset()

    def validate_market_category(self, market_category: str) -> Tuple[bool, str]:
        if not self.supported_market_categories:
            return True, ""
        if market_category in self.supported_market_categories:
            return True, ""
        return False, (
            f"{self.engine_id} only supports "
            f"{', '.join(sorted(self.supported_market_categories))}, "
            f"got {market_category}"
        )

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Return True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully disconnect."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the client is currently connected."""

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "",
        **kwargs,
    ) -> LiveOrderResult:
        ...

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "",
        **kwargs,
    ) -> LiveOrderResult:
        return LiveOrderResult(
            success=False,
            message=f"{self.engine_id} does not support limit orders",
        )

    def cancel_order(self, order_id: int) -> bool:
        return False

    @abstractmethod
    def map_signal_to_side(self, signal_type: str, *, market_category: str = "") -> str:
        """Convert strategy signal (e.g. 'open_long') to 'buy'/'sell'."""

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_positions_normalized(self) -> List[PositionRecord]:
        return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        return []

    def get_account_summary(self) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    def get_connection_status(self) -> Dict[str, Any]:
        return {"connected": self.connected, "engine_id": self.engine_id}

    def is_market_open(self, symbol: str, market_type: str = "") -> Tuple[bool, str]:
        """Check whether the market is open for *symbol*.

        Returns (True, "") if open, or (False, reason) if closed.
        Default implementation: always open (subclass may override).
        """
        return True, ""

    def shutdown(self) -> None:
        self.disconnect()


# backward compat alias
BaseRestClient = BaseRestfulClient
