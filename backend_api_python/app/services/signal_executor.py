"""
Signal executor: 执行交易信号（状态机校验、下单、持仓更新）。

重构为类 `SignalExecutor`，封装了外部依赖（data_handler, pending_order_enqueuer 等），
从而简化每次执行信号时的传参。
"""
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.server_side_risk import to_ratio
from app.services.signal_processor import is_signal_allowed, position_state
from app.services.entry_ai_filter import is_entry_ai_filter_enabled, entry_ai_filter_allows
from app.services.pending_order_enqueuer import PendingOrderEnqueuer
from app.services.data_handler import DataHandler
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _get_available_capital(strategy_id: int, initial_capital: float) -> float:
    """获取策略可用资金（自闭环）"""
    try:
        data_handler = DataHandler()
        used_by_positions = data_handler.get_position_used_capital(strategy_id)
        pending_amount = data_handler.get_pending_order_amount(strategy_id)
        available = initial_capital - used_by_positions - pending_amount
        return max(available, 0)
    except Exception as e:
        logger.warning(f"获取可用资金失败: {e}")
        return initial_capital


class SignalExecutor:
    """信号执行器，负责将交易信号转化为实际的订单或模拟持仓更新。"""
    def __init__(self):
        self.data_handler = DataHandler()
        self.pending_order_enqueuer = PendingOrderEnqueuer()

    def _check_ai_filter(
        self, strategy_ctx: Dict[str, Any], symbol: str, sig: str, signal_ts: int
    ) -> bool:
        """检查 AI 过滤是否允许开仓。返回 False 表示被拦截。"""
        ai_model_config = strategy_ctx.get("ai_model_config") or {}
        trading_config = strategy_ctx.get("trading_config") or {}
        strategy_id = int(strategy_ctx.get("id") or 0)

        ai_enabled = is_entry_ai_filter_enabled(
            ai_model_config=ai_model_config, trading_config=trading_config
        )
        if not ai_enabled or sig not in ("open_long", "open_short"):
            return True

        ok_ai, ai_info = entry_ai_filter_allows(
            symbol=symbol,
            signal_type=sig,
            ai_model_config=ai_model_config,
            trading_config=trading_config,
        )
        if ok_ai:
            return True

        reason = (ai_info or {}).get("reason") or "ai_filter_rejected"
        ai_decision = (ai_info or {}).get("ai_decision") or ""
        title = f"AI过滤拦截开仓 | {symbol}"
        msg = (
            f"策略信号={sig}，AI决策={ai_decision or 'UNKNOWN'}，"
            f"原因={reason}；已HOLD（不下单）"
        )
        self.data_handler.persist_notification(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type="ai_filter_hold",
            title=title,
            message=msg,
            payload={
                "event": "qd.ai_filter",
                "strategy_id": strategy_id,
                "strategy_name": strategy_ctx.get("_strategy_name", ""),
                "symbol": symbol,
                "signal_type": sig,
                "ai_decision": ai_decision,
                "reason": reason,
                "signal_ts": signal_ts,
            },
        )
        logger.info(
            "AI entry filter rejected: strategy_id=%s symbol=%s signal=%s ai=%s reason=%s",
            strategy_id, symbol, sig, ai_decision, reason,
        )
        return False

    def _calculate_target_weight_amount(
        self,
        signal: Dict[str, Any],
        sig: str,
        current_price: float,
        current_positions: List[Dict[str, Any]],
        available_capital: float,
        market_type: str,
        leverage: float,
    ) -> tuple[float, str]:
        target_weight = signal.get("target_weight")
        target_ratio = to_ratio(target_weight, default=0.0)
        if market_type == "spot":
            target_amount = available_capital * target_ratio / current_price
        else:
            target_amount = (
                available_capital * target_ratio * leverage
            ) / current_price

        pos_side = "long" if "long" in sig else "short"
        pos = next(
            (
                p for p in current_positions
                if (p.get("side") or "").strip().lower() == pos_side
            ),
            None,
        )
        old_size = float(pos.get("size") or 0.0) if pos else 0.0

        if target_amount > old_size + 1e-8:
            return target_amount - old_size, f"open_{pos_side}" if old_size == 0 else f"add_{pos_side}"

        if target_amount < old_size - 1e-8:
            if target_amount <= old_size * 0.001:
                return old_size, f"close_{pos_side}"
            return old_size - target_amount, f"reduce_{pos_side}"

        return 0.0, signal.get("type", "")

    def _calculate_order_amount(
        self,
        strategy_ctx: Dict[str, Any],
        signal: Dict[str, Any],
        sig: str,
        current_price: float,
        current_positions: List[Dict[str, Any]],
    ) -> tuple[float, str]:
        """计算下单数量。返回 (amount, 调整后的sig)"""
        strategy_id = int(strategy_ctx.get("id") or 0)
        leverage = float(strategy_ctx.get("_leverage", 1.0))
        initial_capital = float(strategy_ctx.get("_initial_capital", 10000.0))
        market_type = strategy_ctx.get("_market_type", "swap")
        trading_config = strategy_ctx.get("trading_config") or {}

        position_size = signal.get("position_size")
        signal_type = signal.get("type", "")

        # Frontend position sizing alignment
        if sig in ("open_long", "open_short") and isinstance(trading_config, dict):
            ep = trading_config.get("entry_pct")
            if ep is not None:
                position_size = to_ratio(
                    ep, default=position_size if position_size is not None else 0.0
                )

        available_capital = _get_available_capital(strategy_id, initial_capital)

        # Handle target_weight absolute sizing (for cross_sectional_weighted)
        if signal.get("target_weight") is not None:
            return self._calculate_target_weight_amount(
                signal, sig, current_price, current_positions,
                available_capital, market_type, leverage
            )

        if "open" in sig or "add" in sig:
            if position_size is None or float(position_size) <= 0:
                position_size = 0.05
            position_ratio = to_ratio(position_size, default=0.05)
            if market_type == "spot":
                amount = available_capital * position_ratio / current_price
            else:
                amount = (available_capital * position_ratio * leverage) / current_price
            return amount, signal_type

        if sig in ("reduce_long", "reduce_short"):
            pos_side = "long" if "long" in sig else "short"
            pos = next(
                (p for p in current_positions if (p.get("side") or "").strip().lower() == pos_side),
                None,
            )
            if not pos:
                return 0.0, signal_type

            cur_size = float(pos.get("size") or 0.0)
            if cur_size <= 0:
                return 0.0, signal_type

            reduce_ratio = to_ratio(position_size, default=0.1)
            reduce_amount = cur_size * reduce_ratio
            if reduce_amount >= cur_size * 0.999:
                return cur_size, "close_long" if pos_side == "long" else "close_short"
            return reduce_amount, signal_type

        if "close" in sig:
            pos = next(
                (p for p in current_positions if p.get("side") and p["side"] in signal_type),
                None,
            )
            if not pos:
                return 0.0, signal_type
            return float(pos.get("size") or 0.0), signal_type

        return 0.0, signal_type

    def _handle_open_or_add_position(
        self, strategy_id: int, symbol: str, signal_type: str,
        amount: float, current_price: float, current_positions: List[Dict[str, Any]]
    ) -> None:
        self.data_handler.record_trade(
            strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
            price=current_price, amount=amount, value=amount * current_price,
        )
        side = "short" if "short" in signal_type else "long"
        old_pos = next((p for p in current_positions if p.get("side") == side), None)
        new_size = amount
        new_entry = current_price
        if old_pos:
            old_size = float(old_pos.get("size", 0.0))
            old_entry = float(old_pos.get("entry_price", 0.0))
            new_size += old_size
            if new_size > 0:
                new_entry = ((old_size * old_entry) + (amount * current_price)) / new_size

        self.data_handler.update_position(
            strategy_id=strategy_id, symbol=symbol, side=side,
            size=new_size, entry_price=new_entry, current_price=current_price,
        )

    def _handle_reduce_position(
        self, strategy_id: int, symbol: str, signal_type: str,
        amount: float, current_price: float, current_positions: List[Dict[str, Any]]
    ) -> None:
        side = "short" if "short" in signal_type else "long"
        old_pos = next((p for p in current_positions if p.get("side") == side), None)
        if not old_pos:
            return

        old_size = float(old_pos.get("size", 0.0))
        old_entry = float(old_pos.get("entry_price", 0.0))

        reduce_profit = None
        if old_entry > 0 and amount > 0:
            if side == "long":
                reduce_profit = (current_price - old_entry) * amount
            else:
                reduce_profit = (old_entry - current_price) * amount

        self.data_handler.record_trade(
            strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
            price=current_price, amount=amount, value=amount * current_price,
            profit=reduce_profit,
        )

        new_size = max(0.0, old_size - float(amount or 0.0))
        if new_size <= old_size * 0.001:
            self.data_handler.close_position(strategy_id, symbol, side)
        else:
            self.data_handler.update_position(
                strategy_id=strategy_id, symbol=symbol, side=side,
                size=new_size, entry_price=old_entry, current_price=current_price,
            )

    def _handle_close_position(
        self, strategy_id: int, symbol: str, signal_type: str,
        amount: float, current_price: float, current_positions: List[Dict[str, Any]]
    ) -> None:
        side = "short" if "short" in signal_type else "long"
        old_pos = next((p for p in current_positions if p.get("side") == side), None)
        if not old_pos:
            return

        close_profit = None
        entry_price = float(old_pos.get("entry_price", 0.0))
        if entry_price > 0 and amount > 0:
            if side == "long":
                close_profit = (current_price - entry_price) * amount
            else:
                close_profit = (entry_price - current_price) * amount

        self.data_handler.record_trade(
            strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
            price=current_price, amount=amount, value=amount * current_price,
            profit=close_profit,
        )
        self.data_handler.close_position(strategy_id, symbol, side)

    def _update_local_position(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        amount: float,
        current_price: float,
        current_positions: List[Dict[str, Any]],
    ) -> None:
        """更新本地模拟持仓状态"""
        actual_sig = signal_type.strip().lower()
        if "open" in actual_sig or "add" in actual_sig:
            self._handle_open_or_add_position(
                strategy_id, symbol, signal_type, amount, current_price, current_positions
            )
            return

        if actual_sig.startswith("reduce_"):
            self._handle_reduce_position(
                strategy_id, symbol, signal_type, amount, current_price, current_positions
            )
            return

        if "close" in actual_sig:
            self._handle_close_position(
                strategy_id, symbol, signal_type, amount, current_price, current_positions
            )
            return

    def execute(
        self,
        strategy_ctx: Dict[str, Any],
        signal: Dict[str, Any],
        **exec_kwargs
    ) -> bool:
        """
        执行具体的交易信号（不含 AI 过滤，调用方需在调用前完成 AI 过滤）。
        """
        try:
            symbol = exec_kwargs.get("symbol", "")
            current_price = exec_kwargs.get("current_price", 0.0)
            current_positions = exec_kwargs.get("current_positions", [])
            exchange = exec_kwargs.get("exchange")

            strategy_id = int(strategy_ctx.get("id") or 0)
            leverage = float(strategy_ctx.get("_leverage", 1.0))
            market_type = strategy_ctx.get("_market_type", "swap")
            market_category = strategy_ctx.get("_market_category", "Crypto")
            execution_mode = strategy_ctx.get("_execution_mode", "signal")
            notification_config = strategy_ctx.get("_notification_config") or {}

            signal_type = signal.get("type", "")
            signal_ts = int(signal.get("timestamp") or 0)
            stop_loss_price = signal.get("stop_loss_price")
            take_profit_price = signal.get("take_profit_price")

            state = position_state(current_positions)

            # Target weight sizing inherently allows adding to an existing position,
            # even if the original signal was "open_long" or "open_short",
            # so we bypass the strict state machine check for target_weight signals
            if signal.get("target_weight") is None and not is_signal_allowed(state, signal_type):
                return False

            if market_type == "spot" and "short" in signal_type:
                return False

            sig = signal_type.strip().lower()

            if not self._check_ai_filter(strategy_ctx, symbol, sig, signal_ts):
                return False

            amount, signal_type = self._calculate_order_amount(
                strategy_ctx, signal, sig, current_price, current_positions
            )

            from app.services.live_trading.order_normalizer import get_market_pre_normalizer
            normalizer = get_market_pre_normalizer(market_category)
            raw_amount = amount
            amount = normalizer.pre_normalize(amount, symbol)
            if raw_amount != amount:
                logger.info(
                    "Order quantity normalized: %.6f -> %s (strategy=%s symbol=%s market=%s)",
                    raw_amount, amount, strategy_id, symbol, market_category,
                )

            if amount <= 0:
                logger.debug("Amount %s <= 0, returning False", amount)
                return False

            order_result = self.pending_order_enqueuer.execute_exchange_order(
                exchange=exchange, strategy_id=strategy_id, symbol=symbol,
                signal_type=signal_type, amount=amount,
                ref_price=float(current_price or 0.0), market_type=market_type,
                market_category=market_category, leverage=leverage, margin_mode="cross",
                stop_loss_price=stop_loss_price, take_profit_price=take_profit_price,
                execution_mode=execution_mode, notification_config=notification_config,
                signal_ts=signal_ts,
            )

            if not order_result or not order_result.get("success"):
                return False

            if str(execution_mode or "").strip().lower() == "live":
                return True

            self._update_local_position(
                strategy_id, symbol, signal_type, amount,
                current_price, current_positions
            )
            return True

        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as e:
            logger.error("Failed to execute signal: %s", e, exc_info=True)
            return False

    def _fetch_price_for_signal(self, symbol: str, strategy_ctx: Dict[str, Any]) -> float:
        """Fetch current price for a signal's symbol using the strategy's market context."""
        try:
            from app.services.price_fetcher import PriceFetcher
            market_type = strategy_ctx.get("_market_type", "swap")
            market_category = strategy_ctx.get("_market_category", "Crypto")
            pf = PriceFetcher()
            price = pf.fetch_current_price(
                exchange=None, symbol=symbol,
                market_type=market_type, market_category=market_category,
            )
            return float(price) if price else 0.0
        except Exception as e:
            logger.warning("Failed to fetch price for %s: %s", symbol, e)
            return 0.0

    def execute_batch(
        self,
        strategy_ctx: Dict[str, Any],
        signals: List[Dict[str, Any]],
        all_positions: List[Dict[str, Any]],
        current_time: int,
    ) -> None:
        """并发执行批量信号"""
        strategy_id = strategy_ctx.get("id", "?")
        market_category = strategy_ctx.get("_market_category", "?")
        logger.info(
            "execute_batch: strategy=%s market=%s signals=%d positions=%d",
            strategy_id, market_category, len(signals), len(all_positions),
        )

        with ThreadPoolExecutor(max_workers=min(10, len(signals))) as pool:
            futures = {}
            for signal in signals:
                sig_symbol = (signal.get("symbol") or "")
                symbol_positions = [
                    p for p in all_positions
                    if (p.get("symbol") or "").split(":")[0] == sig_symbol.split(":")[0]
                ]

                if not signal.get("timestamp"):
                    signal["timestamp"] = int(current_time)

                price = self._fetch_price_for_signal(sig_symbol, strategy_ctx)
                if price <= 0:
                    logger.warning(
                        "execute_batch: skip %s %s — price=0 (market=%s)",
                        sig_symbol, signal.get("type"), market_category,
                    )
                    continue

                logger.debug(
                    "execute_batch: %s %s price=%.4f weight=%s",
                    sig_symbol, signal.get("type"), price, signal.get("target_weight"),
                )

                future = pool.submit(
                    self.execute,
                    strategy_ctx=strategy_ctx,
                    signal=signal,
                    symbol=signal["symbol"],
                    current_price=price,
                    current_positions=symbol_positions,
                    exchange=None,
                )
                futures[future] = signal

            for future in as_completed(futures):
                signal = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        logger.debug("execute_batch: OK %s %s", signal["symbol"], signal["type"])
                    else:
                        logger.debug("execute_batch: SKIPPED %s %s", signal["symbol"], signal["type"])
                except (ValueError, TypeError, KeyError, RuntimeError, OSError, TimeoutError) as e:
                    logger.error(
                        "execute_batch: FAILED %s %s: %s",
                        signal["symbol"],
                        signal["type"],
                        e,
                        exc_info=True,
                    )
