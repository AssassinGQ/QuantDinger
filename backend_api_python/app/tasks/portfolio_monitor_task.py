"""
portfolio_monitor_task 插件 — 组合风控定时检查。

定时由 APScheduler 调用 run()：
  1. 从 PortfolioAllocator 获取组合 equity
  2. 调 CircuitBreaker.check() 检查回撤
  3. 触发熔断时暂停所有被管理策略
"""

import os
import threading
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_portfolio_monitor"
INTERVAL_MINUTES = 5
# 默认启用；YAML 未开 multi_strategy / circuit_breaker 或无管理策略时 run() 不操作。需关闭时设 ENABLE_PORTFOLIO_MONITOR_TASK=false
ENABLED = os.getenv("ENABLE_PORTFOLIO_MONITOR_TASK", "true").lower() == "true"

_run_lock = threading.Lock()


def run() -> None:
    """由 APScheduler 定时调用。"""
    if not _run_lock.acquire(blocking=False):
        logger.debug("[portfolio_monitor] already running, skip")
        return
    try:
        _run_inner()
    finally:
        _run_lock.release()


def _run_inner() -> None:
    from app.tasks.regime_switch import _load_config

    config = _load_config()
    ms_cfg = config.get("multi_strategy", {})
    cb_cfg = ms_cfg.get("circuit_breaker", {})

    if not ms_cfg.get("enabled", False):
        return
    if not cb_cfg.get("enabled", False):
        return

    from app.services.portfolio_allocator import get_portfolio_allocator
    from app.services.circuit_breaker import get_circuit_breaker

    allocator = get_portfolio_allocator()
    breaker = get_circuit_breaker()

    summary = allocator.get_portfolio_summary()
    current_equity = summary.get("total_equity", 0.0) + summary.get("total_unrealized_pnl", 0.0)

    was_triggered = breaker.is_triggered
    is_triggered = breaker.check(current_equity, config)

    if is_triggered and not was_triggered:
        logger.warning("[portfolio_monitor] circuit breaker triggered, stopping all managed strategies")
        _emergency_stop_all(config)

    status = breaker.get_status(config)
    logger.info(
        "[portfolio_monitor] equity=%.0f drawdown=%.1f%% breaker=%s",
        current_equity, status["current_drawdown_pct"],
        "TRIGGERED" if is_triggered else "ok",
    )


def _emergency_stop_all(config: Dict) -> None:
    """熔断触发时暂停所有被管理策略。"""
    from app.services.portfolio_allocator import get_portfolio_allocator
    from app.tasks.regime_switch import _stop_strategies

    allocator = get_portfolio_allocator()
    all_ids = sorted(allocator._get_all_managed_ids())
    user_id_raw = config.get("user_id")
    user_id = int(user_id_raw) if user_id_raw is not None else None

    if all_ids:
        _stop_strategies(all_ids, user_id=user_id)
        logger.warning("[portfolio_monitor] emergency stop: %s", all_ids)
