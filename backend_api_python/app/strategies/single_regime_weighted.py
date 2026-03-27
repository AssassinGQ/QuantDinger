"""
单标 Regime 加权策略。

继承 SingleSymbolStrategy 的全部信号生成逻辑，在 regime 调仓周期到达时：
1. 从 df 最后一行读取宏观指标 → 计算当前 regime → 获取可用资金比例
2. 若当前持仓超过新可用资金，生成平仓信号
3. 调整新开仓信号的 position_size
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from app.strategies.base import InputContext
from app.strategies.single_symbol import SingleSymbolStrategy
from app.strategies.regime_mixin import RegimeMixin, read_macro_values
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SingleRegimeWeightedStrategy(SingleSymbolStrategy, RegimeMixin):
    """单标 Regime 加权策略：信号由父类生成，regime 调仓按独立周期执行。"""

    def need_macro_info(self) -> bool:
        return True

    def get_signals(
        self,
        ctx: InputContext,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        signals, should_continue, _, meta = super().get_signals(ctx)

        if not ctx.get("should_regime_rebalance", False):
            return signals, should_continue, False, meta

        df = ctx.get("df")
        if df is None or len(df) == 0:
            logger.warning(
                "Strategy %s: should_regime_rebalance=True but df is empty, "
                "skip this rebalance cycle",
                ctx.get("strategy_id", 0),
            )
            return signals, should_continue, False, meta

        regime, capital_ratio = self._compute_regime_ratio(ctx, df)
        self._apply_regime_to_signals(signals, capital_ratio, ctx)

        if meta is None:
            meta = {}
        meta["current_regime"] = regime
        meta["capital_ratio"] = capital_ratio

        return signals, should_continue, True, meta

    def _compute_regime_ratio(
        self, ctx: InputContext, df,
    ) -> Tuple[str, float]:
        """从 df 宏观数据计算当前 regime 和可用资金比例。"""
        trading_config = ctx.get("trading_config") or {}
        macro_indicators = trading_config.get("macro_indicators", ["vix"])
        macro = read_macro_values(df, macro_indicators)

        regime = self.compute_regime_from_context(macro, trading_config)
        strategy_type = trading_config.get("regime_strategy_type", "balanced")
        capital_ratio = self.get_capital_ratio(regime, strategy_type)

        logger.info(
            "Strategy %s regime rebalance: regime=%s, strategy_type=%s, "
            "capital_ratio=%.2f",
            ctx.get("strategy_id", 0), regime, strategy_type, capital_ratio,
        )
        return regime, capital_ratio

    def _apply_regime_to_signals(
        self,
        signals: List[Dict[str, Any]],
        capital_ratio: float,
        ctx: InputContext,
    ) -> None:
        """根据 capital_ratio 生成平仓信号并调整开仓信号大小。"""
        trading_config = ctx.get("trading_config") or {}
        initial_capital = float(trading_config.get("initial_capital", 10000.0))
        positions = ctx.get("positions", [])
        current_price = ctx.get("current_price", 0)

        if positions and capital_ratio < 1.0 and current_price > 0:
            close_signals = self._generate_close_signals_for_ratio(
                positions, capital_ratio, initial_capital, current_price,
            )
            signals.extend(close_signals)

        for signal in signals:
            sig_type = signal.get("type", "")
            if sig_type.startswith("open_") or sig_type.startswith("add_"):
                base_size = signal.get("position_size")
                if base_size is not None:
                    signal["position_size"] = base_size * capital_ratio

    def _generate_close_signals_for_ratio(
        self,
        positions: List[Dict],
        capital_ratio: float,
        initial_capital: float,
        current_price: float,
    ) -> List[Dict[str, Any]]:
        """当持仓超过 regime 允许的可用资金时，生成减仓信号。"""
        close_signals: List[Dict[str, Any]] = []
        available_capital = initial_capital * capital_ratio

        used_capital = 0.0
        for pos in positions:
            pos_size = float(pos.get("size", 0))
            entry_price = float(pos.get("entry_price", 0))
            used_capital += pos_size * entry_price

        if used_capital <= available_capital:
            return close_signals

        excess_ratio = (used_capital - available_capital) / used_capital
        excess_ratio = min(excess_ratio, 1.0)

        for pos in positions:
            close_signals.append({
                "symbol": pos.get("symbol"),
                "type": f"close_{pos.get('side', 'long')}",
                "position_size": excess_ratio,
                "trigger_price": current_price,
                "timestamp": int(time.time()),
            })

        logger.info(
            "Regime close signals: used=%.2f, available=%.2f, "
            "excess_ratio=%.4f, signals=%d",
            used_capital, available_capital, excess_ratio, len(close_signals),
        )
        return close_signals
