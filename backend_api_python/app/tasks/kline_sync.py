"""
kline_sync 插件 — 委托 scheduler_service 现有 K 线同步逻辑。

应用启动时默认注册，按间隔执行（run_immediately=False，首次运行在 interval 后）。
"""

from app.utils.logger import get_logger

logger = get_logger(__name__)

JOB_ID = "task_kline_sync"
INTERVAL_MINUTES = 400
ENABLED = True  # 默认启动，run_immediately=False


def run() -> None:
    """执行一次完整 K 线同步（委托 scheduler_service）。"""
    logger.info("[kline_sync] delegating to scheduler_service.run_kline_sync_once()")
    from app.services.scheduler_service import run_kline_sync_once
    run_kline_sync_once()
    logger.info("[kline_sync] done")
