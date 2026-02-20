"""
插件式定时任务注册入口。

应用启动时调用 register_all_tasks() 统一注册各插件。
每个插件约定提供 JOB_ID / INTERVAL_MINUTES / ENABLED / run()。
"""

from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_all_tasks() -> None:
    """注册所有启用的插件定时任务到 APScheduler。"""
    from app.services.scheduler_service import register_scheduled_job
    from app.tasks import regime_switch, kline_sync, portfolio_monitor_task

    registered = []

    if regime_switch.ENABLED:
        register_scheduled_job(
            regime_switch.JOB_ID,
            regime_switch.run,
            regime_switch.INTERVAL_MINUTES,
            run_immediately=True,
        )
        registered.append(regime_switch.JOB_ID)
    else:
        logger.info("regime_switch disabled (set ENABLE_REGIME_SWITCH=false to disable)")

    if kline_sync.ENABLED:
        register_scheduled_job(
            kline_sync.JOB_ID,
            kline_sync.run,
            kline_sync.INTERVAL_MINUTES,
        )
        registered.append(kline_sync.JOB_ID)
    else:
        logger.info("kline_sync plugin disabled (using existing /api/scheduler route)")

    if portfolio_monitor_task.ENABLED:
        register_scheduled_job(
            portfolio_monitor_task.JOB_ID,
            portfolio_monitor_task.run,
            portfolio_monitor_task.INTERVAL_MINUTES,
        )
        registered.append(portfolio_monitor_task.JOB_ID)
    else:
        logger.info("portfolio_monitor_task disabled (set ENABLE_PORTFOLIO_MONITOR_TASK=false to disable)")

    if registered:
        logger.info("Plugin tasks registered: %s", ", ".join(registered))
    else:
        logger.info("No plugin tasks enabled")
