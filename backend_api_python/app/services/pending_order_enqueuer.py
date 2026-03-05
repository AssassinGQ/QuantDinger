"""
Pending order enqueuer: 将信号转换为 pending 订单并写入 DB。

从 TradingExecutor 抽取，供 signal_executor 调用。
"""
import json
import time
from typing import Any, Callable, Dict, Optional

from app.services.price_fetcher import get_price_fetcher
from app.services.data_handler import DataHandler
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PendingOrderEnqueuer:
    """将交易信号入队为 pending 订单"""

    def __init__(self):
        self.data_handler = DataHandler()
        self._price_fetcher = get_price_fetcher()

    def enqueue_pending_order(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        amount: float,
        price: float,
        signal_ts: int,
        market_type: str,
        leverage: float,
        execution_mode: str,
        notification_config: Optional[Dict[str, Any]] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert a pending order record and return its id."""
        try:
            now = int(time.time())
            mode = (execution_mode or "signal").strip().lower()
            if mode not in ("signal", "live"):
                mode = "signal"

            payload: Dict[str, Any] = {
                "strategy_id": int(strategy_id),
                "symbol": symbol,
                "signal_type": signal_type,
                "market_type": market_type,
                "amount": float(amount or 0.0),
                "price": float(price or 0.0),
                "leverage": float(leverage or 1.0),
                "execution_mode": mode,
                "notification_config": notification_config or {},
                "signal_ts": int(signal_ts or 0),
            }
            if extra_payload and isinstance(extra_payload, dict):
                payload.update(extra_payload)

            stsig = int(signal_ts or 0)
            sig_norm = str(signal_type or "").strip().lower()
            strict_candle_dedup = stsig > 0 and sig_norm in (
                "open_long",
                "open_short",
                "close_long",
                "close_short",
            )

            last = self.data_handler.find_recent_pending_order(
                strategy_id, symbol, signal_type, stsig if strict_candle_dedup else None
            )
            last_id = int((last or {}).get("id") or 0)
            last_status = str((last or {}).get("status") or "").strip().lower()
            _raw_created = (last or {}).get("created_at")
            if hasattr(_raw_created, "timestamp"):
                last_created = int(_raw_created.timestamp())
            else:
                last_created = int(_raw_created or 0)
            cooldown_sec = 30

            if last_id > 0:
                if strict_candle_dedup and last_status not in ("failed",):
                    logger.info(
                        "enqueue_pending_order skipped (same candle): id=%s sid=%s sym=%s "
                        "sig=%s ts=%s status=%s",
                        last_id,
                        strategy_id,
                        symbol,
                        signal_type,
                        stsig,
                        last_status,
                    )
                    return None
                if last_status in ("pending", "processing"):
                    logger.info(
                        "enqueue_pending_order skipped: existing_inflight id=%s strategy_id=%s symbol=%s signal=%s status=%s",
                        last_id,
                        strategy_id,
                        symbol,
                        signal_type,
                        last_status,
                    )
                    return None
                if last_created > 0 and (now - last_created) < cooldown_sec:
                    logger.info(
                        "enqueue_pending_order cooldown: last_id=%s status=%s age=%s (<%s) "
                        "sid=%s sym=%s sig=%s",
                        last_id,
                        last_status,
                        now - last_created,
                        cooldown_sec,
                        strategy_id,
                        symbol,
                        signal_type,
                    )
                    return None

            user_id = self.data_handler.get_user_id(strategy_id)
            pending_id = self.data_handler.insert_pending_order(
                user_id=user_id,
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                signal_ts=stsig,
                market_type=market_type or "swap",
                order_type="market",
                amount=float(amount or 0.0),
                price=float(price or 0.0),
                execution_mode=mode,
                status="pending",
                priority=0,
                attempts=0,
                max_attempts=10,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            return int(pending_id) if pending_id is not None else None
        except Exception as e:
            logger.error("enqueue_pending_order failed: %s", e)
            return None

    def execute_exchange_order(
        self,
        exchange: Any,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        amount: float,
        ref_price: Optional[float] = None,
        market_type: str = "swap",
        market_category: str = "Crypto",
        leverage: float = 1.0,
        margin_mode: str = "cross",
        stop_loss_price: float = None,
        take_profit_price: float = None,
        order_mode: str = None,
        maker_wait_sec: float = None,
        maker_retries: int = 3,
        close_fallback_to_market: bool = True,
        open_fallback_to_market: bool = True,
        execution_mode: str = "signal",
        notification_config: Optional[Dict[str, Any]] = None,
        signal_ts: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Convert a signal into a concrete pending order and enqueue it into DB.

        A separate worker will poll `pending_orders` and dispatch:
        - execution_mode='signal': dispatch notifications (no real trading).
        - execution_mode='live': reserved for future live trading execution (not implemented).
        """
        try:
            if ref_price is None and self._price_fetcher:
                ref_price = self._price_fetcher.fetch_current_price(
                    exchange, symbol, market_type, market_category
                ) or 0.0
            ref_price = float(ref_price or 0.0)

            extra_payload = {
                "ref_price": float(ref_price or 0.0),
                "signal_ts": int(signal_ts or 0),
                "stop_loss_price": float(stop_loss_price or 0.0)
                if stop_loss_price is not None
                else 0.0,
                "take_profit_price": float(take_profit_price or 0.0)
                if take_profit_price is not None
                else 0.0,
                "margin_mode": str(margin_mode or "cross"),
                "maker_retries": int(maker_retries or 0),
                "close_fallback_to_market": bool(close_fallback_to_market),
                "open_fallback_to_market": bool(open_fallback_to_market),
            }
            pending_id = self.enqueue_pending_order(
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                amount=float(amount or 0.0),
                price=float(ref_price or 0.0),
                signal_ts=int(signal_ts or 0),
                market_type=market_type,
                leverage=float(leverage or 1.0),
                execution_mode=execution_mode,
                notification_config=notification_config,
                extra_payload=extra_payload,
            )

            pending_flag = str(execution_mode or "").strip().lower() == "live"

            return {
                "success": True,
                "pending": bool(pending_flag),
                "order_id": f"pending_{pending_id or int(time.time()*1000)}",
                "filled_amount": 0 if pending_flag else amount,
                "filled_base_amount": 0 if pending_flag else amount,
                "filled_price": 0 if pending_flag else ref_price,
                "total_cost": 0
                if pending_flag
                else (
                    float(amount or 0.0) * float(ref_price or 0.0) if ref_price else 0
                ),
                "fee": 0,
                "message": "Order enqueued to pending_orders",
            }
        except Exception as e:
            logger.error("Signal execution failed: %s", e)
            return {"success": False, "error": str(e)}
