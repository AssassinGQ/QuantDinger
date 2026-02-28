"""
单标策略：仅负责生成信号，不依赖 Executor。

- get_data_request(): 返回本 tick 的数据请求，供 Executor 传给 DataHandler
- get_signals(ctx): 基于 InputContext 生成信号，纯计算
- 指标执行由 run_single_indicator 完成，信号提取由 extract_pending_signals_from_df 完成
"""

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from app.data_sources.base import TIMEFRAME_SECONDS
from app.strategies.base import DataRequest, IStrategyLoop, InputContext
from app.strategies.single_symbol_indicator import run_single_indicator
from app.strategies.single_symbol_signals import extract_pending_signals_from_df
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SingleSymbolStrategy(IStrategyLoop):
    """
    单标策略：只生成信号。
    Executor 通过 DataHandler 构建 InputContext，调用 get_signals(ctx) 获取信号。
    """

    def __init__(self):
        self._state: Dict[str, Any] = {}

    def need_macro_info(self) -> bool:
        return False

    def get_data_request(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        current_time: float,
    ) -> DataRequest:
        """返回本 tick 的数据请求"""
        trading_config = strategy.get("trading_config") or {}
        symbol = trading_config.get("symbol", "")
        timeframe = trading_config.get("timeframe", "1H")
        include_macro = trading_config.get("include_macro", False)
        history_limit = int(os.getenv("K_LINE_HISTORY_GET_NUMBER", "500"))
        market_category = strategy.get("_market_category", "Crypto")
        timeframe_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)

        state = self._state
        refresh_klines = True
        df_override = None
        if state.get("_initialized"):
            last_update = state.get("last_kline_update_time", 0)
            refresh_klines = (current_time - last_update) >= timeframe_seconds
            if not refresh_klines and state.get("df") is not None and len(state["df"]) > 0:
                df_override = state["df"].copy()

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "trading_config": trading_config,
            "need_macro": include_macro,
            "refresh_klines": refresh_klines,
            "df_override": df_override,
            "history_limit": history_limit,
            "market_category": market_category,
        }

    def get_signals(
        self,
        ctx: InputContext,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[bool], Optional[Dict[str, Any]]]:
        """
        基于 InputContext 生成本 tick 触发的信号。
        """
        strategy_id = ctx.get("strategy_id", 0)
        indicator_code = ctx.get("indicator_code", "")
        trading_config = ctx.get("trading_config") or {}
        symbol = ctx.get("symbol", "")
        timeframe = trading_config.get("timeframe", "1H")
        current_price = ctx.get("current_price")
        current_time = ctx.get("current_time", time.time())
        timeframe_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)

        if current_price is None:
            logger.error("SingleSymbolStrategy.get_signals requires current_price in ctx")
            return [], False, None, None

        was_initialized = self._state.get("_initialized")
        if not was_initialized:
            ok = self._init_from_ctx(ctx, timeframe_seconds)
            if not ok:
                return [], False, None, None

        state = self._state
        meta = None

        # 已初始化时：本 tick 的 ctx 由 DataHandler 构建，需跑指标更新 pending_signals
        if was_initialized:
            kline_df = ctx.get("df")
        else:
            kline_df = None  # 首次 init 已跑过指标，跳过

        if kline_df is not None and len(kline_df) > 0:
            executed_df, exec_env = run_single_indicator(
                indicator_code,
                kline_df,
                trading_config,
                initial_highest_price=ctx.get("initial_highest_price", 0.0),
                initial_position=ctx.get("initial_position", 0),
                initial_avg_entry_price=ctx.get("initial_avg_entry_price", 0.0),
                initial_position_count=ctx.get("initial_position_count", 0),
                initial_last_add_price=ctx.get("initial_last_add_price", 0.0),
            )
            if executed_df is not None:
                last_kt = (
                    int(kline_df.index[-1].timestamp())
                    if hasattr(kline_df.index[-1], "timestamp")
                    else int(time.time())
                )
                pending_signals = extract_pending_signals_from_df(
                    executed_df, trading_config, last_kt
                )
                state["pending_signals"] = pending_signals
                state["df"] = kline_df
                state["current_pos_list"] = ctx.get("positions", [])
                state["last_kline_update_time"] = current_time

                # 收集 position_updates 供 Executor 持久化
                new_hp = exec_env.get("highest_price", 0)
                position_updates: List[Dict[str, Any]] = []
                if new_hp > 0 and state["current_pos_list"]:
                    current_close = float(kline_df["close"].iloc[-1])
                    for p in state["current_pos_list"]:
                        position_updates.append({
                            "symbol": p["symbol"],
                            "side": p["side"],
                            "size": float(p.get("size", 0)),
                            "entry_price": float(p.get("entry_price", 0)),
                            "current_close": current_close,
                            "highest_price": new_hp,
                        })
                meta = {"position_updates": position_updates} if position_updates else None

        pending_signals = state["pending_signals"]
        current_ts = int(time.time())
        if pending_signals:
            expiration_threshold = timeframe_seconds * 2
            valid_signals = [
                s for s in pending_signals
                if s.get("timestamp", 0) == 0
                or (current_ts - s.get("timestamp", 0)) < expiration_threshold
            ]
            if len(valid_signals) != len(pending_signals):
                for s in pending_signals:
                    if s not in valid_signals:
                        logger.warning("Signal expired and removed: %s", s)
                pending_signals = valid_signals
                state["pending_signals"] = pending_signals

        if pending_signals:
            logger.info(
                "[monitoring] strategy=%s price=%s, pending_signals=%d",
                strategy_id, current_price, len(pending_signals),
            )

        # 应用触发逻辑
        triggered_signals = []
        signals_to_remove = []
        for signal_info in pending_signals:
            signal_type = signal_info.get("type")
            trigger_price = signal_info.get("trigger_price", 0)
            triggered = False
            exit_trigger_mode = trading_config.get("exit_trigger_mode", "immediate")
            if signal_type in ["close_long", "close_short"] and exit_trigger_mode == "immediate":
                triggered = True
            entry_trigger_mode = trading_config.get("entry_trigger_mode", "price")
            if signal_type in ["open_long", "open_short", "add_long", "add_short"] and entry_trigger_mode == "immediate":
                triggered = True
            if trigger_price > 0:
                if signal_type in ["open_long", "close_short", "add_long"]:
                    if current_price >= trigger_price:
                        triggered = True
                elif signal_type in ["open_short", "close_long", "add_short"]:
                    if current_price <= trigger_price:
                        triggered = True
            else:
                triggered = True
            if triggered:
                triggered_signals.append(signal_info)
                signals_to_remove.append(signal_info)

        for signal_info in signals_to_remove:
            if signal_info in pending_signals:
                pending_signals.remove(signal_info)
        state["pending_signals"] = pending_signals

        if triggered_signals:
            logger.info("Strategy %s triggered signals: %s", strategy_id, triggered_signals)

        return triggered_signals, True, None, meta

    def _init_from_ctx(self, ctx: InputContext, timeframe_seconds: int) -> bool:
        """从 ctx 初始化：跑指标、提取 pending_signals"""
        strategy_id = ctx.get("strategy_id", 0)
        indicator_code = ctx.get("indicator_code", "")
        df = ctx.get("df")
        if df is None or len(df) == 0:
            logger.error("Strategy %s failed to fetch K-lines", strategy_id)
            return False

        logger.info("Strategy %s history kline number: %d", strategy_id, len(df))
        current_pos_list = ctx.get("positions", [])
        logger.info(
            "策略 %s 指标注入持仓状态: count=%d, position=%s, entry_price=%s, highest=%s",
            strategy_id, len(current_pos_list),
            ctx.get("initial_position"), ctx.get("initial_avg_entry_price"),
            ctx.get("initial_highest_price"),
        )

        executed_df, _ = run_single_indicator(
            indicator_code,
            df,
            ctx.get("trading_config", {}),
            initial_highest_price=ctx.get("initial_highest_price", 0.0),
            initial_position=ctx.get("initial_position", 0),
            initial_avg_entry_price=ctx.get("initial_avg_entry_price", 0.0),
            initial_position_count=ctx.get("initial_position_count", 0),
            initial_last_add_price=ctx.get("initial_last_add_price", 0.0),
        )
        if executed_df is None:
            logger.error("Strategy %s indicator execution failed", strategy_id)
            return False

        last_kline_time = (
            int(df.index[-1].timestamp())
            if hasattr(df.index[-1], "timestamp")
            else int(time.time())
        )
        pending_signals = extract_pending_signals_from_df(
            executed_df, ctx.get("trading_config", {}), last_kline_time
        )
        logger.info("Strategy %s initialized; pending_signals=%d", strategy_id, len(pending_signals))
        if pending_signals:
            logger.info("Initial signals: %s", pending_signals)

        self._state = {
            "_initialized": True,
            "df": df,
            "pending_signals": pending_signals,
            "current_pos_list": current_pos_list,
            "last_kline_update_time": time.time(),
            "timeframe_seconds": timeframe_seconds,
        }
        return True
