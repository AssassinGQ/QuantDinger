"""
单标 Regime 加权策略运行管道。

继承 SingleSymbolRunner，在每次 tick 中：
1. 从数据库读取 last_rebalance_at，判断是否到了 regime 再平衡周期
2. 将 should_regime_rebalance 注入 InputContext
3. 信号执行后，若策略返回 update_rebalance=True 则更新 last_rebalance_at
4. 将 regime metadata 保存到 status_info
"""
from dataclasses import dataclass
from typing import Any, Dict

from app.strategies.runners.single_symbol_runner import SingleSymbolRunner
from app.strategies.base import IStrategyLoop
from app.strategies.regime_mixin import check_rebalance_due
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class _TickArgs:
    """_run_single_tick 的参数容器，用于减少方法参数数量。"""
    strategy_id: int
    strategy: Dict[str, Any]
    strat_instance: IStrategyLoop
    exchange: Any
    current_time: float


class SingleRegimeWeightedRunner(SingleSymbolRunner):
    """单标 Regime 加权策略的运行流水线。"""

    def _run_single_tick(self, *args):
        """覆盖父类 tick 方法，参数签名与 SingleSymbolRunner 一致。"""
        return self._do_regime_tick(_TickArgs(*args))

    def run_tick(self, tick_args: _TickArgs) -> bool:
        """公开的 tick 方法，供测试调用。"""
        return self._do_regime_tick(tick_args)

    def _do_regime_tick(self, args: _TickArgs) -> bool:
        """执行一次 regime tick 逻辑。"""
        ctx, current_price = self._build_tick_context(args)
        if ctx is None:
            return True

        trading_config = args.strategy.get("trading_config") or {}
        self._inject_rebalance_flag(ctx, args.strategy_id, trading_config)

        signals, keep_running, update_rebalance, meta = args.strat_instance.get_signals(ctx)
        if not keep_running:
            logger.warning("Strategy %s get_signals returned stop", args.strategy_id)
            return False

        self._handle_post_signals(args.strategy_id, meta, update_rebalance)

        if signals:
            self._process_and_execute_signals(
                strategy=args.strategy,
                triggered_signals=signals,
                current_price=current_price,
                exchange=args.exchange,
            )

        symbol = trading_config.get("symbol", "")
        self.data_handler.update_positions_current_price(
            args.strategy_id, symbol, current_price,
        )
        return True

    def _build_tick_context(self, args: _TickArgs):
        """获取价格、构造上下文，返回 (ctx, current_price) 或 (None, None)。"""
        trading_config = args.strategy.get("trading_config") or {}
        symbol = trading_config.get("symbol", "")

        current_price = self.price_fetcher.fetch_current_price(
            args.exchange, symbol,
            market_type=args.strategy.get("_market_type", "swap"),
            market_category=args.strategy.get("_market_category", "Crypto"),
        )
        self._maybe_notify_prev_close_stale(
            args.strategy_id,
            args.strategy,
            symbol,
            args.strategy.get("_market_category", "Crypto"),
        )
        if current_price is None:
            logger.warning(
                "Strategy %s failed to fetch current price for %s",
                args.strategy_id, symbol,
            )
            return None, None

        request = args.strat_instance.get_data_request(
            args.strategy_id, args.strategy, args.current_time,
        )
        ctx = self.data_handler.get_input_context_single(
            args.strategy_id, request, current_price=float(current_price),
        )
        if ctx is None:
            logger.warning("Strategy %s failed to get input context", args.strategy_id)
            return None, None

        ctx["strategy_id"] = args.strategy_id
        ctx["indicator_code"] = args.strategy.get("_indicator_code", "")
        ctx["current_time"] = args.current_time
        ctx["current_price"] = float(current_price)
        return ctx, float(current_price)

    def _inject_rebalance_flag(self, ctx, strategy_id, trading_config):
        """注入 should_regime_rebalance 标志到 ctx。"""
        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        rebalance_freq = trading_config.get("rebalance_frequency", "daily")
        rebalance_now = check_rebalance_due(rebalance_freq, last_rebalance)
        ctx["should_regime_rebalance"] = rebalance_now

        if rebalance_now:
            logger.info(
                "Strategy %s regime rebalance triggered (last=%s, freq=%s)",
                strategy_id, last_rebalance, rebalance_freq,
            )

    def _handle_post_signals(self, strategy_id, meta, update_rebalance):
        """处理信号后的 metadata 保存和 rebalance 更新。"""
        if meta:
            self.data_handler.update_strategy_status_info(strategy_id, meta)
            for pu in meta.get("position_updates") or []:
                self.data_handler.update_position(
                    strategy_id=strategy_id,
                    symbol=pu["symbol"],
                    side=pu["side"],
                    size=pu["size"],
                    entry_price=pu["entry_price"],
                    current_price=pu["current_close"],
                    highest_price=pu["highest_price"],
                )
        if update_rebalance:
            self.data_handler.update_last_rebalance(strategy_id)