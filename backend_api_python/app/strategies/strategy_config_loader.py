"""
策略配置加载：从 DB 加载、解析 JSON、校验、归一化。
DB 访问委托给 DataHandler，策略或 factory 不直接操作 DB。
"""

import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.services.data_handler import DataHandler

logger = get_logger(__name__)


def load_strategy(
    strategy_id: int,
    data_handler: Optional["DataHandler"] = None,
) -> Optional[Dict[str, Any]]:
    """
    加载策略配置，包含解析、校验、归一化。
    返回可直接用于 Executor 驱动策略（get_signals）的配置，失败返回 None。
    """
    try:
        if data_handler is None:
            from app.services.data_handler import DataHandler
            dh = DataHandler()
        else:
            dh = data_handler
        strategy = dh.get_strategy_row(strategy_id)
        if not strategy:
            return None

        # 解析 JSON 字段
        for field in [
            "indicator_config",
            "trading_config",
            "notification_config",
            "ai_model_config",
        ]:
            if isinstance(strategy.get(field), str):
                try:
                    strategy[field] = json.loads(strategy[field])
                except Exception:
                    strategy[field] = {}

        exchange_config_str = strategy.get("exchange_config", "{}")
        if isinstance(exchange_config_str, str) and exchange_config_str:
            try:
                strategy["exchange_config"] = json.loads(exchange_config_str)
            except Exception as e:
                logger.error(
                    "Strategy %s failed to parse exchange_config: %s",
                    strategy_id,
                    e,
                )
                try:
                    strategy["exchange_config"] = json.loads(exchange_config_str)
                except Exception:
                    strategy["exchange_config"] = {}
        else:
            strategy["exchange_config"] = {}

        # 校验 strategy_type
        if strategy.get("strategy_type") != "IndicatorStrategy":
            logger.error(
                "Strategy %s has unsupported strategy_type for realtime execution: %s",
                strategy_id,
                strategy.get("strategy_type"),
            )
            return None

        trading_config = strategy.get("trading_config") or {}
        indicator_config = strategy.get("indicator_config") or {}

        # 归一化 execution_mode
        execution_mode = (strategy.get("execution_mode") or "signal").strip().lower()
        if execution_mode not in ["signal", "live"]:
            execution_mode = "signal"
        strategy["_execution_mode"] = execution_mode

        strategy["_strategy_name"] = (
            strategy.get("strategy_name") or f"strategy_{int(strategy_id)}"
        )
        strategy["_notification_config"] = strategy.get("notification_config") or {}

        # 解析 leverage
        try:
            leverage_val = trading_config.get("leverage", 1)
            if isinstance(leverage_val, (list, tuple)):
                leverage_val = leverage_val[0] if leverage_val else 1
            leverage = float(leverage_val)
        except Exception:
            logger.warning(
                "Strategy %s invalid leverage format, reset to 1: %s",
                strategy_id,
                trading_config.get("leverage"),
            )
            leverage = 1.0

        # 归一化 market_type：杠杆=1→spot，否则→swap
        market_type = trading_config.get("market_type", "swap")
        if market_type not in ["swap", "spot"]:
            logger.error(
                "Strategy %s invalid market_type=%s (only swap/spot supported); refusing to start",
                strategy_id,
                market_type,
            )
            return None
        if leverage == 1.0:
            market_type = "spot"
            logger.info("Strategy %s leverage=1; auto-switch market_type to spot", strategy_id)
        else:
            market_type = "swap"
            logger.info(
                "Strategy %s derivatives trading; normalize market_type to: %s",
                strategy_id,
                market_type,
            )

        if market_type == "spot":
            leverage = 1.0
        elif leverage < 1:
            leverage = 1.0
        elif leverage > 125:
            leverage = 125.0
            logger.warning("Strategy %s leverage > 125; capped to 125", strategy_id)

        strategy["_market_type"] = market_type
        strategy["_leverage"] = leverage

        # market_category
        market_category = (strategy.get("market_category") or "Crypto").strip()
        strategy["_market_category"] = market_category
        logger.info("Strategy %s market_category: %s", strategy_id, market_category)

        # initial_capital
        try:
            initial_capital_val = strategy.get("initial_capital", 1000)
            if isinstance(initial_capital_val, (list, tuple)):
                initial_capital_val = (
                    initial_capital_val[0] if initial_capital_val else 1000
                )
            initial_capital = float(initial_capital_val)
        except Exception:
            logger.warning(
                "Strategy %s invalid initial_capital format, reset to 1000: %s",
                strategy_id,
                strategy.get("initial_capital"),
            )
            initial_capital = 1000.0
        strategy["_initial_capital"] = initial_capital

        # indicator_code
        indicator_id = indicator_config.get("indicator_id")
        indicator_code = indicator_config.get("indicator_code", "")
        if not indicator_code and indicator_id:
            indicator_code = dh.get_indicator_code(indicator_id)
        if not indicator_code:
            logger.error("Strategy %s indicator_code is empty", strategy_id)
            return None
        if not isinstance(indicator_code, str):
            indicator_code = str(indicator_code)
        if "\\n" in indicator_code and "\n" not in indicator_code:
            try:
                decoded = json.loads(f'"{indicator_code}"')
                if isinstance(decoded, str):
                    indicator_code = decoded
                    logger.info("Strategy %s decoded escaped indicator_code", strategy_id)
            except Exception as e:
                logger.warning(
                    "Strategy %s JSON decode failed; falling back to manual unescape: %s",
                    strategy_id,
                    e,
                )
                indicator_code = (
                    indicator_code.replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace("\\r", "\r")
                    .replace('\\"', '"')
                    .replace("\\'", "'")
                    .replace("\\\\", "\\")
                )
        strategy["_indicator_code"] = indicator_code
        strategy["_indicator_id"] = indicator_id

        return strategy

    except Exception as e:
        logger.error("Failed to load strategy config: %s", e)
        return None
