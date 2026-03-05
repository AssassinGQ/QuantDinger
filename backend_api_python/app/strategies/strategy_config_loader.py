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


def _parse_json_fields(strategy: Dict[str, Any]) -> None:
    for field in [
        "indicator_config",
        "trading_config",
        "notification_config",
        "ai_model_config",
    ]:
        if isinstance(strategy.get(field), str):
            try:
                strategy[field] = json.loads(strategy[field])
            except (json.JSONDecodeError, TypeError, ValueError):
                strategy[field] = {}

    exchange_config_str = strategy.get("exchange_config", "{}")
    if isinstance(exchange_config_str, str) and exchange_config_str:
        try:
            strategy["exchange_config"] = json.loads(exchange_config_str)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            strategy_id = strategy.get("id")
            logger.error("Strategy %s failed to parse exchange_config: %s", strategy_id, e)
            strategy["exchange_config"] = {}
    else:
        strategy["exchange_config"] = {}


def _normalize_leverage_and_market(strategy: Dict[str, Any]) -> bool:
    trading_config = strategy.get("trading_config") or {}
    strategy_id = strategy.get("id")
    try:
        leverage_val = trading_config.get("leverage", 1)
        if isinstance(leverage_val, (list, tuple)):
            leverage_val = leverage_val[0] if leverage_val else 1
        leverage = float(leverage_val)
    except (TypeError, ValueError):
        logger.warning(
            "Strategy %s invalid leverage format, reset to 1: %s",
            strategy_id,
            trading_config.get("leverage"),
        )
        leverage = 1.0

    market_type = trading_config.get("market_type", "swap")
    if market_type not in ["swap", "spot"]:
        logger.error(
            "Strategy %s invalid market_type=%s (only swap/spot supported); refusing to start",
            strategy_id,
            market_type,
        )
        return False

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
    return True


def _normalize_capital(strategy: Dict[str, Any]) -> None:
    strategy_id = strategy.get("id")
    try:
        initial_capital_val = strategy.get("initial_capital", 1000)
        if isinstance(initial_capital_val, (list, tuple)):
            initial_capital_val = initial_capital_val[0] if initial_capital_val else 1000
        initial_capital = float(initial_capital_val)
    except (TypeError, ValueError):
        logger.warning(
            "Strategy %s invalid initial_capital format, reset to 1000: %s",
            strategy_id,
            strategy.get("initial_capital"),
        )
        initial_capital = 1000.0

    # Also sync trading_config.initial_capital so all consumers see the same value
    tc = strategy.get("trading_config")
    if isinstance(tc, dict):
        tc_capital = tc.get("initial_capital")
        if tc_capital is not None:
            try:
                tc_capital_f = float(tc_capital)
                if tc_capital_f != initial_capital:
                    logger.info(
                        "Strategy %s: DB initial_capital=%.2f differs from "
                        "trading_config.initial_capital=%.2f, using DB value",
                        strategy_id, initial_capital, tc_capital_f,
                    )
            except (TypeError, ValueError):
                pass
        tc["initial_capital"] = initial_capital

    strategy["_initial_capital"] = initial_capital


def _normalize_indicator_code(strategy: Dict[str, Any], dh: 'DataHandler') -> bool:
    indicator_config = strategy.get("indicator_config") or {}
    strategy_id = strategy.get("id")
    indicator_id = indicator_config.get("indicator_id")
    indicator_code = indicator_config.get("indicator_code", "")

    if not indicator_code and indicator_id:
        indicator_code = dh.get_indicator_code(indicator_id)

    if not indicator_code:
        logger.error("Strategy %s indicator_code is empty", strategy_id)
        return False

    if not isinstance(indicator_code, str):
        indicator_code = str(indicator_code)

    if "\\n" in indicator_code and "\n" not in indicator_code:
        try:
            decoded = json.loads(f'"{indicator_code}"')
            if isinstance(decoded, str):
                indicator_code = decoded
                logger.info("Strategy %s decoded escaped indicator_code", strategy_id)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
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
    return True


def _get_code_from_id_or_str(ind: Any, dh: Any) -> Optional[str]:
    """Helper to resolve indicator code from id or str"""
    if isinstance(ind, int):
        return dh.get_indicator_code(ind)
    if isinstance(ind, str):
        return ind
    return None

def _parse_symbol_indicators(trading_config: Dict[str, Any], dh: Any) -> Dict[str, Any]:
    """Parse symbol_indicators supporting both flat and nested dict formats."""
    # pylint: disable=too-many-branches,too-many-nested-blocks
    symbol_indicator_codes = {}
    symbol_indicators = trading_config.get("symbol_indicators", {})
    if not isinstance(symbol_indicators, dict) or not symbol_indicators:
        return symbol_indicator_codes

    strategy_type = trading_config.get("strategy_type", "single")
    symbol = trading_config.get("symbol", "")

    # For cross_sectional_weighted, if keyed by style directly (single symbol regime)
    is_flat_dict = not any(isinstance(v, dict) for v in symbol_indicators.values())
    if strategy_type == "cross_sectional_weighted" and symbol and is_flat_dict:
        nested_codes = {}
        for style, ind_or_list in symbol_indicators.items():
            if isinstance(ind_or_list, list):
                codes = []
                for ind in ind_or_list:
                    code = _get_code_from_id_or_str(ind, dh)
                    if code:
                        codes.append(code)
                if codes:
                    nested_codes[style] = codes
            else:
                code = _get_code_from_id_or_str(ind_or_list, dh)
                if code:
                    nested_codes[style] = [code]
        if nested_codes:
            symbol_indicator_codes[symbol] = nested_codes
        return symbol_indicator_codes

    # Old format or multi-symbol format: { sym: id } or { sym: { style: id } }
    for sym, ind_or_dict in symbol_indicators.items():
        if isinstance(ind_or_dict, dict):
            nested_codes = {}
            for style, ind_or_list in ind_or_dict.items():
                if isinstance(ind_or_list, list):
                    codes = []
                    for ind in ind_or_list:
                        code = _get_code_from_id_or_str(ind, dh)
                        if code:
                            codes.append(code)
                    if codes:
                        nested_codes[style] = codes
                else:
                    code = _get_code_from_id_or_str(ind_or_list, dh)
                    if code:
                        nested_codes[style] = [code]
            if nested_codes:
                symbol_indicator_codes[sym] = nested_codes
        else:
            code = _get_code_from_id_or_str(ind_or_dict, dh)
            if code:
                symbol_indicator_codes[sym] = code
    return symbol_indicator_codes


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
            # pylint: disable=import-outside-toplevel
            from app.services.data_handler import DataHandler
            dh = DataHandler()
        else:
            dh = data_handler

        strategy = dh.get_strategy_row(strategy_id)
        if not strategy:
            return None

        _parse_json_fields(strategy)

        if strategy.get("strategy_type") != "IndicatorStrategy":
            logger.error(
                "Strategy %s has unsupported strategy_type for realtime execution: %s",
                strategy_id,
                strategy.get("strategy_type"),
            )
            return None

        execution_mode = (strategy.get("execution_mode") or "signal").strip().lower()
        if execution_mode not in ["signal", "live"]:
            execution_mode = "signal"
        strategy["_execution_mode"] = execution_mode

        strategy["_strategy_name"] = strategy.get("strategy_name") or f"strategy_{int(strategy_id)}"
        strategy["_notification_config"] = strategy.get("notification_config") or {}

        if not _normalize_leverage_and_market(strategy):
            return None

        market_category = (strategy.get("market_category") or "Crypto").strip()
        strategy["_market_category"] = market_category
        logger.info("Strategy %s market_category: %s", strategy_id, market_category)

        _normalize_capital(strategy)

        trading_config = strategy.get("trading_config") or {}
        cs_type = trading_config.get("strategy_type") or trading_config.get("cs_strategy_type") or "single"

        if cs_type == "cross_sectional_weighted":
            strategy["_indicator_code"] = ""
            strategy["_indicator_id"] = None
        else:
            if not _normalize_indicator_code(strategy, dh):
                return None

        strategy["_symbol_indicator_codes"] = _parse_symbol_indicators(trading_config, dh)

        return strategy

    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as e:
        logger.error("Failed to load strategy config: %s", e)
        return None
