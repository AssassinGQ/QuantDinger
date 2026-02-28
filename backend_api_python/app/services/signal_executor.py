"""
Signal executor: 执行交易信号（状态机校验、下单、持仓更新）。

重构为类 `SignalExecutor`，封装了外部依赖（data_handler, pending_order_enqueuer 等），
从而简化每次执行信号时的传参。
"""
from typing import Any, Callable, Dict, List, Optional

from app.services.server_side_risk import to_ratio
from app.services.signal_processor import is_signal_allowed, position_state
from app.services.pending_order_enqueuer import PendingOrderEnqueuer
from app.services.data_handler import DataHandler
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _get_available_capital(strategy_id: int, initial_capital: float) -> float:
    """获取可用资金：优先从 PortfolioAllocator 获取动态分配，fallback 到 initial_capital。"""
    try:
        from app.services.portfolio_allocator import get_portfolio_allocator
        allocator = get_portfolio_allocator()
        allocated = allocator.get_allocated_capital(strategy_id)
        if allocated is not None:
            return allocated
    except Exception:
        pass
    return initial_capital


class SignalExecutor:
    def __init__(self):
        self.data_handler = DataHandler()
        self.pending_order_enqueuer = PendingOrderEnqueuer()

    def execute(
        self,
        strategy_ctx: Dict[str, Any],
        signal: Dict[str, Any],
        symbol: str,
        current_price: float,
        current_positions: List[Dict[str, Any]],
        exchange: Any = None,
    ) -> bool:
        """
        执行具体的交易信号（不含 AI 过滤，调用方需在调用前完成 AI 过滤）。

        Args:
            strategy_ctx: 包含策略全量配置的字典（来自 DB 行，含内部提取的 _ 属性）。
            signal: 信号内容字典。
            symbol: 交易对。
            current_price: 当前触发价格或最新市价。
            current_positions: 当前的持仓列表。
            exchange: 交易所实例（可选）。

        Returns:
            True 表示执行成功，False 表示被拒绝或失败。
        """
        try:
            # 1. 提取策略配置
            strategy_id = int(strategy_ctx.get("id") or 0)
            leverage = float(strategy_ctx.get("_leverage", 1.0))
            initial_capital = float(strategy_ctx.get("_initial_capital", 10000.0))
            market_type = strategy_ctx.get("_market_type", "swap")
            market_category = strategy_ctx.get("_market_category", "Crypto")
            execution_mode = strategy_ctx.get("_execution_mode", "signal")
            notification_config = strategy_ctx.get("_notification_config") or {}
            trading_config = strategy_ctx.get("trading_config") or {}
            margin_mode = "cross"  # 固定为 cross，如需可放入配置

            # 2. 提取信号内容
            signal_type = signal.get("type", "")
            position_size = signal.get("position_size")
            signal_ts = int(signal.get("timestamp") or 0)
            stop_loss_price = signal.get("stop_loss_price")
            take_profit_price = signal.get("take_profit_price")

            # Hard state-machine guard
            state = position_state(current_positions)
            if not is_signal_allowed(state, signal_type):
                return False

            # 检查交易方向限制
            if market_type == "spot" and "short" in signal_type:
                return False

            sig = signal_type.strip().lower()

            # 计算下单数量
            available_capital = _get_available_capital(strategy_id, initial_capital)
            amount = 0.0

            # Frontend position sizing alignment: open_* uses entry_pct from trading_config
            if sig in ("open_long", "open_short") and isinstance(trading_config, dict):
                ep = trading_config.get("entry_pct")
                if ep is not None:
                    position_size = to_ratio(
                        ep, default=position_size if position_size is not None else 0.0
                    )

            # Open / add sizing
            if "open" in sig or "add" in sig:
                if position_size is None or float(position_size) <= 0:
                    position_size = 0.05
                position_ratio = to_ratio(position_size, default=0.05)
                if market_type == "spot":
                    amount = available_capital * position_ratio / current_price
                else:
                    amount = (available_capital * position_ratio * leverage) / current_price

            # Reduce sizing
            if sig in ("reduce_long", "reduce_short"):
                pos_side = "long" if "long" in sig else "short"
                pos = next(
                    (
                        p
                        for p in current_positions
                        if (p.get("side") or "").strip().lower() == pos_side
                    ),
                    None,
                )
                if not pos:
                    return False
                cur_size = float(pos.get("size") or 0.0)
                if cur_size <= 0:
                    return False
                reduce_ratio = to_ratio(position_size, default=0.1)
                reduce_amount = cur_size * reduce_ratio
                if reduce_amount >= cur_size * 0.999:
                    sig = "close_long" if pos_side == "long" else "close_short"
                    signal_type = sig
                    amount = cur_size
                else:
                    amount = reduce_amount

            # Close sizing
            if "close" in sig:
                pos = next(
                    (
                        p
                        for p in current_positions
                        if p.get("side") and p["side"] in signal_type
                    ),
                    None,
                )
                if not pos:
                    return False
                amount = float(pos["size"] or 0.0)
                if amount <= 0:
                    return False

            if amount <= 0 and ("open" in signal_type or "add" in signal_type):
                return False

            # Execute order enqueue
            order_result = self.pending_order_enqueuer.execute_exchange_order(
                exchange=exchange,
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                amount=amount,
                ref_price=float(current_price or 0.0),
                market_type=market_type,
                market_category=market_category,
                leverage=leverage,
                margin_mode=margin_mode,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                execution_mode=execution_mode,
                notification_config=notification_config,
                signal_ts=signal_ts,
            )

            if order_result and order_result.get("success"):
                if str(execution_mode or "").strip().lower() == "live":
                    return True

                # 更新数据库状态 (signal mode / local simulation)
                if "open" in sig or "add" in sig:
                    self.data_handler.record_trade(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        trade_type=signal_type,
                        price=current_price,
                        amount=amount,
                        value=amount * current_price,
                    )
                    side = "short" if "short" in signal_type else "long"

                    old_pos = next((p for p in current_positions if p["side"] == side), None)
                    new_size = amount
                    new_entry = current_price
                    if old_pos:
                        old_size = float(old_pos["size"])
                        old_entry = float(old_pos["entry_price"])
                        new_size += old_size
                        new_entry = (
                            (old_size * old_entry) + (amount * current_price)
                        ) / new_size

                    self.data_handler.update_position(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        side=side,
                        size=new_size,
                        entry_price=new_entry,
                        current_price=current_price,
                    )
                elif sig.startswith("reduce_"):
                    side = "short" if "short" in signal_type else "long"
                    old_pos = next(
                        (p for p in current_positions if p.get("side") == side), None
                    )
                    if not old_pos:
                        return True
                    old_size = float(old_pos.get("size") or 0.0)
                    old_entry = float(old_pos.get("entry_price") or 0.0)

                    reduce_profit = None
                    if old_entry > 0 and amount > 0:
                        if side == "long":
                            reduce_profit = (current_price - old_entry) * amount
                        else:
                            reduce_profit = (old_entry - current_price) * amount

                    self.data_handler.record_trade(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        trade_type=signal_type,
                        price=current_price,
                        amount=amount,
                        value=amount * current_price,
                        profit=reduce_profit,
                    )

                    new_size = max(0.0, old_size - float(amount or 0.0))
                    if new_size <= old_size * 0.001:
                        self.data_handler.close_position(strategy_id, symbol, side)
                    else:
                        self.data_handler.update_position(
                            strategy_id=strategy_id,
                            symbol=symbol,
                            side=side,
                            size=new_size,
                            entry_price=old_entry,
                            current_price=current_price,
                        )
                elif "close" in sig:
                    side = "short" if "short" in signal_type else "long"
                    old_pos = next(
                        (p for p in current_positions if p.get("side") == side), None
                    )

                    close_profit = None
                    if old_pos:
                        entry_price = float(old_pos.get("entry_price") or 0)
                        if entry_price > 0 and amount > 0:
                            if side == "long":
                                close_profit = (current_price - entry_price) * amount
                            else:
                                close_profit = (entry_price - current_price) * amount

                    self.data_handler.record_trade(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        trade_type=signal_type,
                        price=current_price,
                        amount=amount,
                        value=amount * current_price,
                        profit=close_profit,
                    )
                    self.data_handler.close_position(strategy_id, symbol, side)

                return True

            return False

        except Exception as e:
            logger.error("Failed to execute signal: %s", e)
            return False
